# Click-Lake

## Docker (1단계: server + dashboard)
현재 구조를 Docker Compose로 기동할 수 있습니다.

```bash
docker compose up --build
```

접속:
- FastAPI: `http://localhost:8000/health`
- Dashboard: `http://localhost:5173`

구성:
- `server` 컨테이너: FastAPI (`uvicorn app.main:app`)
- `dashboard` 컨테이너: Vite dev server
