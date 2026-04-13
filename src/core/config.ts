import type { SDKConfig } from "../types/event"

const defaultConfig = {
  debug: false,
  autoPageView: true,
  flushIntervalMs: 3000,
  batchSize: 5
}

let config: Required<SDKConfig> | null = null

export const setConfig = (input: SDKConfig) => {
  if (!input.sdkKey) throw new Error("sdkKey is required")
  if (!input.endpoint) throw new Error("endpoint is required")

  config = {
    ...defaultConfig,
    ...input,
    debug: input.debug ?? defaultConfig.debug,
    autoPageView: input.autoPageView ?? defaultConfig.autoPageView,
    flushIntervalMs: input.flushIntervalMs ?? defaultConfig.flushIntervalMs,
    batchSize: input.batchSize ?? defaultConfig.batchSize
  }
}

export const getConfig = () => config

export const ensureInitialized = () => {
  if (!config) throw new Error("ClickLake SDK not initialized. Call init() first.")
  return config
}
