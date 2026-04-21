-- JSON Bronze -> Silver Valid Events
-- Source: workspace.clicklake_bronze.events_raw_json

CREATE SCHEMA IF NOT EXISTS workspace.clicklake_silver;

CREATE TABLE IF NOT EXISTS workspace.clicklake_silver.silver_events_json (
  received_at TIMESTAMP,
  event_date DATE,
  sdk_key STRING,
  event_id STRING,
  event_type STRING,
  event_time TIMESTAMP,
  session_id STRING,
  anonymous_id STRING,
  user_id STRING,
  page_url STRING,
  referrer_url STRING,
  page_title STRING,
  page_type STRING,
  device_type STRING,
  os_name STRING,
  browser_name STRING,
  viewport_width INT,
  viewport_height INT,
  country STRING,
  language STRING,
  promotion_id STRING,
  promotion_name STRING,
  campaign_id STRING,
  campaign_name STRING,
  placement STRING,
  creative_id STRING,
  creative_type STRING,
  position_index INT,
  click_target_url STRING,
  click_x INT,
  click_y INT,
  product_id STRING,
  product_name STRING,
  category_id STRING,
  category_name STRING,
  quantity INT,
  unit_price DECIMAL(18,2),
  currency STRING,
  source_promotion_id STRING,
  source_campaign_id STRING,
  raw_event_json STRING,
  export_batch_id STRING,
  source_file STRING,
  loaded_at TIMESTAMP,
  validated_at TIMESTAMP
)
USING DELTA;

INSERT OVERWRITE workspace.clicklake_silver.silver_events_json
WITH parsed AS (
  SELECT
    to_timestamp(received_at) AS received_at,
    trim(coalesce(sdk_key, get_json_object(raw_event_json, '$.sdk_key'))) AS sdk_key,
    trim(coalesce(event_id, get_json_object(raw_event_json, '$.event_id'))) AS event_id,
    lower(trim(coalesce(event_type, get_json_object(raw_event_json, '$.event_type')))) AS event_type,
    trim(coalesce(event_time, get_json_object(raw_event_json, '$.event_time'))) AS event_time_raw,
    to_timestamp(trim(coalesce(event_time, get_json_object(raw_event_json, '$.event_time')))) AS event_time,
    trim(coalesce(session_id, get_json_object(raw_event_json, '$.session_id'))) AS session_id,
    trim(coalesce(page_url, get_json_object(raw_event_json, '$.page_url'))) AS page_url,
    trim(get_json_object(raw_event_json, '$.anonymous_id')) AS anonymous_id,
    trim(get_json_object(raw_event_json, '$.user_id')) AS user_id,
    trim(get_json_object(raw_event_json, '$.referrer_url')) AS referrer_url,
    trim(get_json_object(raw_event_json, '$.page_title')) AS page_title,
    trim(get_json_object(raw_event_json, '$.page_type')) AS page_type,
    trim(get_json_object(raw_event_json, '$.device_type')) AS device_type,
    trim(get_json_object(raw_event_json, '$.os_name')) AS os_name,
    trim(get_json_object(raw_event_json, '$.browser_name')) AS browser_name,
    CAST(get_json_object(raw_event_json, '$.viewport_width') AS INT) AS viewport_width,
    CAST(get_json_object(raw_event_json, '$.viewport_height') AS INT) AS viewport_height,
    trim(get_json_object(raw_event_json, '$.country')) AS country,
    trim(get_json_object(raw_event_json, '$.language')) AS language,
    trim(get_json_object(raw_event_json, '$.promotion_id')) AS promotion_id,
    trim(get_json_object(raw_event_json, '$.promotion_name')) AS promotion_name,
    trim(get_json_object(raw_event_json, '$.campaign_id')) AS campaign_id,
    trim(get_json_object(raw_event_json, '$.campaign_name')) AS campaign_name,
    trim(get_json_object(raw_event_json, '$.placement')) AS placement,
    trim(get_json_object(raw_event_json, '$.creative_id')) AS creative_id,
    trim(get_json_object(raw_event_json, '$.creative_type')) AS creative_type,
    CAST(get_json_object(raw_event_json, '$.position_index') AS INT) AS position_index,
    trim(get_json_object(raw_event_json, '$.click_target_url')) AS click_target_url,
    CAST(get_json_object(raw_event_json, '$.click_x') AS INT) AS click_x,
    CAST(get_json_object(raw_event_json, '$.click_y') AS INT) AS click_y,
    trim(get_json_object(raw_event_json, '$.product_id')) AS product_id,
    trim(get_json_object(raw_event_json, '$.product_name')) AS product_name,
    trim(get_json_object(raw_event_json, '$.category_id')) AS category_id,
    trim(get_json_object(raw_event_json, '$.category_name')) AS category_name,
    CAST(get_json_object(raw_event_json, '$.quantity') AS INT) AS quantity,
    CAST(get_json_object(raw_event_json, '$.unit_price') AS DECIMAL(18,2)) AS unit_price,
    trim(get_json_object(raw_event_json, '$.currency')) AS currency,
    trim(get_json_object(raw_event_json, '$.source_promotion_id')) AS source_promotion_id,
    trim(get_json_object(raw_event_json, '$.source_campaign_id')) AS source_campaign_id,
    raw_event_json,
    export_batch_id,
    source_file,
    to_timestamp(loaded_at) AS loaded_at
  FROM workspace.clicklake_bronze.events_raw_json
),
validated AS (
  SELECT
    *,
    CASE
      WHEN coalesce(sdk_key, '') = '' THEN 'MISSING_SDK_KEY'
      WHEN coalesce(event_id, '') = '' THEN 'MISSING_EVENT_ID'
      WHEN coalesce(event_type, '') = '' THEN 'MISSING_EVENT_TYPE'
      WHEN event_type NOT IN ('page_view', 'promotion_view', 'promotion_click', 'product_view', 'add_to_cart')
        THEN 'INVALID_EVENT_TYPE'
      WHEN coalesce(event_time_raw, '') = '' THEN 'MISSING_EVENT_TIME'
      WHEN event_time IS NULL THEN 'INVALID_EVENT_TIME_FORMAT'
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
)
SELECT
  received_at,
  CAST(event_time AS DATE) AS event_date,
  sdk_key,
  event_id,
  event_type,
  event_time,
  session_id,
  anonymous_id,
  user_id,
  page_url,
  referrer_url,
  page_title,
  page_type,
  device_type,
  os_name,
  browser_name,
  viewport_width,
  viewport_height,
  country,
  language,
  promotion_id,
  promotion_name,
  campaign_id,
  campaign_name,
  placement,
  creative_id,
  creative_type,
  position_index,
  click_target_url,
  click_x,
  click_y,
  product_id,
  product_name,
  category_id,
  category_name,
  quantity,
  unit_price,
  currency,
  source_promotion_id,
  source_campaign_id,
  raw_event_json,
  export_batch_id,
  source_file,
  loaded_at,
  current_timestamp() AS validated_at
FROM validated
WHERE error_code IS NULL;
