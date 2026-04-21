import { track } from "../core/track"
import type { PromotionViewInput } from "../types/event"

export const promotionView = (payload: PromotionViewInput) => {
  track("promotion_view", payload)
}
