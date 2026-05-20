# Click Lake

Click Lake는 이벤트 수집부터 분석 집계까지 한 번에 검증할 수 있는 이벤트 데이터 파이프라인 프로젝트입니다.

## 프로젝트 목적
- 웹/앱 이벤트를 안정적으로 수집
- 원본(raw) 보존 + 정제(Silver) + 지표(Gold) 계층화
- 운영 전 단계에서 대용량 시뮬레이션, 중복 제거, 품질 검증까지 수행
- Dashboard / Slack 질의로 결과를 빠르게 확인

## 아키텍처 요약
- SDK/테스트 페이지 → FastAPI `/collect`
- FastAPI → direct raw JSONL 저장 + Kafka publish
- Consumer → Kafka consume 후 raw sink / Bronze direct writer 저장
- Export/Upload → Databricks Volume 업로드
- Databricks Bronze / Silver / Gold SQL 변환 및 집계
- Dashboard / Slack 조회 API로 결과 확인

## 핵심 기능
- 이벤트 유효성 검증 및 invalid 분리
- `event_id` 기준 dedup / idempotency 강화
- direct vs kafka `ingestion_source` 비교 가능
- 파이프라인 오케스트레이터(`run_pipeline.py`) + dry-run
- Slack slash command 기반 조회형 MVP
- Docker Compose 기반 실행
- Kubernetes 매니페스트(server/dashboard/consumer)

## 현재 검증 가능한 포인트
- Bronze: source 분포, raw count, source_file 추적
- Silver: valid/invalid 분포, error_code 분포, dedup 결과
- Gold: health / promotion performance / campaign funnel 지표 비교

## 기술 스택
- Backend: FastAPI, Python
- Streaming: Kafka
- Storage/Analytics: Databricks (Bronze/Silver/Gold)
- Frontend: React + Vite Dashboard
- Infra: Docker Compose, Kubernetes