export interface HealthRow {
  event_date: string
  sdk_key: string
  raw_event_count: number
  valid_event_count: number
  invalid_event_count: number
  invalid_event_ratio: number
  distinct_sessions: number
  latest_event_time: string
  freshness_minutes: number | null
}

export interface PromotionPerformanceRow {
  event_date: string
  sdk_key: string
  campaign_id: string
  campaign_name: string
  promotion_id: string
  promotion_name: string
  placement: string
  promotion_views: number
  promotion_clicks: number
  ctr: number
  product_views_after_click: number
  add_to_cart_after_click: number
  product_view_rate_after_click: number
  add_to_cart_rate_after_click: number
}

export interface CampaignFunnelRow {
  event_date: string
  sdk_key: string
  campaign_id: string
  campaign_name: string
  promotion_view_sessions: number
  promotion_click_sessions: number
  product_view_sessions: number
  add_to_cart_sessions: number
  view_to_click_rate: number
  click_to_product_view_rate: number
  click_to_add_to_cart_rate: number
}

export interface Column<T> {
  key: keyof T
  label: string
  align?: "left" | "right"
  render?: (value: T[keyof T], row: T) => string
}
