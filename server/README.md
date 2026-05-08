# Click Lake Collector (FastAPI MVP)

간단한 이벤트 수집용 FastAPI 서버
SDK가 전송한 payload를 받고, 날짜 파티션 + 롤링 JSONL로 raw 저장

## 구조
```
server/
  app/
    main.py       # FastAPI 엔트리포인트
    schemas.py    # Pydantic 요청/응답 모델
    config.py     # 간단한 설정 (CORS 등)
    storage.py    # 날짜 파티션 + 파일 롤링 저장 로직
    routes/
      gold.py     # Gold read-only API endpoint
    services/
      gold_data.py # Gold 조회 데이터 로딩 서비스(Databricks SQL)
  scripts/
    export_raw_to_bronze.py
    upload_bronze_batches_to_databricks.py
  data/
    raw_events/
      date=YYYY-MM-DD/
        events-0001.jsonl
        events-0002.jsonl
    checkpoints/
      bronze_export_state.json
  out/
    bronze_batches/
      bronze_events_YYYYMMDDTHHMMSSZ.jsonl
  .env.example
  requirements.txt
```

## 설치
```bash
cd server
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 실행
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

롤링 크기 변경(예: 500)
```bash
MAX_EVENTS_PER_FILE=500 uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 엔드포인트
- `GET /health` -> `{ "status": "ok" }`
- `GET /api/gold/health[?sdk_key=...]`
- `GET /api/gold/promotion-performance[?sdk_key=...]`
- `GET /api/gold/campaign-funnel[?sdk_key=...]`
- `POST /collect`
  - 요청 예시
    ```json
    {
      "sdk_key": "clk_live_cp001",
      "events": [
        {"event_id": "evt_001", "event_type": "page_view", "event_time": "2026-04-12T10:00:00Z", "session_id": "sess_001", "page_url": "/"}
      ]
    }
    ```
  - 응답 예시
    ```json
    {"success": true, "received_events": 1, "stored_dir": "server/data/raw_events/date=2026-04-15"}
    ```
  - 저장 형식(JSONL)
    ```json
    {"received_at":"2026-04-12T10:00:00Z","sdk_key":"clk_live_cp001","event":{"event_id":"evt_001","event_type":"page_view","event_time":"2026-04-12T10:00:00Z","session_id":"sess_001","page_url":"/"}}
    ```
    요청의 `events` 배열은 이벤트 1개당 JSONL 1줄로 append 됩니다.
  - 파일 롤링
    - 기본 `max_events_per_file=1000`
    - 파일이 1000줄에 도달하면 `events-0002.jsonl` 같은 다음 파일로 저장

### Gold read-only API 데이터 소스
- 현재 단계에서는 Databricks SQL Warehouse를 직접 조회합니다.
- 조회 대상 테이블:
  - `workspace.clicklake_gold.gold_workspace_health_daily_json`
  - `workspace.clicklake_gold.gold_promotion_performance_daily_json`
  - `workspace.clicklake_gold.gold_campaign_funnel_daily_json`
- `sdk_key` 쿼리가 있으면 SQL `WHERE sdk_key = ?`로 서버 측 필터링합니다.

필수 환경변수:
```env
DATABRICKS_HOST=https://<workspace-host>
DATABRICKS_TOKEN=<pat-token>
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/<warehouse-id>
```

설정 예시:
```bash
cd server
cp .env.example .env
```

## Raw -> Bronze Export (파일 단위)
- 처리 단위: line offset이 아니라 `date=.../events-....jsonl` 파일 단위
- 체크포인트: `data/checkpoints/bronze_export_state.json`
- 체크포인트 구조
  ```json
  {
    "processed_files": [
      "date=2026-04-15/events-0001.jsonl"
    ]
  }
  ```

실행
```bash
cd server
source .venv/bin/activate
python scripts/export_raw_to_bronze.py
```

결과
- 신규 파일만 export
- 출력: `out/bronze_batches/bronze_events_<timestamp>.jsonl`
- 같은 파일은 다음 실행에서 재처리되지 않음

확인
```bash
cat data/checkpoints/bronze_export_state.json
find out/bronze_batches -type f | sort
```

Databricks Bronze SQL
- `../sql/bronze/03_create_events_raw_json.sql`
- `COPY INTO`의 `SOURCE_PATH`는 Databricks에서 접근 가능한 경로로 교체 필요

## Bronze Batch -> Databricks Volume Upload
- 입력: `out/bronze_batches/*.jsonl`
- 출력 대상: `DATABRICKS_VOLUME_PATH`
  - 예1: `/Volumes/workspace/clicklake_bronze/raw_files`
  - 예2: `/Volumes/workspace/clicklake_bronze/raw_batches`
- 체크포인트: `data/checkpoints/bronze_upload_state.json`
- 체크포인트 구조
  ```json
  {
    "uploaded_files": [
      "bronze_events_20260415T101500Z.jsonl"
    ]
  }
  ```
- 처리 순서: 파일명 오름차순
- 성공한 파일만 checkpoint에 반영 (중복 업로드 방지)

환경변수 설정
```bash
cd server
cp .env.example .env
```
업로드 스크립트는 `server/.env`를 자동으로 읽습니다.
이미 셸에 export된 환경변수가 있으면 그 값을 우선 사용합니다.

실행
```bash
cd server
source .venv/bin/activate
python scripts/upload_bronze_batches_to_databricks.py
```

성공/재실행 예시
- `Uploaded bronze_events_20260415T101500Z.jsonl`
- `No new batch files to upload.`

Databricks 업로드 확인
0) 필요 시 Volume 생성
```sql
CREATE VOLUME IF NOT EXISTS workspace.clicklake_bronze.raw_batches;
```
1) SQL Editor에서 Volume 파일 목록 확인
```sql
LIST '/Volumes/workspace/clicklake_bronze/raw_files';
LIST '/Volumes/workspace/clicklake_bronze/raw_batches';
```
2) 파일 데이터 확인 (선택)
```sql
SELECT * FROM json.`/Volumes/workspace/clicklake_bronze/raw_files/*.jsonl` LIMIT 10;
SELECT * FROM json.`/Volumes/workspace/clicklake_bronze/raw_batches/*.jsonl` LIMIT 10;
```

## End-to-End 검증 순서 (로컬 -> Databricks Bronze)
1) Bronze batch 파일 생성
```bash
cd server
source .venv/bin/activate
python scripts/export_raw_to_bronze.py
```
2) Databricks Volume 업로드
```bash
python scripts/upload_bronze_batches_to_databricks.py
```
3) Databricks에서 업로드 파일 확인
```sql
LIST '/Volumes/workspace/clicklake_bronze/raw_files';
```
4) Bronze 테이블 생성 + 적재
```sql
-- sql/bronze/03_create_events_raw_json.sql 실행
```
5) 적재 결과 확인
```sql
SELECT COUNT(*) AS row_count
FROM workspace.clicklake_bronze.events_raw_json;
```
