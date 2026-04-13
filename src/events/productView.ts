import { track } from "../core/track"

export const productView = (payload: Record<string, unknown>) => {
  track("product_view", payload)
}
