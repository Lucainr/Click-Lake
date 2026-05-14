# Click Lake Kafka Consumer (Stage 2)

`clicklake.events.raw` topic 메시지를 consume해서 두 가지 sink를 병행 저장할 수 있습니다.

## 동작
- Topic subscribe: `clicklake.events.raw`
- 메시지 형식: `{ received_at, sdk_key, events: [...] }`
- 저장 단위: **event 1건당 JSONL 1줄**
- raw sink 경로(기본): `/data/raw_events_kafka/date=YYYY-MM-DD/events-0001.jsonl`
- bronze direct sink 경로(기본): `/data/bronze_batches_kafka/date=YYYY-MM-DD/bronze_events-0001.jsonl`

## 이유 (event 단위 저장)
- 기존 raw 저장 포맷(`received_at`, `sdk_key`, `event`)과 동일해 downstream 재사용이 쉽습니다.
- 요청 단위 메시지라도 event별 처리/검증/재처리에 유리합니다.
- Bronze direct sink도 event 1건 기준으로 구성하면 Silver/Gold 입력으로 변환하기 쉽습니다.

## 주요 환경변수
- `KAFKA_BOOTSTRAP_SERVERS` (기본: `kafka:9092`)
- `KAFKA_TOPIC_RAW_EVENTS` (기본: `clicklake.events.raw`)
- `KAFKA_CONSUMER_GROUP` (기본: `clicklake-consumer`)
- `KAFKA_AUTO_OFFSET_RESET` (기본: `latest`)
- `KAFKA_ENABLE_RAW_SINK` (기본: `true`)
- `KAFKA_SINK_DIR` (기본: `/data/raw_events_kafka`)
- `SINK_MAX_EVENTS_PER_FILE` (기본: `1000`)
- `KAFKA_ENABLE_BRONZE_DIRECT` (기본: `true`)
- `KAFKA_BRONZE_SINK_DIR` (기본: `/data/bronze_batches_kafka`)
- `KAFKA_BRONZE_MAX_EVENTS_PER_FILE` (기본: `1000`)
