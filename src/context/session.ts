import { makeId } from "../utils/uuid"

const SESSION_KEY = "clicklake_session_id"

const getStorage = () => {
  try {
    return typeof window !== "undefined" ? window.sessionStorage : null
  } catch (e) {
    return null
  }
}

export const getSessionId = (): string => {
  const storage = getStorage()
  if (!storage) return makeId("sess")
  const existing = storage.getItem(SESSION_KEY)
  if (existing) return existing
  const created = makeId("sess")
  storage.setItem(SESSION_KEY, created)
  return created
}
