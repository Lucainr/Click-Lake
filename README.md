<div align="center">

<img src="https://img.shields.io/badge/Click_Lake-Event_Pipeline-0EA5E9?style=for-the-badge" alt="Click Lake" />

# Click Lake

### 커머스 이벤트 수집부터 Gold 지표 집계까지, 풀스택 데이터 파이프라인

<br />

<p align="center">
  <img src="https://img.shields.io/badge/TypeScript-5.0-3178C6?style=flat-square&logo=typescript" />
  <img src="https://img.shields.io/badge/React-Vite-61DAFB?style=flat-square&logo=react" />
  <img src="https://img.shields.io/badge/tsup-ESM_SDK-000000?style=flat-square" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-Python_3.11+-009688?style=flat-square&logo=fastapi" />
  <img src="https://img.shields.io/badge/Kafka-KRaft-231F20?style=flat-square&logo=apachekafka" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis" />
  <img src="https://img.shields.io/badge/Databricks-SQL-FF3621?style=flat-square&logo=databricks" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker" />
  <img src="https://img.shields.io/badge/Kubernetes-Manifests-326CE5?style=flat-square&logo=kubernetes" />
  <img src="https://img.shields.io/badge/Slack-Slash_Command-4A154B?style=flat-square&logo=slack" />
</p>

<br />

**브라우저 SDK** · **Kafka 스트리밍** · **Medallion 레이크하우스** · **실시간 대시보드**

</div>

<br />

---

## 📌 Overview

**Click Lake**는 브라우저에서 발생하는 커머스 이벤트(페이지뷰, 프로모션, 장바구니 등)를 수집하고, Kafka를 거쳐 Databricks의 Bronze → Silver → Gold Medallion 아키텍처로 집계·분석하는 풀스택 데이터 파이프라인 프로젝트입니다.

> 💡 **"이벤트 수집부터 Gold 지표 확인까지, 하나의 파이프라인으로."**

<br />

## ✨ Key Features

<table>
<tr>
<td width="50%">

### 📦 브라우저 SDK
- TypeScript + tsup 빌드, **ESM 패키지**
- `page_view` · `promotion_view` · `promotion_click` · `product_view` · `add_to_cart` 이벤트
- 배치 큐 + 주기 flush + **Beacon API** 낙장 방지
- `crypto.randomUUID()` 기반 고유 `event_id`
- `onError` 콜백으로 프로덕션 검증 오류 추적

</td>
<td width="50%">

### ⚡ 이벤트 수집 서버
- **FastAPI** 기반 `/collect` 엔드포인트
- Kafka(`clicklake.events.raw`) 비동기 publish
- **Redis** 공유 캐시로 Gold API 응답 가속
- 요청당 이벤트 수 제한 (기본 500건)
- `/health` readiness probe 지원

</td>
</tr>
<tr>
<td width="50%">

### 🏗️ Medallion 레이크하우스
- **Bronze**: raw JSONL → Databricks Volume 업로드
- **Silver**: 유효성 검증 + `event_id` 기준 dedup
- **Gold**: 워크스페이스 건강도 · 프로모션 성과 · 캠페인 퍼널 집계
- `ingestion_source`(`direct_raw` / `kafka_consumer`) 계보 추적
- 파이프라인 오케스트레이터(`run_pipeline.py`) + dry-run 지원

</td>
<td width="50%">

### 📊 대시보드 & Slack 연동
- React + Vite **Gold API 대시보드**
- **Slack slash command** 조회형 MVP
  - `/clicklake health`, `top-ctr`, `funnel` 등
- Slack 요청 서명 검증 (HMAC-SHA256)
- 200K 이벤트 시뮬레이터로 대규모 검증 가능

</td>
</tr>
</table>

<br />

---

## 🛠️ Tech Stack

### SDK (Browser)

| Category | Technologies |
|----------|-------------|
| **Language** | TypeScript 5 |
| **Build** | tsup (ESM + CJS dual output) |
| **Delivery** | Fetch API, Beacon API, 배치 큐 |
| **ID 생성** | `crypto.randomUUID()` |

### Server

| Category | Technologies |
|----------|-------------|
| **Framework** | FastAPI, Uvicorn |
| **Language** | Python 3.11+ |
| **Streaming** | Apache Kafka (KRaft mode) |
| **Cache** | Redis 7 |
| **Validation** | Pydantic v1 |

### Data Platform

| Category | Technologies |
|----------|-------------|
| **Storage** | Databricks Volumes (JSONL) |
| **Analytics** | Databricks SQL (Bronze / Silver / Gold) |
| **Connector** | databricks-sql-connector |
| **Format** | JSONL, date-partition |

### Infrastructure

| Category | Technologies |
|----------|-------------|
| **Local** | Docker Compose |
| **Production** | Kubernetes (namespace, ConfigMap, Secret) |
| **Notification** | Slack Slash Command |
| **Load Test** | k6 |

<br />

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Browser / Client                          │
│               Click Lake SDK (TypeScript · ESM)                  │
│        page_view · promotion · product_view · add_to_cart        │
└──────────────────────────┬───────────────────────────────────────┘
                           │  POST /collect (batch)
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                   FastAPI Collector Server                        │
│              sdk_key 검증 · 이벤트 수 제한 (500/req)              │
│                   Redis 캐시 (Gold API TTL)                       │
└──────────┬───────────────────────────────┬───────────────────────┘
           │ Kafka Publish                 │ Gold Read API
           ▼                               ▼
┌─────────────────────┐        ┌───────────────────────────────────┐
│  Kafka (KRaft)      │        │       React Dashboard             │
│  clicklake.events   │        │   health · promotion · funnel     │
│       .raw          │        └───────────────────────────────────┘
└────────┬────────────┘
         │ Consume
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Kafka Consumer                             │
│         Raw JSONL Sink  ·  Bronze Direct Sink (date partition)  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Upload Script
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Databricks Volumes                           │
│         /raw_batches/direct  ·  /raw_batches/kafka              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ SQL
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
    ┌──────────┐    ┌──────────┐    ┌──────────────┐
    │  Bronze  │───▶│  Silver  │───▶│     Gold     │
    │ raw ingest│   │ validate │    │  집계 지표   │
    │          │   │  dedup   │    │health/promo/ │
    └──────────┘   └──────────┘    │    funnel    │
                                   └──────────────┘
```

<br />

---

## 📂 Project Structure

```
Click-Lake/
│
├── 📁 src/                          # Browser SDK (TypeScript)
│   ├── core/                        # init · config · queue · sender · track
│   ├── context/                     # device · identity · page · session
│   ├── events/                      # pageView · promotionView · addToCart 등
│   ├── types/                       # EventPayload · SDKConfig 타입
│   ├── utils/                       # uuid · logger · time
│   ├── validation/                  # validateEvent
│   └── index.ts                     # ClickLake 퍼블릭 API
│
├── 📁 server/                       # FastAPI 수집 서버
│   ├── app/
│   │   ├── main.py                  # FastAPI 엔트리포인트 · /collect
│   │   ├── config.py                # 환경변수 설정 (Pydantic Settings)
│   │   ├── schemas.py               # 요청/응답 모델
│   │   ├── storage.py               # JSONL 파일 롤링 저장
│   │   ├── routes/
│   │   │   ├── gold.py              # Gold read-only API
│   │   │   └── slack.py             # Slack slash command
│   │   └── services/
│   │       ├── kafka_producer.py    # Kafka 비동기 publish
│   │       ├── gold_data.py         # Databricks SQL 조회 + Redis 캐시
│   │       └── slack_query_service.py
│   └── scripts/
│       ├── export_raw_to_bronze.py  # raw JSONL → Bronze batch
│       ├── upload_bronze_batches_to_databricks.py
│       ├── run_pipeline.py          # 전체 파이프라인 오케스트레이터
│       └── simulate_events.py       # 대량 이벤트 시뮬레이터 (200K)
│
├── 📁 consumer/                     # Kafka Consumer
│   ├── main.py                      # Raw sink · Bronze direct sink
│   └── Dockerfile
│
├── 📁 dashboard/                    # React + Vite 대시보드
│   └── src/
│
├── 📁 sql/                          # Databricks SQL
│   ├── bronze/                      # 03_create_events_raw_json.sql
│   ├── silver/                      # valid / invalid events
│   └── gold/                        # health · promotion · funnel
│
├── 📁 k8s/                          # Kubernetes 매니페스트
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.example.yaml
│   ├── server-deployment.yaml
│   ├── consumer-deployment.yaml
│   └── dashboard-deployment.yaml
│
├── 📁 loadtest/                     # k6 부하 테스트
│   └── k6_collect.js
│
└── 🐳 docker-compose.yml            # Kafka · Redis · Server · Consumer · Dashboard
```

<br />

---

## 🚀 Getting Started

### Prerequisites

```
✅ Docker & Docker Compose
✅ Node.js 20+
✅ Python 3.11+
```

### Quick Start (Docker Compose)

```bash
# 1. 저장소 클론
git clone https://github.com/Lucainr/Click-Lake.git
cd Click-Lake

# 2. 환경변수 설정
cp server/.env.example server/.env
# server/.env에 Databricks / Kafka 설정 입력

# 3. 전체 서비스 실행 (Kafka · Redis · Server · Consumer · Dashboard)
docker compose up --build

# 4. 접속
#    Collector API:  http://localhost:8000
#    API 문서:       http://localhost:8000/docs
#    Dashboard:      http://localhost:5173
```

### SDK 개발 빌드

```bash
npm install
npm run build      # dist/ 생성
npm run typecheck  # 타입 검사
```

### 서버 로컬 실행

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 파이프라인 실행

```bash
cd server
source .venv/bin/activate

# raw → Bronze export
python scripts/export_raw_to_bronze.py

# Databricks Volume 업로드
python scripts/upload_bronze_batches_to_databricks.py

# Bronze · Silver · Gold SQL 전체 갱신
python scripts/run_pipeline.py

# dry-run 확인
python scripts/run_pipeline.py --dry-run
```

<br />

---

## 📊 Data Pipeline

| Layer | 역할 | 위치 |
|-------|------|------|
| **Raw** | SDK 원본 이벤트 JSONL 보존 | `server/data/raw_events_kafka/` |
| **Bronze** | date 파티션 배치, `ingestion_source` 태깅 | Databricks Volume |
| **Silver** | 유효성 검증, `event_id` dedup, invalid 분리 | Databricks SQL |
| **Gold** | 워크스페이스 건강도 · 프로모션 CTR · 캠페인 퍼널 | Databricks SQL |

### Gold 지표 확인

```bash
# Slack slash command
/clicklake health
/clicklake top-ctr clk_live_demo 10
/clicklake funnel clk_live_demo

# REST API
GET /api/gold/dashboard?sdk_key=clk_live_demo
GET /api/gold/health
GET /api/gold/promotion-performance
GET /api/gold/campaign-funnel
```

<br />

---

## 🧪 Load Test

```bash
# 200K 이벤트 시뮬레이션 (API 모드)
cd server
python scripts/simulate_events.py \
  --mode api \
  --events 200000 \
  --days 14 \
  --concurrency 10 \
  --collect-url http://localhost:8000/collect

# k6 부하 테스트
k6 run loadtest/k6_collect.js
```

<br />

---

## 👤 Author

<table>
<tr>
<td align="center" width="20%">
<a href="https://github.com/Lucainr">
<img src="https://github.com/Lucainr.png" width="100px" style="border-radius:50%"/><br />
<b>김형욱 (Luca)</b>
</a><br />
<sub>Backend · Infra · Data</sub><br />
<sub>⚙️ 풀스택 데이터 파이프라인</sub>
</td>
</tr>
</table>

<br />

---

## 📄 License

MIT License © 2026 **HyungWook Kim (Luca)**

<br />

---

<div align="center">

**Built with ❤️ by Luca**

<br />

[⬆️ Back to Top](#click-lake)

</div>
