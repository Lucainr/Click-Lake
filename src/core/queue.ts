import type { EventPayload } from "../types/event"
import { ensureInitialized, getConfig } from "./config"
import { sendBatch } from "./sender"

let queue: EventPayload[] = []
let flushHandle: ReturnType<typeof setInterval> | null = null
let flushing = false

export const initQueue = () => {
  const cfg = ensureInitialized()
  if (flushHandle) clearInterval(flushHandle)
  flushHandle = setInterval(() => {
    void flush()
  }, cfg.flushIntervalMs)
}

export const enqueue = (event: EventPayload) => {
  queue.push(event)
  const cfg = getConfig()
  if (cfg && queue.length >= cfg.batchSize) {
    void flush()
  }
}

export const flush = async () => {
  if (flushing) return
  const cfg = getConfig()
  if (!cfg) return
  if (!queue.length) return
  flushing = true
  const toSend = [...queue]
  const success = await sendBatch(toSend, cfg.sdkKey, cfg.endpoint)
  if (success) {
    queue = []
  }
  flushing = false
}

export const stopQueue = () => {
  if (flushHandle) clearInterval(flushHandle)
  flushHandle = null
}

export const size = () => queue.length

// For tests / debug only
export const getQueueSnapshot = () => [...queue]
