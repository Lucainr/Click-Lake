import { track } from "../core/track"

export const promotionClick = (payload: Record<string, unknown>) => {
  track("promotion_click", payload)
}
