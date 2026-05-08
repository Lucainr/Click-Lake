import { nowIso } from "../utils/time"
import type { EventPayload } from "../types/event"
import { log, warn } from "../utils/logger"

const enrichEvents = (events: EventPayload[]) => events.map((evt) => ({ ...evt, sent_at: nowIso() }))

const makeRequestBody = (events: EventPayload[], sdkKey: string) =>
  JSON.stringify({ sdk_key: sdkKey, events: enrichEvents(events) })

export const sendBatch = async (
  events: EventPayload[],
  sdkKey: string,
  endpoint: string,
  maxRetries = 2
): Promise<boolean> => {
  const body = makeRequestBody(events, sdkKey)

  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body,
        keepalive: true
      })
      if (res.ok) {
        log("flush success", { status: res.status, events: events.length, attempt })
        return true
      }

      warn("collector responded with non-2xx", {
        status: res.status,
        events: events.length,
        attempt
      })
    } catch (err) {
      warn("flush failed", { err, events: events.length, attempt })
    }

    if (attempt < maxRetries) {
      log("retrying flush", { nextAttempt: attempt + 1, events: events.length })
    }
  }

  return false
}

export const sendBatchWithBeacon = (
  events: EventPayload[],
  sdkKey: string,
  endpoint: string
): boolean => {
  if (typeof navigator === "undefined" || typeof navigator.sendBeacon !== "function") {
    return false
  }

  const body = makeRequestBody(events, sdkKey)
  const queued = navigator.sendBeacon(endpoint, new Blob([body], { type: "application/json" }))
  if (queued) {
    log("sendBeacon queued", { events: events.length })
  } else {
    warn("sendBeacon failed to queue", { events: events.length })
  }
  return queued
}
