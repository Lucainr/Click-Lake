export type EventType =
  | "page_view"
  | "promotion_view"
  | "promotion_click"
  | "product_view"
  | "add_to_cart"

export interface BaseEvent {
  sdk_key: string
  event_id: string
  event_type: EventType
  event_version: number
  event_time: string
  sent_at?: string
  anonymous_id: string
  session_id: string
  user_id?: string | null
  page_url: string
  referrer_url?: string | null
  page_title?: string | null
  page_type?: string | null
  device_type?: string | null
  os_name?: string | null
  browser_name?: string | null
  viewport_width?: number | null
  viewport_height?: number | null
  country?: string | null
  language?: string | null
}

export interface PageViewEvent extends BaseEvent {
  event_type: "page_view"
}

export interface PromotionViewEvent extends BaseEvent {
  event_type: "promotion_view"
  promotion_id: string
  promotion_name: string
  campaign_id: string
  campaign_name?: string
  placement: string
  creative_id?: string
  creative_type?: string
  position_index?: number
}

export interface PromotionClickEvent extends BaseEvent {
  event_type: "promotion_click"
  promotion_id: string
  promotion_name: string
  campaign_id: string
  campaign_name?: string
  placement: string
  creative_id?: string
  creative_type?: string
  position_index?: number
  click_target_url?: string
  click_x?: number
  click_y?: number
}

export interface ProductViewEvent extends BaseEvent {
  event_type: "product_view"
  product_id: string
  product_name?: string
  category_id?: string
  category_name?: string
  source_promotion_id?: string
  source_campaign_id?: string
}

export interface AddToCartEvent extends BaseEvent {
  event_type: "add_to_cart"
  product_id: string
  product_name?: string
  category_id?: string
  category_name?: string
  quantity?: number
  unit_price?: number
  currency?: string
  source_promotion_id?: string
  source_campaign_id?: string
}

export type EventPayload =
  | PageViewEvent
  | PromotionViewEvent
  | PromotionClickEvent
  | ProductViewEvent
  | AddToCartEvent

export interface SDKConfig {
  sdkKey: string
  endpoint: string
  debug?: boolean
  autoPageView?: boolean
  flushIntervalMs?: number
  batchSize?: number
  maxRetries?: number
}

export type PromotionViewInput = Pick<
  PromotionViewEvent,
  "promotion_id" | "promotion_name" | "campaign_id" | "placement"
> &
  Partial<
    Pick<
      PromotionViewEvent,
      "campaign_name" | "creative_id" | "creative_type" | "position_index"
    >
  >

export type PromotionClickInput = Pick<
  PromotionClickEvent,
  "promotion_id" | "promotion_name" | "campaign_id" | "placement"
> &
  Partial<
    Pick<
      PromotionClickEvent,
      | "campaign_name"
      | "creative_id"
      | "creative_type"
      | "position_index"
      | "click_target_url"
      | "click_x"
      | "click_y"
    >
  >

export type ProductViewInput = Pick<ProductViewEvent, "product_id"> &
  Partial<
    Pick<
      ProductViewEvent,
      | "product_name"
      | "category_id"
      | "category_name"
      | "source_promotion_id"
      | "source_campaign_id"
    >
  >

export type AddToCartInput = Pick<AddToCartEvent, "product_id"> &
  Partial<
    Pick<
      AddToCartEvent,
      | "product_name"
      | "category_id"
      | "category_name"
      | "quantity"
      | "unit_price"
      | "currency"
      | "source_promotion_id"
      | "source_campaign_id"
    >
  >
