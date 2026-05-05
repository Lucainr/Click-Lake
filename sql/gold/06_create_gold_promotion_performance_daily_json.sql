-- Silver JSON -> Gold Promotion Performance (Daily)
-- Source table:
--   workspace.clicklake_silver.silver_events_json

CREATE SCHEMA IF NOT EXISTS workspace.clicklake_gold;

CREATE TABLE IF NOT EXISTS workspace.clicklake_gold.gold_promotion_performance_daily_json (
  event_date DATE,
  sdk_key STRING,
  campaign_id STRING,
  campaign_name STRING,
  promotion_id STRING,
  promotion_name STRING,
  placement STRING,
  device_type STRING,
  promotion_views BIGINT,
  promotion_clicks BIGINT,
  ctr DECIMAL(10,4),
  unique_view_sessions BIGINT,
  unique_click_sessions BIGINT,
  product_views_after_click BIGINT,
  add_to_cart_after_click BIGINT,
  product_view_rate_after_click DECIMAL(10,4),
  add_to_cart_rate_after_click DECIMAL(10,4),
  last_updated_at TIMESTAMP
)
USING DELTA;

INSERT OVERWRITE workspace.clicklake_gold.gold_promotion_performance_daily_json
WITH base AS (
  SELECT
    event_date,
    trim(sdk_key) AS sdk_key,
    event_type,
    trim(session_id) AS session_id,
    trim(campaign_id) AS campaign_id,
    trim(campaign_name) AS campaign_name,
    trim(promotion_id) AS promotion_id,
    trim(promotion_name) AS promotion_name,
    coalesce(nullif(trim(placement), ''), '(unknown)') AS placement,
    coalesce(nullif(trim(device_type), ''), '(unknown)') AS device_type,
    trim(source_campaign_id) AS source_campaign_id,
    trim(source_promotion_id) AS source_promotion_id
  FROM workspace.clicklake_silver.silver_events_json
  WHERE event_type IN ('promotion_view', 'promotion_click', 'product_view', 'add_to_cart')
    AND event_date IS NOT NULL
    AND coalesce(trim(sdk_key), '') <> ''
),
promotion_agg AS (
  SELECT
    event_date,
    sdk_key,
    campaign_id,
    campaign_name,
    promotion_id,
    promotion_name,
    placement,
    device_type,
    COUNT(CASE WHEN event_type = 'promotion_view' THEN 1 END) AS promotion_views,
    COUNT(CASE WHEN event_type = 'promotion_click' THEN 1 END) AS promotion_clicks,
    COUNT(DISTINCT CASE WHEN event_type = 'promotion_view' THEN session_id END) AS unique_view_sessions,
    COUNT(DISTINCT CASE WHEN event_type = 'promotion_click' THEN session_id END) AS unique_click_sessions
  FROM base
  WHERE event_type IN ('promotion_view', 'promotion_click')
    AND coalesce(campaign_id, '') <> ''
    AND coalesce(promotion_id, '') <> ''
  GROUP BY
    event_date,
    sdk_key,
    campaign_id,
    campaign_name,
    promotion_id,
    promotion_name,
    placement,
    device_type
),
post_click_agg AS (
  SELECT
    event_date,
    sdk_key,
    source_campaign_id AS campaign_id,
    source_promotion_id AS promotion_id,
    device_type,
    COUNT(CASE WHEN event_type = 'product_view' THEN 1 END) AS product_views_after_click,
    COUNT(CASE WHEN event_type = 'add_to_cart' THEN 1 END) AS add_to_cart_after_click
  FROM base
  WHERE event_type IN ('product_view', 'add_to_cart')
    AND coalesce(source_campaign_id, '') <> ''
    AND coalesce(source_promotion_id, '') <> ''
  GROUP BY
    event_date,
    sdk_key,
    source_campaign_id,
    source_promotion_id,
    device_type
),
all_keys AS (
  SELECT
    event_date,
    sdk_key,
    campaign_id,
    campaign_name,
    promotion_id,
    promotion_name,
    placement,
    device_type
  FROM promotion_agg

  UNION

  SELECT
    p.event_date,
    p.sdk_key,
    p.campaign_id,
    CAST(NULL AS STRING) AS campaign_name,
    p.promotion_id,
    CAST(NULL AS STRING) AS promotion_name,
    CAST(NULL AS STRING) AS placement,
    p.device_type
  FROM post_click_agg p
)
SELECT
  k.event_date,
  k.sdk_key,
  k.campaign_id,
  coalesce(k.campaign_name, pa.campaign_name) AS campaign_name,
  k.promotion_id,
  coalesce(k.promotion_name, pa.promotion_name) AS promotion_name,
  coalesce(k.placement, pa.placement) AS placement,
  k.device_type,
  coalesce(pa.promotion_views, 0) AS promotion_views,
  coalesce(pa.promotion_clicks, 0) AS promotion_clicks,
  ROUND(
    CASE
      WHEN coalesce(pa.promotion_views, 0) = 0 THEN 0
      ELSE coalesce(pa.promotion_clicks, 0) / coalesce(pa.promotion_views, 0)
    END,
    4
  ) AS ctr,
  coalesce(pa.unique_view_sessions, 0) AS unique_view_sessions,
  coalesce(pa.unique_click_sessions, 0) AS unique_click_sessions,
  coalesce(pc.product_views_after_click, 0) AS product_views_after_click,
  coalesce(pc.add_to_cart_after_click, 0) AS add_to_cart_after_click,
  ROUND(
    CASE
      WHEN coalesce(pa.promotion_clicks, 0) = 0 THEN 0
      ELSE coalesce(pc.product_views_after_click, 0) / coalesce(pa.promotion_clicks, 0)
    END,
    4
  ) AS product_view_rate_after_click,
  ROUND(
    CASE
      WHEN coalesce(pa.promotion_clicks, 0) = 0 THEN 0
      ELSE coalesce(pc.add_to_cart_after_click, 0) / coalesce(pa.promotion_clicks, 0)
    END,
    4
  ) AS add_to_cart_rate_after_click,
  current_timestamp() AS last_updated_at
FROM all_keys k
LEFT JOIN promotion_agg pa
  ON k.event_date = pa.event_date
 AND k.sdk_key = pa.sdk_key
 AND k.campaign_id = pa.campaign_id
 AND k.promotion_id = pa.promotion_id
 AND coalesce(k.placement, '') = coalesce(pa.placement, '')
 AND coalesce(k.device_type, '') = coalesce(pa.device_type, '')
LEFT JOIN post_click_agg pc
  ON k.event_date = pc.event_date
 AND k.sdk_key = pc.sdk_key
 AND k.campaign_id = pc.campaign_id
 AND k.promotion_id = pc.promotion_id
 AND coalesce(k.device_type, '') = coalesce(pc.device_type, '');
