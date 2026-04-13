export interface DeviceContext {
  device_type?: string | null
  os_name?: string | null
  browser_name?: string | null
  viewport_width?: number | null
  viewport_height?: number | null
  language?: string | null
  country?: string | null
}

const parseOS = (ua: string): string | null => {
  if (/windows/i.test(ua)) return "Windows"
  if (/macintosh|mac os x/i.test(ua)) return "macOS"
  if (/android/i.test(ua)) return "Android"
  if (/iphone|ipad|ipod/i.test(ua)) return "iOS"
  if (/linux/i.test(ua)) return "Linux"
  return null
}

const parseBrowser = (ua: string): string | null => {
  if (/chrome\//i.test(ua) && !/edge\//i.test(ua) && !/edg\//i.test(ua)) return "Chrome"
  if (/safari/i.test(ua) && !/chrome\//i.test(ua)) return "Safari"
  if (/firefox/i.test(ua)) return "Firefox"
  if (/edg\//i.test(ua) || /edge\//i.test(ua)) return "Edge"
  return null
}

const parseDeviceType = (ua: string): string => {
  if (/mobile/i.test(ua)) return "mobile"
  if (/tablet/i.test(ua)) return "tablet"
  return "desktop"
}

export const getDeviceContext = (): DeviceContext => {
  if (typeof window === "undefined") return {}
  const ua = window.navigator.userAgent || ""
  return {
    device_type: parseDeviceType(ua),
    os_name: parseOS(ua),
    browser_name: parseBrowser(ua),
    viewport_width: window.innerWidth || null,
    viewport_height: window.innerHeight || null,
    language: window.navigator.language || null,
    country: null
  }
}
