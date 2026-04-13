export interface PageContext {
  page_url: string
  referrer_url?: string | null
  page_title?: string | null
  page_type?: string | null
}

export const getPageContext = (): PageContext => {
  if (typeof window === "undefined") {
    return {
      page_url: "",
      referrer_url: null,
      page_title: null,
      page_type: null
    }
  }
  const page_url = `${window.location.pathname}${window.location.search}`
  const referrer_url = document.referrer || null
  const page_title = document.title || null
  return {
    page_url,
    referrer_url,
    page_title,
    page_type: null
  }
}
