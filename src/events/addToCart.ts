import { track } from "../core/track"
import type { AddToCartInput } from "../types/event"

export const addToCart = (payload: AddToCartInput) => {
  track("add_to_cart", payload)
}
