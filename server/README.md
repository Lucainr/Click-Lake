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
      kafka_producer.py # /collect 이벤트 Kafka publish 서비스
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
../consumer/
  main.py
  Dockerfile
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

## Docker 실행
단독 빌드/실행:
```bash
cd server
docker build -t clicklake-server .
docker run --rm -p 8000:8000 --env-file .env clicklake-server
```

권장: 루트에서 compose 실행
```bash
docker compose up --build
```

Kafka 포함 compose 확인:
- broker 내부 주소: `kafka:9092` (server 컨테이너에서 사용)
- 호스트 테스트 주소: `localhost:29092`

롤링 크기 변경(예: 500)
```bash
MAX_EVENTS_PER_FILE=500 uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 엔드포인트
- `GET /health` -> `{ "status": "ok" }`
- `GET /api/gold/health[?sdk_key=...]`
- `GET /api/gold/promotion-performance[?sdk_key=...]`
- `GET /api/gold/campaign-funnel[?sdk_key=...]`
- `GET /api/gold/dashboard[?sdk_key=...]`  # health/promotion/funnel 한번에 조회

Gold API 오류 응답 형식:
```json
{
  "error_code": "DATABRICKS_QUERY_FAILED",
  "message": "Failed to query Databricks Gold table",
  "details": "..."
}
```

주요 `error_code`:
- `CONFIG_MISSING`
- `DATABRICKS_CONNECT_FAILED`
- `WAREHOUSE_UNAVAILABLE`
- `DATABRICKS_QUERY_FAILED`
- `RESULT_PARSE_FAILED`
- `UNKNOWN_ERROR`
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
  - Kafka publish 병행
    - topic: `clicklake.events.raw`
    - 메시지 구조:
      ```json
      {
        "received_at": "2026-04-22T12:00:00Z",
        "sdk_key": "clk_live_demo",
        "events": [ ... ]
      }
      ```
    - 정책: raw 저장 성공 시 API는 성공 응답을 유지하고, Kafka publish 실패는 warning 로그만 남깁니다.

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

성능 관련 옵션(선택):
```env
GOLD_QUERY_LIMIT=500
GOLD_API_CACHE_TTL_SECONDS=20
GOLD_WARMUP_ON_STARTUP=true
```

Kafka 관련 옵션:
```env
KAFKA_ENABLED=true
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_TOPIC_RAW_EVENTS=clicklake.events.raw
KAFKA_CLIENT_ID=clicklake-server
KAFKA_PUBLISH_TIMEOUT_SECONDS=3
```

## Kafka Consumer (Stage 2)
- compose 서비스명: `consumer`
- source topic: `clicklake.events.raw`
- raw sink 경로(호스트): `server/data/raw_events_kafka/date=YYYY-MM-DD/events-0001.jsonl`
- Bronze direct sink 경로(호스트): `server/data/bronze_batches_kafka/date=YYYY-MM-DD/bronze_events-0001.jsonl`
- 저장 단위: 두 sink 모두 event 1건당 JSONL 1줄

consumer sink 제어 환경변수:
```env
KAFKA_ENABLE_RAW_SINK=true
KAFKA_SINK_DIR=/data/raw_events_kafka
SINK_MAX_EVENTS_PER_FILE=1000
KAFKA_ENABLE_BRONZE_DIRECT=true
KAFKA_BRONZE_SINK_DIR=/data/bronze_batches_kafka
KAFKA_BRONZE_MAX_EVENTS_PER_FILE=1000
```

로그 확인:
```bash
docker compose logs -f consumer
```

Kafka 메시지 확인(선택):
```bash
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 \
  --topic clicklake.events.raw \
  --from-beginning \
  --max-messages 5
```

설정 예시:
```bash
cd server
cp .env.example .env
```

## Raw -> Bronze Export (파일 단위)
- 입력 소스(동시 지원):
  - `data/raw_events/date=.../events-....jsonl`
  - `data/raw_events_kafka/date=.../events-....jsonl`
- 처리 단위: line offset이 아니라 **파일 단위**
- 체크포인트: `data/checkpoints/bronze_export_state.json`
- 체크포인트 구조
  ```json
  {
    "processed_files": [
      "raw_events/date=2026-04-15/events-0001.jsonl",
      "raw_events_kafka/date=2026-04-15/events-0001.jsonl"
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
- Bronze 레코드에 `ingestion_source` 포함:
  - `direct_raw` (raw_events)
  - `kafka_consumer` (raw_events_kafka)

확인
```bash
cat data/checkpoints/bronze_export_state.json
find out/bronze_batches -type f | sort
```

Databricks Bronze SQL
- `../sql/bronze/03_create_events_raw_json.sql`
- `COPY INTO`의 `SOURCE_PATH`는 Databricks에서 접근 가능한 경로로 교체 필요

## Bronze Batch -> Databricks Volume Upload
- 입력 source(동시 지원):
  - direct: `out/bronze_batches/*.jsonl`
  - kafka direct: `data/bronze_batches_kafka/**/*.jsonl`
- Databricks 출력 대상(권장 분리):
  - direct: `DATABRICKS_VOLUME_PATH_DIRECT`
    - 예: `/Volumes/workspace/clicklake_bronze/raw_batches/direct`
  - kafka: `DATABRICKS_VOLUME_PATH_KAFKA`
    - 예: `/Volumes/workspace/clicklake_bronze/raw_batches/kafka`
- 체크포인트: `data/checkpoints/bronze_upload_state.json`
- 체크포인트 구조
  ```json
  {
    "uploaded_files": [
      "out/bronze_batches/bronze_events_20260415T101500Z.jsonl",
      "data/bronze_batches_kafka/date=2026-05-14/bronze_events-0001.jsonl"
    ]
  }
  ```
- 처리 순서: source/direct->kafka + 파일명 오름차순
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
- `Uploaded source=direct file=bronze_events_20260415T101500Z.jsonl remote=/Volumes/.../direct/bronze_events_20260415T101500Z.jsonl`
- `Uploaded source=kafka file=date=2026-05-14/bronze_events-0001.jsonl remote=/Volumes/.../kafka/date=2026-05-14/bronze_events-0001.jsonl`
- `No new batch files to upload.`

Databricks 업로드 확인
0) 필요 시 Volume 생성
```sql
CREATE VOLUME IF NOT EXISTS workspace.clicklake_bronze.raw_batches;
```
1) SQL Editor에서 Volume 파일 목록 확인
```sql
LIST '/Volumes/workspace/clicklake_bronze/raw_batches/direct';
LIST '/Volumes/workspace/clicklake_bronze/raw_batches/kafka';
```
2) 파일 데이터 확인 (선택)
```sql
SELECT * FROM json.`/Volumes/workspace/clicklake_bronze/raw_batches/direct/*.jsonl` LIMIT 10;
SELECT * FROM json.`/Volumes/workspace/clicklake_bronze/raw_batches/kafka/date=*/bronze_events-*.jsonl` LIMIT 10;
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
LIST '/Volumes/workspace/clicklake_bronze/raw_batches/direct';
LIST '/Volumes/workspace/clicklake_bronze/raw_batches/kafka';
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

## 전체 파이프라인 Orchestrator
수동 단계를 한 번에 실행:
1. raw JSONL -> Bronze batch export
2. Bronze batch -> Databricks Volume upload
3. Bronze SQL refresh
4. Silver SQL refresh
5. Gold SQL refresh

실행:
```bash
cd server
source .venv/bin/activate
python scripts/run_pipeline.py
```

옵션:
```bash
python scripts/run_pipeline.py --dry-run
python scripts/run_pipeline.py --skip-export
python scripts/run_pipeline.py --skip-upload
python scripts/run_pipeline.py --skip-sql
python scripts/run_pipeline.py --bronze-only
python scripts/run_pipeline.py --silver-only
python scripts/run_pipeline.py --gold-only
```

Dry-run 예시:
```bash
python scripts/run_pipeline.py --dry-run --skip-upload
python scripts/run_pipeline.py --dry-run --gold-only
```

`--dry-run`은 실행 예정 단계/SQL 파일/skip 항목만 출력하고 실제 명령은 수행하지 않습니다.

필수 환경변수:
- `DATABRICKS_HOST`
- `DATABRICKS_TOKEN`
- `DATABRICKS_HTTP_PATH`
- `DATABRICKS_VOLUME_PATH_DIRECT` (upload direct source)
- `DATABRICKS_VOLUME_PATH_KAFKA` (upload kafka source)
  - (호환) `DATABRICKS_VOLUME_PATH`만 있으면 자동으로 `/direct`, `/kafka` suffix 사용

실패 시 확인 포인트:
- export 실패: raw JSONL 경로/체크포인트 파일 권한 확인
- upload 실패: `DATABRICKS_VOLUME_PATH_DIRECT`/`DATABRICKS_VOLUME_PATH_KAFKA`/토큰 권한 확인
- SQL 실패: SQL Warehouse 상태(실행 중 여부), Gold/Bronze 테이블 권한, SQL 파일 경로 확인
