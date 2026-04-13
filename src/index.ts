import { init } from "./core/init"
import { track } from "./core/track"
import { flush } from "./core/queue"
import { pageView } from "./events/pageView"
import { promotionView } from "./events/promotionView"
import { promotionClick } from "./events/promotionClick"
import { productView } from "./events/productView"
import { addToCart } from "./events/addToCart"
import { setUserId } from "./context/identity"

export const ClickLake = {
  init,
  track,
  pageView,
  promotionView,
  promotionClick,
  productView,
  addToCart,
  identify: (userId: string | null) => setUserId(userId),
  flush
}

export type { SDKConfig, EventPayload, EventType } from "./types/event"
