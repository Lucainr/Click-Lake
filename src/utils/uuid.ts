const randomPart = (): string => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID().replace(/-/g, "")
  }
  // SSR / very old browser fallback
  return Math.random().toString(36).slice(2, 10) + Math.random().toString(36).slice(2, 10)
}

export const makeId = (prefix: string) => `${prefix}_${randomPart()}`
