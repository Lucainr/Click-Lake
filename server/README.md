# Click Lake Collector (FastAPI MVP)

간단한 이벤트 수집용 FastAPI 서버입니다. SDK가 전송한 payload를 받고, 날짜 파티션 + 롤링 JSONL로 raw 저장

## 구조
```
server/
  app/
    main.py       # FastAPI 엔트리포인트
    schemas.py    # Pydantic 요청/응답 모델
    config.py     # 간단한 설정 (CORS 등)
    storage.py    # 날짜 파티션 + 파일 롤링 저장 로직
  data/
    raw_events/
      date=YYYY-MM-DD/
        events-0001.jsonl
        events-0002.jsonl
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

롤링 크기 변경(예: 500):
```bash
MAX_EVENTS_PER_FILE=500 uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 엔드포인트
- `GET /health` -> `{ "status": "ok" }`
- `POST /collect`
  - 요청 예시:
    ```json
    {
      "sdk_key": "clk_live_cp001",
      "events": [
        {"event_id": "evt_001", "event_type": "page_view", "event_time": "2026-04-12T10:00:00Z", "session_id": "sess_001", "page_url": "/"}
      ]
    }
    ```
  - 응답 예시:
    ```json
    {"success": true, "received_events": 1, "stored_dir": "server/data/raw_events/date=2026-04-15"}
    ```
  - 저장 형식(JSONL):
    ```json
    {"received_at":"2026-04-12T10:00:00Z","sdk_key":"clk_live_cp001","event":{"event_id":"evt_001","event_type":"page_view","event_time":"2026-04-12T10:00:00Z","session_id":"sess_001","page_url":"/"}}
    ```
    요청의 `events` 배열은 이벤트 1개당 JSONL 1줄로 append 됩니다.
  - 파일 롤링:
    - 기본 `max_events_per_file=1000`
    - 파일이 1000줄에 도달하면 `events-0002.jsonl` 같은 다음 파일로 저장
