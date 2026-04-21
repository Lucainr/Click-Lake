import { track } from "../core/track"
import type { PromotionClickInput } from "../types/event"

export const promotionClick = (payload: PromotionClickInput) => {
  track("promotion_click", payload)
}
