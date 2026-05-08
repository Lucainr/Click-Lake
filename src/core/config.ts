import type { SDKConfig } from "../types/event"

const defaultConfig = {
  debug: false,
  autoPageView: true,
  flushIntervalMs: 3000,
  batchSize: 5,
  maxRetries: 2
}

let config: Required<SDKConfig> | null = null

export const setConfig = (input: SDKConfig) => {
  if (!input.sdkKey) throw new Error("sdkKey is required")
  if (!input.endpoint) throw new Error("endpoint is required")
  if (input.batchSize !== undefined && input.batchSize < 1) {
    throw new Error("batchSize must be >= 1")
  }
  if (input.flushIntervalMs !== undefined && input.flushIntervalMs < 1) {
    throw new Error("flushIntervalMs must be >= 1")
  }
  if (input.maxRetries !== undefined && input.maxRetries < 0) {
    throw new Error("maxRetries must be >= 0")
  }

  config = {
    ...defaultConfig,
    ...input,
    debug: input.debug ?? defaultConfig.debug,
    autoPageView: input.autoPageView ?? defaultConfig.autoPageView,
    flushIntervalMs: input.flushIntervalMs ?? defaultConfig.flushIntervalMs,
    batchSize: input.batchSize ?? defaultConfig.batchSize,
    maxRetries: input.maxRetries ?? defaultConfig.maxRetries
  }
}

export const getConfig = () => config

export const ensureInitialized = () => {
  if (!config) throw new Error("ClickLake SDK not initialized. Call init() first.")
  return config
}
