-- Click Lake Bronze JSON table (raw event payload preserved)
-- Use explicit casting in COPY INTO to avoid schema merge/type conflicts.

CREATE SCHEMA IF NOT EXISTS workspace.clicklake_bronze;

CREATE TABLE IF NOT EXISTS workspace.clicklake_bronze.events_raw_json (
  received_at STRING,
  sdk_key STRING,
  event_id STRING,
  event_type STRING,
  event_time STRING,
  session_id STRING,
  page_url STRING,
  raw_event_json STRING,
  exported_at STRING,
  export_batch_id STRING,
  source_file STRING,
  loaded_at STRING
)
USING DELTA;

-- If your upload target is /Volumes/workspace/clicklake_bronze/raw_batches:
COPY INTO workspace.clicklake_bronze.events_raw_json
FROM (
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
    CAST(loaded_at AS STRING) AS loaded_at
  FROM '/Volumes/workspace/clicklake_bronze/raw_batches/*.jsonl'
)
FILEFORMAT = JSON
COPY_OPTIONS ('mergeSchema' = 'false');

-- If your upload target is /Volumes/workspace/clicklake_bronze/raw_files, use this instead:
-- COPY INTO workspace.clicklake_bronze.events_raw_json
-- FROM (
--   SELECT
--     CAST(received_at AS STRING) AS received_at,
--     CAST(sdk_key AS STRING) AS sdk_key,
--     CAST(event_id AS STRING) AS event_id,
--     CAST(event_type AS STRING) AS event_type,
--     CAST(event_time AS STRING) AS event_time,
--     CAST(session_id AS STRING) AS session_id,
--     CAST(page_url AS STRING) AS page_url,
--     CAST(raw_event_json AS STRING) AS raw_event_json,
--     CAST(exported_at AS STRING) AS exported_at,
--     CAST(export_batch_id AS STRING) AS export_batch_id,
--     CAST(source_file AS STRING) AS source_file,
--     CAST(loaded_at AS STRING) AS loaded_at
--   FROM '/Volumes/workspace/clicklake_bronze/raw_files/*.jsonl'
-- )
-- FILEFORMAT = JSON
-- COPY_OPTIONS ('mergeSchema' = 'false');
