# Click Lake Demo Dashboard (Read-Only)

Gold 집계 결과를 시연하기 위한 로컬 조회 화면입니다.

## 선택한 구조
- **React + Vite (TypeScript)**
- 이유:
  - Next.js보다 초기 구성이 가볍고 실행 속도가 빠름
  - 정적 JSON 기반 시연에 충분함
  - 이후 API 연동으로 확장하기 쉬움

## 데이터 소스
현재는 mock JSON 파일 사용:
- `public/demo-data/health.json`
- `public/demo-data/promotion_performance.json`
- `public/demo-data/campaign_funnel.json`

## 실행 방법
```bash
cd dashboard
npm install
npm run dev
```

브라우저에서 `http://localhost:5173` 접속.

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
1. `src/App.tsx`의 `fetch("/demo-data/*.json")` 부분을 API 호출로 교체
2. 예시 API 형태
   - `GET /api/gold/health`
   - `GET /api/gold/promotion-performance`
   - `GET /api/gold/campaign-funnel`
3. 응답 스키마를 현재 JSON 컬럼명과 동일하게 유지하면 UI 수정 최소화 가능

## 참고
- 이 대시보드는 **read-only 시연용 MVP**입니다.
- 데이터 수정/삭제 기능은 포함하지 않았습니다.
