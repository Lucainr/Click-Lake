import type { EventPayload } from "../types/event"

const requiredByType: Record<string, string[]> = {
  promotion_view: ["promotion_id", "promotion_name", "campaign_id", "placement"],
  promotion_click: ["promotion_id", "promotion_name", "campaign_id", "placement"],
  product_view: ["product_id"],
  add_to_cart: ["product_id"]
}

export const validateEvent = (event: EventPayload): string[] => {
  const errors: string[] = []
  if (!event.sdk_key) errors.push("sdk_key is required")
  if (!event.event_type) errors.push("event_type is required")
  if (!event.event_time) errors.push("event_time is required")
  if (!event.session_id) errors.push("session_id is required")
  if (!event.page_url) errors.push("page_url is required")

  const fields = requiredByType[event.event_type]
  if (fields) {
    const record = event as unknown as Record<string, unknown>
    fields.forEach((field) => {
      const value = record[field]
      if (value === undefined || value === null || value === "") {
        errors.push(`${event.event_type}: ${field} is required`)
      }
    })
  }
  return errors
}

export const isSupportedEventType = (type: string) =>
  [
    "page_view",
    "promotion_view",
    "promotion_click",
    "product_view",
    "add_to_cart"
  ].includes(type)
