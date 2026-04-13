import { track } from "../core/track"

export const promotionView = (payload: Record<string, unknown>) => {
  track("promotion_view", payload)
}
