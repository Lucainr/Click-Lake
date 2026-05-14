# Click-Lake

## Docker (3단계: server + dashboard + kafka + consumer)
현재 구조를 Docker Compose로 기동할 수 있습니다.

```bash
docker compose up --build
```

접속:
- FastAPI: `http://localhost:8000/health`
- Dashboard: `http://localhost:5173`
- Kafka(호스트 테스트용 listener): `localhost:29092`

구성:
- `server` 컨테이너: FastAPI (`uvicorn app.main:app`)
- `dashboard` 컨테이너: Vite dev server
- `kafka` 컨테이너: ingest 이벤트 publish 대상 broker
- `consumer` 컨테이너: Kafka 메시지를 날짜별 JSONL sink로 저장
