import { track } from "../core/track"

export const addToCart = (payload: Record<string, unknown>) => {
  track("add_to_cart", payload)
}
