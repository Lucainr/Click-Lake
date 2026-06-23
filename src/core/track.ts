import { getAnonymousId, getUserId } from "../context/identity"
import { getDeviceContext } from "../context/device"
import { getPageContext } from "../context/page"
import { getSessionId } from "../context/session"
import type { BaseEvent, EventPayload, EventType } from "../types/event"
import { validateEvent, isSupportedEventType } from "../validation/validateEvent"
import { makeId } from "../utils/uuid"
import { nowIso } from "../utils/time"
import { enqueue } from "./queue"
import { ensureInitialized } from "./config"
import { log, warn } from "../utils/logger"

export const track = (eventType: EventType, properties: Record<string, unknown> = {}) => {
  const cfg = ensureInitialized()

  if (!isSupportedEventType(eventType)) {
    warn(`unsupported event_type: ${eventType}`)
    return
  }

  const page = getPageContext()
  const device = getDeviceContext()

  const base: BaseEvent = {
    sdk_key: cfg.sdkKey,
    event_id: makeId("evt"),
    event_type: eventType,
    event_version: 1,
    event_time: nowIso(),
    anonymous_id: getAnonymousId(),
    session_id: getSessionId(),
    user_id: getUserId(),
    page_url: page.page_url,
    referrer_url: page.referrer_url,
    page_title: page.page_title,
    page_type: page.page_type,
    device_type: device.device_type,
    os_name: device.os_name,
    browser_name: device.browser_name,
    viewport_width: device.viewport_width,
    viewport_height: device.viewport_height,
    country: device.country,
    language: device.language
  }

  const payload = { ...base, ...properties, event_type: eventType } as EventPayload

  const errors = validateEvent(payload)
  if (errors.length) {
    warn("validation failed", errors)
    cfg.onError?.(errors, eventType)
    return
  }

  log("track", eventType, payload)
  enqueue(payload)
}
