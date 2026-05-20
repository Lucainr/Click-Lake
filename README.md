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
- `consumer` 컨테이너: Kafka 메시지를 raw sink + Bronze direct JSONL sink로 저장

## 대규모 이벤트 시뮬레이터
수십만 건 규모 테스트 데이터 생성 스크립트:
- `server/scripts/simulate_events.py`

빠른 예시:
```bash
cd server
source .venv/bin/activate
python scripts/simulate_events.py --mode api --events 200000 --seed 42
```

## Kubernetes (1단계: app-level only)
`server`, `dashboard`, `consumer`만 Kubernetes manifest로 분리했습니다.
Kafka는 이번 단계에서 Kubernetes 리소스로 포함하지 않았습니다.

manifest 위치:
- `k8s/namespace.yaml`
- `k8s/configmap.yaml`
- `k8s/secret.example.yaml`
- `k8s/server-deployment.yaml`
- `k8s/server-service.yaml`
- `k8s/dashboard-deployment.yaml`
- `k8s/dashboard-service.yaml`
- `k8s/consumer-deployment.yaml`

적용 순서(권장):
```bash
kubectl apply -f k8s/namespace.yaml
# secret.example.yaml을 secret.yaml로 복사 후 실제 값 입력
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/server-deployment.yaml
kubectl apply -f k8s/server-service.yaml
kubectl apply -f k8s/dashboard-deployment.yaml
kubectl apply -f k8s/dashboard-service.yaml
kubectl apply -f k8s/consumer-deployment.yaml
```

한 번에 적용:
```bash
kubectl apply -f k8s/
```

로컬 확인 예시(port-forward):
```bash
kubectl -n clicklake port-forward svc/clicklake-server-service 8000:8000
kubectl -n clicklake port-forward svc/clicklake-dashboard-service 5173:5173
```

dashboard ↔ server 통신 방식:
- 브라우저에서는 `server` 서비스 DNS를 직접 해석하지 못하므로,
  dashboard는 `VITE_API_BASE_URL=/`(same-origin)로 요청합니다.
- Vite dev server가 `/api` 요청을 `http://clicklake-server-service:8000`으로 프록시합니다.

## Slack 조회형 연동 (1단계 MVP)
FastAPI에 Slack slash command endpoint를 추가했습니다.

- endpoint: `POST /slack/commands/clicklake`
- 명령:
  - `health [sdk_key]`
  - `top-invalid [sdk_key] [limit]`
  - `top-ctr [sdk_key] [limit]`
  - `funnel [sdk_key] [limit]`
  - `help`

환경변수(`server/.env`):
- `SLACK_ENABLE_SIGNATURE_VALIDATION=false` (개발 기본)
- `SLACK_SIGNING_SECRET=<replace-me>` (실서비스 권장)
