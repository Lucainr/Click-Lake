import { nowIso } from "../utils/time"
import type { EventPayload } from "../types/event"
import { log, warn } from "../utils/logger"

export const sendBatch = async (
  events: EventPayload[],
  sdkKey: string,
  endpoint: string
): Promise<boolean> => {
  const enriched = events.map((evt) => ({ ...evt, sent_at: nowIso() }))
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ sdk_key: sdkKey, events: enriched })
    })
    log("flush success", res.status)
    if (!res.ok) {
      warn("collector responded with non-2xx", res.status)
      return false
    }
    return true
  } catch (err) {
    warn("flush failed", err)
    return false
  }
}
