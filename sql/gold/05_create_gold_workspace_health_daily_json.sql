-- JSON Bronze/Silver -> Gold Workspace Health (Daily)
-- Source tables:
--   workspace.clicklake_bronze.events_raw_json
--   workspace.clicklake_silver.silver_events_json
--   workspace.clicklake_silver.silver_invalid_events_json

CREATE SCHEMA IF NOT EXISTS workspace.clicklake_gold;

CREATE TABLE IF NOT EXISTS workspace.clicklake_gold.gold_workspace_health_daily_json (
  event_date DATE,
  sdk_key STRING,
  raw_event_count BIGINT,
  valid_event_count BIGINT,
  invalid_event_count BIGINT,
  invalid_event_ratio DECIMAL(10,4),
  distinct_sessions BIGINT,
  latest_event_time TIMESTAMP,
  latest_loaded_at TIMESTAMP,
  freshness_minutes INT,
  last_updated_at TIMESTAMP
)
USING DELTA;

INSERT OVERWRITE workspace.clicklake_gold.gold_workspace_health_daily_json
WITH bronze_base AS (
  SELECT
    COALESCE(CAST(to_timestamp(event_time) AS DATE), CAST(to_timestamp(received_at) AS DATE)) AS event_date,
    trim(sdk_key) AS sdk_key,
    to_timestamp(event_time) AS event_time_ts,
    to_timestamp(loaded_at) AS loaded_at_ts
  FROM workspace.clicklake_bronze.events_raw_json
  WHERE coalesce(trim(sdk_key), '') <> ''
),
raw_agg AS (
  SELECT
    event_date,
    sdk_key,
    COUNT(*) AS raw_event_count,
    MAX(event_time_ts) AS latest_event_time,
    MAX(loaded_at_ts) AS latest_loaded_at
  FROM bronze_base
  WHERE event_date IS NOT NULL
  GROUP BY event_date, sdk_key
),
valid_agg AS (
  SELECT
    event_date,
    trim(sdk_key) AS sdk_key,
    COUNT(*) AS valid_event_count,
    MAX(event_time) AS latest_event_time,
    MAX(loaded_at) AS latest_loaded_at
  FROM workspace.clicklake_silver.silver_events_json
  WHERE event_date IS NOT NULL
    AND coalesce(trim(sdk_key), '') <> ''
  GROUP BY event_date, trim(sdk_key)
),
invalid_agg AS (
  SELECT
    COALESCE(CAST(to_timestamp(event_time) AS DATE), CAST(received_at AS DATE)) AS event_date,
    trim(sdk_key) AS sdk_key,
    COUNT(*) AS invalid_event_count
  FROM workspace.clicklake_silver.silver_invalid_events_json
  WHERE coalesce(trim(sdk_key), '') <> ''
  GROUP BY COALESCE(CAST(to_timestamp(event_time) AS DATE), CAST(received_at AS DATE)), trim(sdk_key)
),
session_agg AS (
  SELECT
    event_date,
    trim(sdk_key) AS sdk_key,
    COUNT(DISTINCT session_id) AS distinct_sessions
  FROM workspace.clicklake_silver.silver_events_json
  WHERE event_date IS NOT NULL
    AND coalesce(trim(sdk_key), '') <> ''
  GROUP BY event_date, trim(sdk_key)
),
all_keys AS (
  SELECT event_date, sdk_key FROM raw_agg
  UNION
  SELECT event_date, sdk_key FROM valid_agg
  UNION
  SELECT event_date, sdk_key FROM invalid_agg
)
SELECT
  k.event_date,
  k.sdk_key,
  COALESCE(r.raw_event_count, 0) AS raw_event_count,
  COALESCE(v.valid_event_count, 0) AS valid_event_count,
  COALESCE(i.invalid_event_count, 0) AS invalid_event_count,
  ROUND(
    CASE
      WHEN COALESCE(r.raw_event_count, 0) = 0 THEN 0
      ELSE COALESCE(i.invalid_event_count, 0) / COALESCE(r.raw_event_count, 0)
    END,
    4
  ) AS invalid_event_ratio,
  COALESCE(s.distinct_sessions, 0) AS distinct_sessions,
  COALESCE(r.latest_event_time, v.latest_event_time) AS latest_event_time,
  COALESCE(r.latest_loaded_at, v.latest_loaded_at) AS latest_loaded_at,
  CASE
    WHEN COALESCE(r.latest_event_time, v.latest_event_time) IS NULL
      OR COALESCE(r.latest_loaded_at, v.latest_loaded_at) IS NULL
      THEN CAST(NULL AS INT)
    ELSE CAST(
      (unix_timestamp(COALESCE(r.latest_loaded_at, v.latest_loaded_at))
      - unix_timestamp(COALESCE(r.latest_event_time, v.latest_event_time))) / 60
      AS INT
    )
  END AS freshness_minutes,
  current_timestamp() AS last_updated_at
FROM all_keys k
LEFT JOIN raw_agg r
  ON k.event_date = r.event_date
 AND k.sdk_key = r.sdk_key
LEFT JOIN valid_agg v
  ON k.event_date = v.event_date
 AND k.sdk_key = v.sdk_key
LEFT JOIN invalid_agg i
  ON k.event_date = i.event_date
 AND k.sdk_key = i.sdk_key
LEFT JOIN session_agg s
  ON k.event_date = s.event_date
 AND k.sdk_key = s.sdk_key;
