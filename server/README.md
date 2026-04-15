# Click Lake Collector (FastAPI MVP)

간단한 이벤트 수집용 FastAPI 서버입니다. SDK가 전송한 payload를 받고, 이벤트 단위로 JSONL raw 파일에 저장합니다.

## 구조
```
server/
  app/
    main.py       # FastAPI 엔트리포인트
    schemas.py    # Pydantic 요청/응답 모델
    config.py     # 간단한 설정 (CORS 등)
    storage.py    # JSONL append 저장 로직
  data/
    raw_events.jsonl
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
    {"success": true, "received_events": 1, "stored_path": "server/data/raw_events.jsonl"}
    ```
  - 저장 형식(JSONL):
    ```json
    {"received_at":"2026-04-12T10:00:00Z","sdk_key":"clk_live_cp001","event":{"event_id":"evt_001","event_type":"page_view","event_time":"2026-04-12T10:00:00Z","session_id":"sess_001","page_url":"/"}}
    ```
    요청의 `events` 배열은 이벤트 1개당 JSONL 1줄로 append 됩니다.

## 브라우저 SDK와 테스트 방법
1) 서버 실행: `uvicorn app.main:app --reload --port 8000`
2) 프런트 SDK 예제(`examples/basic.html`)를 열고 콘솔 확인.
3) 서버 터미널 로그에 `received sdk_key=... events=...`가 찍히는지 확인.
4) 저장 파일 확인: `cat data/raw_events.jsonl`

## 확장 포인트 (Kafka 등)
- `app/main.py`에서 `append_raw_events_jsonl(...)` 호출부를 Kafka producer 호출로 교체하면 됩니다.
- 파일 저장 상세 로직은 `app/storage.py`에 모여 있으므로 교체 범위가 명확합니다.
