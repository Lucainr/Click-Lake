-- Click Lake Bronze JSON table (raw event payload preserved)
-- direct + kafka 경로를 함께 읽어 Bronze 테이블을 재구성합니다.
--
-- source paths
--  - /Volumes/workspace/clicklake_bronze/raw_batches/direct/*.jsonl
--  - /Volumes/workspace/clicklake_bronze/raw_batches/kafka/date=*/bronze_events-*.jsonl
--
-- NOTE:
-- - 이 스크립트는 COPY INTO 대신 CREATE OR REPLACE TABLE AS SELECT(CTAS) 방식입니다.
-- - 실행할 때마다 대상 테이블을 source 파일 기준으로 전체 재생성합니다.

CREATE SCHEMA IF NOT EXISTS workspace.clicklake_bronze;

CREATE OR REPLACE TABLE workspace.clicklake_bronze.events_raw_json
USING DELTA
AS
WITH direct_source AS (
  SELECT
    CAST(received_at AS STRING) AS received_at,
    CAST(sdk_key AS STRING) AS sdk_key,
    CAST(event_id AS STRING) AS event_id,
    CAST(event_type AS STRING) AS event_type,
    CAST(event_time AS STRING) AS event_time,
    CAST(session_id AS STRING) AS session_id,
    CAST(page_url AS STRING) AS page_url,
    CAST(raw_event_json AS STRING) AS raw_event_json,
    CAST(exported_at AS STRING) AS exported_at,
    CAST(export_batch_id AS STRING) AS export_batch_id,
    CAST(source_file AS STRING) AS source_file,
    CAST(COALESCE(ingestion_source, 'direct_raw') AS STRING) AS ingestion_source,
    CAST(loaded_at AS STRING) AS loaded_at
  FROM read_files(
    '/Volumes/workspace/clicklake_bronze/raw_batches/direct/*.jsonl',
    format => 'json',
    ignoreMissingFiles => true
  )
),
kafka_source AS (
  SELECT
    CAST(received_at AS STRING) AS received_at,
    CAST(sdk_key AS STRING) AS sdk_key,
    CAST(event_id AS STRING) AS event_id,
    CAST(event_type AS STRING) AS event_type,
    CAST(event_time AS STRING) AS event_time,
    CAST(session_id AS STRING) AS session_id,
    CAST(page_url AS STRING) AS page_url,
    CAST(raw_event_json AS STRING) AS raw_event_json,
    CAST(exported_at AS STRING) AS exported_at,
    CAST(export_batch_id AS STRING) AS export_batch_id,
    CAST(source_file AS STRING) AS source_file,
    CAST(COALESCE(ingestion_source, 'kafka_consumer_direct') AS STRING) AS ingestion_source,
    CAST(loaded_at AS STRING) AS loaded_at
  FROM read_files(
    '/Volumes/workspace/clicklake_bronze/raw_batches/kafka/date=*/bronze_events-*.jsonl',
    format => 'json',
    ignoreMissingFiles => true
  )
)
SELECT * FROM direct_source
UNION ALL
SELECT * FROM kafka_source;
