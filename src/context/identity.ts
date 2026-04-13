import { makeId } from "../utils/uuid"

const ANON_KEY = "clicklake_anonymous_id"
let userId: string | null = null

const getStorage = () => {
  try {
    return typeof window !== "undefined" ? window.localStorage : null
  } catch (e) {
    return null
  }
}

export const getAnonymousId = (): string => {
  const storage = getStorage()
  if (!storage) return makeId("anon")
  const existing = storage.getItem(ANON_KEY)
  if (existing) return existing
  const created = makeId("anon")
  storage.setItem(ANON_KEY, created)
  return created
}

export const setUserId = (id: string | null) => {
  userId = id
}

export const getUserId = () => userId
