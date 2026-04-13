import { getConfig } from "../core/config"

const safeConsole = typeof console !== "undefined" ? console : null

export const log = (...args: unknown[]) => {
  if (!getConfig()?.debug) return
  safeConsole?.log("[ClickLake]", ...args)
}

export const warn = (...args: unknown[]) => {
  if (!getConfig()?.debug) return
  safeConsole?.warn("[ClickLake]", ...args)
}

export const error = (...args: unknown[]) => {
  if (!getConfig()?.debug) return
  safeConsole?.error("[ClickLake]", ...args)
}
