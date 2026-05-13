-- JSON Bronze -> Silver Invalid Events (event_id dedup + idempotency)
-- Source: workspace.clicklake_bronze.events_raw_json

CREATE SCHEMA IF NOT EXISTS workspace.clicklake_silver;

CREATE TABLE IF NOT EXISTS workspace.clicklake_silver.silver_invalid_events_json (
  received_at TIMESTAMP,
  sdk_key STRING,
  event_id STRING,
  event_type STRING,
  event_time STRING,
  session_id STRING,
  page_url STRING,
  raw_event_json STRING,
  error_code STRING,
  error_message STRING,
  validation_stage STRING,
  source_file STRING,
  loaded_at TIMESTAMP,
  detected_at TIMESTAMP
)
USING DELTA;

INSERT OVERWRITE workspace.clicklake_silver.silver_invalid_events_json
WITH parsed AS (
  SELECT
    to_timestamp(received_at) AS received_at,
    trim(coalesce(sdk_key, get_json_object(raw_event_json, '$.sdk_key'))) AS sdk_key,
    trim(coalesce(event_id, get_json_object(raw_event_json, '$.event_id'))) AS event_id,
    lower(trim(coalesce(event_type, get_json_object(raw_event_json, '$.event_type')))) AS event_type,
    trim(coalesce(event_time, get_json_object(raw_event_json, '$.event_time'))) AS event_time,
    to_timestamp(trim(coalesce(event_time, get_json_object(raw_event_json, '$.event_time')))) AS event_time_ts,
    trim(coalesce(session_id, get_json_object(raw_event_json, '$.session_id'))) AS session_id,
    trim(coalesce(page_url, get_json_object(raw_event_json, '$.page_url'))) AS page_url,
    trim(get_json_object(raw_event_json, '$.promotion_id')) AS promotion_id,
    trim(get_json_object(raw_event_json, '$.promotion_name')) AS promotion_name,
    trim(get_json_object(raw_event_json, '$.campaign_id')) AS campaign_id,
    trim(get_json_object(raw_event_json, '$.placement')) AS placement,
    trim(get_json_object(raw_event_json, '$.product_id')) AS product_id,
    raw_event_json,
    source_file,
    to_timestamp(loaded_at) AS loaded_at
  FROM workspace.clicklake_bronze.events_raw_json
),
classified AS (
  SELECT
    *,
    CASE
      WHEN coalesce(sdk_key, '') = '' THEN 'MISSING_SDK_KEY'
      WHEN coalesce(event_id, '') = '' THEN 'MISSING_EVENT_ID'
      WHEN coalesce(event_type, '') = '' THEN 'MISSING_EVENT_TYPE'
      WHEN event_type NOT IN ('page_view', 'promotion_view', 'promotion_click', 'product_view', 'add_to_cart')
        THEN 'INVALID_EVENT_TYPE'
      WHEN coalesce(event_time, '') = '' THEN 'MISSING_EVENT_TIME'
      WHEN event_time_ts IS NULL THEN 'INVALID_EVENT_TIME_FORMAT'
      WHEN coalesce(session_id, '') = '' THEN 'MISSING_SESSION_ID'
      WHEN coalesce(page_url, '') = '' THEN 'MISSING_PAGE_URL'
      WHEN event_type IN ('promotion_view', 'promotion_click')
        AND (
          coalesce(promotion_id, '') = ''
          OR coalesce(promotion_name, '') = ''
          OR coalesce(campaign_id, '') = ''
          OR coalesce(placement, '') = ''
        )
        THEN 'MISSING_PROMOTION_REQUIRED_FIELDS'
      WHEN event_type IN ('product_view', 'add_to_cart')
        AND coalesce(product_id, '') = ''
        THEN 'MISSING_PRODUCT_ID'
      ELSE NULL
    END AS error_code
  FROM parsed
),
ranked_by_event_id AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY event_id
      ORDER BY
        CASE WHEN error_code IS NULL THEN 0 ELSE 1 END ASC,
        loaded_at DESC,
        event_time_ts DESC,
        source_file DESC
    ) AS row_num
  FROM classified
  WHERE coalesce(event_id, '') <> ''
),
dedup_invalid AS (
  -- event_id가 있는 경우:
  -- 1) valid/invalid 충돌 시 valid 우선 (invalid는 제외)
  -- 2) invalid만 존재하면 최신 invalid 1건만 유지
  SELECT
    received_at,
    sdk_key,
    event_id,
    event_type,
    event_time,
    session_id,
    page_url,
    raw_event_json,
    error_code,
    source_file,
    loaded_at
  FROM ranked_by_event_id
  WHERE row_num = 1
    AND error_code IS NOT NULL

  UNION ALL

  -- event_id가 비어있는 invalid는 id 기반 dedup 불가 -> 원본 유지
  SELECT
    received_at,
    sdk_key,
    event_id,
    event_type,
    event_time,
    session_id,
    page_url,
    raw_event_json,
    error_code,
    source_file,
    loaded_at
  FROM classified
  WHERE coalesce(event_id, '') = ''
    AND error_code IS NOT NULL
)
SELECT
  received_at,
  sdk_key,
  event_id,
  event_type,
  event_time,
  session_id,
  page_url,
  raw_event_json,
  error_code,
  CASE
    WHEN error_code = 'MISSING_SDK_KEY' THEN 'sdk_key is required'
    WHEN error_code = 'MISSING_EVENT_ID' THEN 'event_id is required'
    WHEN error_code = 'MISSING_EVENT_TYPE' THEN 'event_type is required'
    WHEN error_code = 'INVALID_EVENT_TYPE' THEN 'event_type must be one of page_view,promotion_view,promotion_click,product_view,add_to_cart'
    WHEN error_code = 'MISSING_EVENT_TIME' THEN 'event_time is required'
    WHEN error_code = 'INVALID_EVENT_TIME_FORMAT' THEN 'event_time must be parseable timestamp'
    WHEN error_code = 'MISSING_SESSION_ID' THEN 'session_id is required'
    WHEN error_code = 'MISSING_PAGE_URL' THEN 'page_url is required'
    WHEN error_code = 'MISSING_PROMOTION_REQUIRED_FIELDS' THEN 'promotion_id,promotion_name,campaign_id,placement are required for promotion events'
    WHEN error_code = 'MISSING_PRODUCT_ID' THEN 'product_id is required for product_view/add_to_cart'
    ELSE 'unknown validation error'
  END AS error_message,
  CASE
    WHEN error_code IN ('MISSING_SDK_KEY', 'MISSING_EVENT_ID', 'MISSING_EVENT_TYPE', 'MISSING_EVENT_TIME', 'MISSING_SESSION_ID', 'MISSING_PAGE_URL')
      THEN 'COMMON_REQUIRED'
    WHEN error_code IN ('INVALID_EVENT_TYPE')
      THEN 'EVENT_TYPE'
    WHEN error_code IN ('INVALID_EVENT_TIME_FORMAT')
      THEN 'COMMON_FORMAT'
    WHEN error_code IN ('MISSING_PROMOTION_REQUIRED_FIELDS', 'MISSING_PRODUCT_ID')
      THEN 'EVENT_SPECIFIC'
    ELSE 'UNKNOWN'
  END AS validation_stage,
  source_file,
  loaded_at,
  current_timestamp() AS detected_at
FROM dedup_invalid;
