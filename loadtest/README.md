# Click Lake k6 Load Test (Stage 1)

`/collect` 대상 부하 테스트 스크립트:
- `loadtest/k6_collect.js`

목표:
1. 동시 요청에서 `/collect` 성공률 확인
2. 응답시간(p95/p99) 확인
3. Kafka publish/consumer 및 Databricks 적재 정합성 확인

## 사전 준비
- FastAPI server 실행 (`/collect` 가능 상태)
- (권장) Kafka + consumer 실행
- k6 설치

macOS 예시:
```bash
brew install k6
```

## 실행 시나리오

### 1) Smoke (기본)
```bash
k6 run loadtest/k6_collect.js \
  -e TARGET_URL=http://localhost:8000/collect \
  -e TEST_TYPE=smoke
```

### 2) Load (중간 부하)
```bash
k6 run loadtest/k6_collect.js \
  -e TARGET_URL=http://localhost:8000/collect \
  -e TEST_TYPE=load
```

### 3) Stress (고부하)
```bash
k6 run loadtest/k6_collect.js \
  -e TARGET_URL=http://localhost:8000/collect \
  -e TEST_TYPE=stress
```

### 4) 전체 시나리오 연속
```bash
k6 run loadtest/k6_collect.js \
  -e TARGET_URL=http://localhost:8000/collect \
  -e TEST_TYPE=all
```

## 주요 환경변수
- `TARGET_URL` (기본: `http://localhost:8000/collect`)
- `TEST_TYPE` (`smoke|load|stress|all`)
- `RUN_ID` (미지정 시 timestamp)
- `SDK_KEYS` (쉼표 구분)
- `DAYS` (event_time 분산 일수, 기본 14)
- `INVALID_RATIO` (기본 0.03)
- `DUPLICATE_RATIO` (기본 0.01)
- `SLEEP_MS` (요청 간 sleep, 기본 200ms)

## 스크립트 특성
- 세션 기반 funnel 이벤트 생성:
  - `page_view`
  - `promotion_view`
  - `promotion_click`
  - `product_view`
  - `add_to_cart`
- 캠페인 프로파일(A/B/C/D)로 CTR/전환 차이 유도
- 일부 invalid/duplicate 이벤트 포함

## 성공 기준 (MVP)
- `http_req_failed < 1%`
- `http_req_duration p95 < 1200ms`
- `http_req_duration p99 < 2500ms`
- 체크 성공률(`checks`) 99% 이상

## 운영 로그 확인 포인트
- server 로그: `/collect` 200 비율, 예외 여부
- consumer 로그: consume/sink write 정상 여부
- Kafka broker: publish 실패/지연 징후

## Databricks 검증 쿼리

Bronze source 분포:
```sql
SELECT ingestion_source, COUNT(*) AS cnt
FROM workspace.clicklake_bronze.events_raw_json
GROUP BY ingestion_source
ORDER BY cnt DESC;
```

Silver valid/invalid 분포:
```sql
SELECT ingestion_source, COUNT(*) AS cnt
FROM workspace.clicklake_silver.silver_events_json
GROUP BY ingestion_source
ORDER BY cnt DESC;
```

```sql
SELECT ingestion_source, error_code, COUNT(*) AS cnt
FROM workspace.clicklake_silver.silver_invalid_events_json
GROUP BY ingestion_source, error_code
ORDER BY ingestion_source, cnt DESC;
```

Gold 확인:
```sql
SELECT *
FROM workspace.clicklake_gold.gold_workspace_health_daily_json
ORDER BY event_date DESC, raw_event_count DESC;
```

```sql
SELECT *
FROM workspace.clicklake_gold.gold_promotion_performance_daily_json
ORDER BY event_date DESC, promotion_views DESC;
```

```sql
SELECT *
FROM workspace.clicklake_gold.gold_campaign_funnel_daily_json
ORDER BY event_date DESC, promotion_view_sessions DESC;
```

## 참고
k6는 API 부하를 검증하고, 실제 브라우저 상호작용 검증은 `examples/demo-store.html`로 분리해 수행합니다.
