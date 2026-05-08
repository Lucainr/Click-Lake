import type { EventPayload } from "../types/event"
import { ensureInitialized, getConfig } from "./config"
import { sendBatch, sendBatchWithBeacon } from "./sender"
import { log, warn } from "../utils/logger"

let queue: EventPayload[] = []
let flushHandle: ReturnType<typeof setInterval> | null = null
let flushing = false
let lifecycleHandlersBound = false
let beforeUnloadHandler: (() => void) | null = null
let pageHideHandler: (() => void) | null = null
let visibilityHandler: (() => void) | null = null

type FlushReason =
  | "interval"
  | "batch_size"
  | "manual"
  | "beforeunload"
  | "pagehide"
  | "visibility_hidden"

export interface FlushOptions {
  reason?: FlushReason
}

export const initQueue = () => {
  const cfg = ensureInitialized()
  if (flushHandle) clearInterval(flushHandle)
  flushHandle = setInterval(() => {
    void flush({ reason: "interval" })
  }, cfg.flushIntervalMs)
  bindLifecycleHandlers()
}

export const enqueue = (event: EventPayload) => {
  queue.push(event)
  log("queued event", { eventType: event.event_type, queueSize: queue.length })
  const cfg = getConfig()
  if (cfg && queue.length >= cfg.batchSize) {
    void flush({ reason: "batch_size" })
  }
}

export const flush = async (options: FlushOptions = {}): Promise<boolean> => {
  if (flushing) return false
  const cfg = getConfig()
  if (!cfg) return false
  if (!queue.length) return true

  const reason = options.reason ?? "manual"
  flushing = true
  let delivered = 0

  try {
    while (queue.length > 0) {
      const batch = queue.splice(0, Math.min(cfg.batchSize, queue.length))
      log("flush start", {
        reason,
        batchSize: batch.length,
        queueRemaining: queue.length
      })

      const success = await sendBatch(batch, cfg.sdkKey, cfg.endpoint, cfg.maxRetries)
      if (!success) {
        queue = [...batch, ...queue]
        warn("flush aborted after failed batch", {
          reason,
          failedBatchSize: batch.length,
          queueSize: queue.length
        })
        return false
      }

      delivered += batch.length
    }

    log("flush success", { reason, delivered, queueSize: queue.length })
    return true
  } finally {
    flushing = false
  }
}

export const stopQueue = () => {
  if (flushHandle) clearInterval(flushHandle)
  flushHandle = null
  unbindLifecycleHandlers()
}

export const size = () => queue.length

// For tests / debug only
export const getQueueSnapshot = () => [...queue]

const flushOnPageExit = (reason: FlushReason) => {
  const cfg = getConfig()
  if (!cfg || !queue.length) return
  if (flushing) return

  log("unload flush attempt", { reason, queueSize: queue.length })
  const pending = [...queue]
  const beaconQueued = sendBatchWithBeacon(pending, cfg.sdkKey, cfg.endpoint)
  log("sendBeacon available", {
    reason,
    beaconUsed: beaconQueued,
    queueSize: pending.length
  })

  if (beaconQueued) {
    queue = []
    return
  }

  void flush({ reason })
}

const bindLifecycleHandlers = () => {
  if (lifecycleHandlersBound || typeof window === "undefined") return

  beforeUnloadHandler = () => flushOnPageExit("beforeunload")
  pageHideHandler = () => flushOnPageExit("pagehide")
  visibilityHandler = () => {
    if (document.visibilityState === "hidden") {
      flushOnPageExit("visibility_hidden")
    }
  }

  window.addEventListener("beforeunload", beforeUnloadHandler)
  window.addEventListener("pagehide", pageHideHandler)
  document.addEventListener("visibilitychange", visibilityHandler)
  lifecycleHandlersBound = true
}

const unbindLifecycleHandlers = () => {
  if (!lifecycleHandlersBound || typeof window === "undefined") return
  if (beforeUnloadHandler) window.removeEventListener("beforeunload", beforeUnloadHandler)
  if (pageHideHandler) window.removeEventListener("pagehide", pageHideHandler)
  if (visibilityHandler) document.removeEventListener("visibilitychange", visibilityHandler)

  beforeUnloadHandler = null
  pageHideHandler = null
  visibilityHandler = null
  lifecycleHandlersBound = false
}
