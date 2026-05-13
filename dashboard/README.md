# Click Lake Demo Dashboard (Read-Only)

Gold 집계 결과를 시연하기 위한 로컬 조회 화면입니다.

## 선택한 구조
- **React + Vite (TypeScript)**
- 이유:
  - Next.js보다 초기 구성이 가볍고 실행 속도가 빠름
  - 정적 JSON 기반 시연에 충분함
  - 이후 API 연동으로 확장하기 쉬움

## 데이터 소스
FastAPI read-only API 사용:
- `GET /api/gold/health`
- `GET /api/gold/promotion-performance`
- `GET /api/gold/campaign-funnel`

기본값은 same-origin(`""`)이며, 로컬 개발에서 프론트/백엔드 포트가 다르면
`VITE_API_BASE_URL`을 설정합니다.
Vite dev server는 `/api`를 `http://localhost:8000`으로 프록시하도록 설정되어 있습니다.

## 실행 방법
```bash
cd dashboard
npm install
# 필요 시 API 베이스 설정
# export VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

브라우저에서 `http://localhost:5173` 접속.

## Docker Compose 실행
루트에서 실행:
```bash
docker compose up --build
```

compose 환경에서는 dashboard가 `VITE_API_BASE_URL=http://localhost:8000`를 사용해
host 노출된 FastAPI 포트로 조회합니다.

## 화면 구성
1. Health 요약
   - summary cards: raw / valid / invalid / invalid ratio
   - health 테이블
2. Promotion Performance
   - CTR, post-click 지표 중심 테이블
3. Campaign Funnel
   - 세션 기반 퍼널 및 비율 테이블

## 정렬/필터
- 기본 정렬: 최근 날짜 우선
- Promotion: CTR 우선 정렬
- Funnel: view sessions 우선 정렬
- 상단 SDK Key 필터(`All` 포함)

## 실제 Databricks live 데이터로 전환하려면
1. `server/app/services/gold_data.py`의 JSON 로딩 로직을 Databricks 조회 로직으로 교체
2. API 응답 스키마(컬럼명)는 동일 유지
3. dashboard는 별도 수정 없이 그대로 조회 가능

## 참고
- 이 대시보드는 **read-only 시연용 MVP**입니다.
- 데이터 수정/삭제 기능은 포함하지 않았습니다.
