-- Click Lake Bronze JSON table (raw event payload preserved)
-- Adjust catalog/schema names and source path to your Databricks environment.

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

-- Example load: export script output JSONL -> Bronze table
-- If your upload target is /Volumes/workspace/clicklake_bronze/raw_files:
COPY INTO workspace.clicklake_bronze.events_raw_json
FROM '/Volumes/workspace/clicklake_bronze/raw_files/*.jsonl'
FILEFORMAT = JSON
FORMAT_OPTIONS ('multiLine' = 'false')
COPY_OPTIONS ('mergeSchema' = 'true');

-- If your upload target is /Volumes/workspace/clicklake_bronze/raw_batches:
-- COPY INTO workspace.clicklake_bronze.events_raw_json
-- FROM '/Volumes/workspace/clicklake_bronze/raw_batches/*.jsonl'
-- FILEFORMAT = JSON
-- FORMAT_OPTIONS ('multiLine' = 'false')
-- COPY_OPTIONS ('mergeSchema' = 'true');
