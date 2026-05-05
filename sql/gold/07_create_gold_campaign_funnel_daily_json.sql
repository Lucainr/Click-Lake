-- Silver JSON -> Gold Campaign Funnel (Daily, session-based)
-- Source table:
--   workspace.clicklake_silver.silver_events_json

CREATE SCHEMA IF NOT EXISTS workspace.clicklake_gold;

CREATE TABLE IF NOT EXISTS workspace.clicklake_gold.gold_campaign_funnel_daily_json (
  event_date DATE,
  sdk_key STRING,
  campaign_id STRING,
  campaign_name STRING,
  promotion_view_sessions BIGINT,
  promotion_click_sessions BIGINT,
  product_view_sessions BIGINT,
  add_to_cart_sessions BIGINT,
  view_to_click_rate DECIMAL(10,4),
  click_to_product_view_rate DECIMAL(10,4),
  click_to_add_to_cart_rate DECIMAL(10,4),
  last_updated_at TIMESTAMP
)
USING DELTA;

INSERT OVERWRITE workspace.clicklake_gold.gold_campaign_funnel_daily_json
WITH base AS (
  SELECT
    event_date,
    trim(sdk_key) AS sdk_key,
    trim(session_id) AS session_id,
    lower(trim(event_type)) AS event_type,
    coalesce(nullif(trim(campaign_id), ''), nullif(trim(source_campaign_id), '')) AS campaign_id_norm,
    nullif(trim(campaign_name), '') AS campaign_name_norm
  FROM workspace.clicklake_silver.silver_events_json
  WHERE event_type IN ('promotion_view', 'promotion_click', 'product_view', 'add_to_cart')
    AND event_date IS NOT NULL
    AND coalesce(trim(sdk_key), '') <> ''
    AND coalesce(trim(session_id), '') <> ''
),
campaign_name_map AS (
  SELECT
    event_date,
    sdk_key,
    campaign_id_norm AS campaign_id,
    max(campaign_name_norm) AS campaign_name
  FROM base
  WHERE campaign_id_norm IS NOT NULL
    AND campaign_name_norm IS NOT NULL
  GROUP BY event_date, sdk_key, campaign_id_norm
),
session_flags AS (
  SELECT
    event_date,
    sdk_key,
    campaign_id_norm AS campaign_id,
    session_id,
    max(CASE WHEN event_type = 'promotion_view' THEN 1 ELSE 0 END) AS has_promotion_view,
    max(CASE WHEN event_type = 'promotion_click' THEN 1 ELSE 0 END) AS has_promotion_click,
    max(CASE WHEN event_type = 'product_view' THEN 1 ELSE 0 END) AS has_product_view,
    max(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END) AS has_add_to_cart
  FROM base
  WHERE campaign_id_norm IS NOT NULL
  GROUP BY event_date, sdk_key, campaign_id_norm, session_id
),
campaign_agg AS (
  SELECT
    event_date,
    sdk_key,
    campaign_id,
    sum(has_promotion_view) AS promotion_view_sessions,
    sum(has_promotion_click) AS promotion_click_sessions,
    sum(has_product_view) AS product_view_sessions,
    sum(has_add_to_cart) AS add_to_cart_sessions
  FROM session_flags
  GROUP BY event_date, sdk_key, campaign_id
)
SELECT
  a.event_date,
  a.sdk_key,
  a.campaign_id,
  coalesce(m.campaign_name, '(unknown)') AS campaign_name,
  a.promotion_view_sessions,
  a.promotion_click_sessions,
  a.product_view_sessions,
  a.add_to_cart_sessions,
  ROUND(
    CASE
      WHEN a.promotion_view_sessions = 0 THEN 0
      ELSE a.promotion_click_sessions / a.promotion_view_sessions
    END,
    4
  ) AS view_to_click_rate,
  ROUND(
    CASE
      WHEN a.promotion_click_sessions = 0 THEN 0
      ELSE a.product_view_sessions / a.promotion_click_sessions
    END,
    4
  ) AS click_to_product_view_rate,
  ROUND(
    CASE
      WHEN a.promotion_click_sessions = 0 THEN 0
      ELSE a.add_to_cart_sessions / a.promotion_click_sessions
    END,
    4
  ) AS click_to_add_to_cart_rate,
  current_timestamp() AS last_updated_at
FROM campaign_agg a
LEFT JOIN campaign_name_map m
  ON a.event_date = m.event_date
 AND a.sdk_key = m.sdk_key
 AND a.campaign_id = m.campaign_id;
