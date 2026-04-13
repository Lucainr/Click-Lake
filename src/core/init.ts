import type { SDKConfig } from "../types/event"
import { setConfig, ensureInitialized } from "./config"
import { initQueue } from "./queue"
import { log } from "../utils/logger"
import { track } from "./track"
import { getSessionId } from "../context/session"
import { getAnonymousId } from "../context/identity"

export const init = (config: SDKConfig) => {
  setConfig(config)
  const cfg = ensureInitialized()

  // 준비 단계에서 식별자 생성/저장
  getSessionId()
  getAnonymousId()

  initQueue()
  log("init", cfg)
  if (cfg.autoPageView) {
    track("page_view")
  }
}
