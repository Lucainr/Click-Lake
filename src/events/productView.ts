import { track } from "../core/track"
import type { ProductViewInput } from "../types/event"

export const productView = (payload: ProductViewInput) => {
  track("product_view", payload)
}
