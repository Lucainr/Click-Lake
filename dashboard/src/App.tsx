import { useEffect, useMemo, useState } from "react"
import { DataTable } from "./components/DataTable"
import { SectionHeader } from "./components/SectionHeader"
import { SummaryCard } from "./components/SummaryCard"
import type { CampaignFunnelRow, HealthRow, PromotionPerformanceRow } from "./types"

interface DashboardData {
  health: HealthRow[]
  promotion: PromotionPerformanceRow[]
  funnel: CampaignFunnelRow[]
}

type SectionKey = "health" | "promotion" | "funnel"

interface ApiErrorPayload {
  error_code?: string
  message?: string
  details?: string
}

interface SectionError {
  errorCode: string
  message: string
  details?: string
  hint: string
}

const defaultLocalApiBase =
  typeof window !== "undefined" && window.location.port === "5173"
    ? "http://localhost:8000"
    : ""
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? defaultLocalApiBase).replace(/\/+$/, "")

const buildApiUrl = (path: string) => {
  if (!API_BASE_URL) return path
  return `${API_BASE_URL}${path}`
}

const withSdkKeyQuery = (path: string, sdkKey: string) => {
  if (sdkKey === "all") return path
  const params = new URLSearchParams({ sdk_key: sdkKey })
  return `${path}?${params.toString()}`
}

const getErrorHint = (errorCode: string, section: SectionKey) => {
  switch (errorCode) {
    case "CONFIG_MISSING":
      return "서버 Databricks 설정값이 누락되었습니다. (.env 확인)"
    case "DATABRICKS_CONNECT_FAILED":
      return "Databricks 연결에 실패했습니다. Host/Token/HTTP Path를 확인하세요."
    case "WAREHOUSE_UNAVAILABLE":
      return "SQL Warehouse가 중지되었거나 사용 불가 상태일 수 있습니다."
    case "DATABRICKS_QUERY_FAILED":
      return "Gold 테이블 조회 쿼리 실행에 실패했습니다."
    case "RESULT_PARSE_FAILED":
      return "조회 결과 파싱 중 오류가 발생했습니다."
    default:
      return `Failed to load ${section} data.`
  }
}

const parseErrorPayload = async (response: Response): Promise<ApiErrorPayload> => {
  const contentType = response.headers.get("content-type") ?? ""
  if (!contentType.includes("application/json")) {
    const body = await response.text()
    return {
      error_code: "UNKNOWN_ERROR",
      message: `Unexpected non-JSON response: ${body.slice(0, 80)}`
    }
  }

  try {
    return (await response.json()) as ApiErrorPayload
  } catch {
    return {
      error_code: "UNKNOWN_ERROR",
      message: "Failed to parse error response JSON"
    }
  }
}

const fetchJson = async <T,>(path: string, section: SectionKey): Promise<T> => {
  const url = buildApiUrl(path)
  const response = await fetch(url)

  if (!response.ok) {
    const payload = await parseErrorPayload(response)
    const error = new Error(payload.message ?? `Request failed: ${path}`) as Error & {
      errorCode?: string
      details?: string
    }
    error.errorCode = payload.error_code ?? "UNKNOWN_ERROR"
    error.details = payload.details
    throw error
  }

  const contentType = response.headers.get("content-type") ?? ""
  if (!contentType.includes("application/json")) {
    const body = await response.text()
    const error = new Error(`Expected JSON from ${url}, received: ${body.slice(0, 80)}`) as Error & {
      errorCode?: string
      details?: string
    }
    error.errorCode = "UNKNOWN_ERROR"
    error.details = `section=${section}`
    throw error
  }

  return (await response.json()) as T
}

const formatInt = (value: number) => value.toLocaleString("ko-KR")
const formatRatio = (value: number) => `${(value * 100).toFixed(2)}%`
const formatSdkFilterLabel = (value: string) => (value === "all" ? "All SDK Keys" : value)

const sortByDateDesc = <T extends { event_date: string }>(rows: T[]) =>
  [...rows].sort((a, b) => b.event_date.localeCompare(a.event_date))

const renderRateBadge = (value: number) => {
  const tone = value >= 0.5 ? "high" : value >= 0.2 ? "mid" : "low"
  return <span className={`metric-badge metric-badge--${tone}`}>{formatRatio(value)}</span>
}

const App = () => {
  const [data, setData] = useState<DashboardData>({ health: [], promotion: [], funnel: [] })
  const [sectionErrors, setSectionErrors] = useState<Partial<Record<SectionKey, SectionError>>>({})
  const [loading, setLoading] = useState<boolean>(true)
  const [selectedSdkKey, setSelectedSdkKey] = useState<string>("all")
  const [sdkKeyOptions, setSdkKeyOptions] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setSectionErrors({})

      const [healthResult, promotionResult, funnelResult] = await Promise.allSettled([
        fetchJson<HealthRow[]>(withSdkKeyQuery("/api/gold/health", selectedSdkKey), "health"),
        fetchJson<PromotionPerformanceRow[]>(
          withSdkKeyQuery("/api/gold/promotion-performance", selectedSdkKey),
          "promotion"
        ),
        fetchJson<CampaignFunnelRow[]>(withSdkKeyQuery("/api/gold/campaign-funnel", selectedSdkKey), "funnel")
      ])

      if (cancelled) return

      const nextData: DashboardData = {
        health:
          healthResult.status === "fulfilled"
            ? sortByDateDesc(healthResult.value)
            : [],
        promotion:
          promotionResult.status === "fulfilled"
            ? [...promotionResult.value].sort((a, b) => {
                const byDate = b.event_date.localeCompare(a.event_date)
                if (byDate !== 0) return byDate
                return b.ctr - a.ctr
              })
            : [],
        funnel:
          funnelResult.status === "fulfilled"
            ? [...funnelResult.value].sort((a, b) => {
                const byDate = b.event_date.localeCompare(a.event_date)
                if (byDate !== 0) return byDate
                return b.promotion_view_sessions - a.promotion_view_sessions
              })
            : []
      }

      if (selectedSdkKey === "all" && healthResult.status === "fulfilled") {
        const keys = [...new Set(healthResult.value.map((row) => row.sdk_key))].sort()
        setSdkKeyOptions(keys)
      }

      const nextErrors: Partial<Record<SectionKey, SectionError>> = {}

      const mapError = (section: SectionKey, reason: unknown): SectionError => {
        const errorCode =
          typeof reason === "object" && reason !== null && "errorCode" in reason
            ? String((reason as { errorCode?: string }).errorCode ?? "UNKNOWN_ERROR")
            : "UNKNOWN_ERROR"
        const message = reason instanceof Error ? reason.message : `Failed to load ${section} data`
        const details =
          typeof reason === "object" && reason !== null && "details" in reason
            ? String((reason as { details?: string }).details ?? "")
            : undefined

        return {
          errorCode,
          message,
          details,
          hint: getErrorHint(errorCode, section)
        }
      }

      if (healthResult.status === "rejected") {
        nextErrors.health = mapError("health", healthResult.reason)
      }
      if (promotionResult.status === "rejected") {
        nextErrors.promotion = mapError("promotion", promotionResult.reason)
      }
      if (funnelResult.status === "rejected") {
        nextErrors.funnel = mapError("funnel", funnelResult.reason)
      }

      setData(nextData)
      setSectionErrors(nextErrors)
      setLoading(false)
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [selectedSdkKey])

  const healthSummary = useMemo(() => {
    const raw = data.health.reduce((sum, row) => sum + row.raw_event_count, 0)
    const valid = data.health.reduce((sum, row) => sum + row.valid_event_count, 0)
    const invalid = data.health.reduce((sum, row) => sum + row.invalid_event_count, 0)
    const ratio = raw === 0 ? 0 : invalid / raw

    return { raw, valid, invalid, ratio }
  }, [data])

  const globalError =
    !loading &&
    sectionErrors.health !== undefined &&
    sectionErrors.promotion !== undefined &&
    sectionErrors.funnel !== undefined

  if (loading) {
    return (
      <main className="app">
        <div className="state-card">
          <h2>Loading dashboard...</h2>
          <p>Reading read-only data from FastAPI Gold API endpoints.</p>
        </div>
      </main>
    )
  }

  return (
    <main className="app">
      {globalError ? (
        <div className="state-card state-card--error">
          <h2>Failed to load dashboard data</h2>
          <p>모든 섹션에서 조회 실패가 발생했습니다. 서버 로그와 Databricks 상태를 확인하세요.</p>
        </div>
      ) : null}

      <header className="hero">
        <div className="hero-copy">
          <h1>Click Lake Demo Dashboard</h1>
          <p>JSON Gold metrics overview for health, promotion performance, and campaign funnel.</p>
          <div className="hero-meta">
            <span className="status-pill">Filter: {formatSdkFilterLabel(selectedSdkKey)}</span>
            <span className="status-pill">Health Rows: {formatInt(data.health.length)}</span>
            <span className="status-pill">Promotion Rows: {formatInt(data.promotion.length)}</span>
            <span className="status-pill">Funnel Rows: {formatInt(data.funnel.length)}</span>
          </div>
        </div>
        <label className="hero-filter">
          SDK Key
          <select value={selectedSdkKey} onChange={(event) => setSelectedSdkKey(event.target.value)}>
            <option value="all">All</option>
            {sdkKeyOptions.map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </select>
        </label>
      </header>

      <section className="section">
        <SectionHeader
          title="1) Health 요약"
          description="raw/valid/invalid 규모와 데이터 신선도를 확인합니다."
          meta={`Rows: ${formatInt(data.health.length)}`}
        />
        {sectionErrors.health ? (
          <div className="state-card state-card--error">
            <h2>{sectionErrors.health.errorCode}</h2>
            <p>{sectionErrors.health.message}</p>
            <p>{sectionErrors.health.hint}</p>
          </div>
        ) : (
          <>
            <div className="summary-grid">
              <SummaryCard label="총 이벤트" value={formatInt(healthSummary.raw)} hint="수집된 전체 이벤트" />
              <SummaryCard label="정상 이벤트" value={formatInt(healthSummary.valid)} hint="검증 통과 이벤트" accent="good" />
              <SummaryCard label="비정상 이벤트" value={formatInt(healthSummary.invalid)} hint="검증 실패 이벤트" accent="warn" />
              <SummaryCard label="비정상 비율" value={formatRatio(healthSummary.ratio)} hint="비정상 / 총 이벤트 수" accent="danger" />
            </div>
            <DataTable
              columns={[
                { key: "event_date", label: "이벤트 일자" },
                { key: "sdk_key", label: "SDK 키" },
                { key: "raw_event_count", label: "총 이벤트수", align: "right", render: (v) => formatInt(Number(v)) },
                { key: "valid_event_count", label: "정상 이벤트수", align: "right", render: (v) => formatInt(Number(v)) },
                { key: "invalid_event_count", label: "비정상 이벤트수", align: "right", render: (v) => formatInt(Number(v)) },
                {
                  key: "invalid_event_ratio",
                  label: "비정상 비율",
                  align: "right",
                  render: (v) => renderRateBadge(Number(v)),
                  emphasize: true
                },
                {
                  key: "distinct_sessions",
                  label: "고유 세션수",
                  align: "right",
                  render: (v) => formatInt(Number(v))
                },
                { key: "latest_event_time", label: "최종 이벤트시각" },
                {
                  key: "freshness_minutes",
                  label: "신선도(분)",
                  align: "right",
                  render: (v) => (v === null ? "-" : formatInt(Number(v)))
                }
              ]}
              rows={data.health}
              rowKey={(row) => `${row.event_date}-${row.sdk_key}`}
            />
          </>
        )}
      </section>

      <section className="section">
        <SectionHeader
          title="2) Promotion Performance"
          description="CTR 및 post-click 성과를 프로모션 단위로 확인합니다."
          meta={`Rows: ${formatInt(data.promotion.length)}`}
        />
        {sectionErrors.promotion ? (
          <div className="state-card state-card--error">
            <h2>{sectionErrors.promotion.errorCode}</h2>
            <p>{sectionErrors.promotion.message}</p>
            <p>{sectionErrors.promotion.hint}</p>
          </div>
        ) : (
          <DataTable
            columns={[
              { key: "event_date", label: "이벤트 일자" },
              { key: "sdk_key", label: "SDK 키" },
              { key: "campaign_id", label: "캠페인 ID" },
              { key: "promotion_id", label: "프로모션 ID" },
              { key: "promotion_name", label: "프로모션명" },
              { key: "placement", label: "노출 위치" },
              { key: "promotion_views", label: "노출수", align: "right", render: (v) => formatInt(Number(v)) },
              { key: "promotion_clicks", label: "클릭수", align: "right", render: (v) => formatInt(Number(v)) },
              { key: "ctr", label: "CTR", align: "right", render: (v) => renderRateBadge(Number(v)), emphasize: true },
              {
                key: "product_views_after_click",
                label: "클릭후 상품조회",
                align: "right",
                render: (v) => formatInt(Number(v))
              },
              {
                key: "add_to_cart_after_click",
                label: "클릭후 장바구니",
                align: "right",
                render: (v) => formatInt(Number(v))
              },
              {
                key: "product_view_rate_after_click",
                label: "클릭후 상품조회율",
                align: "right",
                render: (v) => renderRateBadge(Number(v)),
                emphasize: true
              },
              {
                key: "add_to_cart_rate_after_click",
                label: "클릭후 장바구니율",
                align: "right",
                render: (v) => renderRateBadge(Number(v)),
                emphasize: true
              }
            ]}
            rows={data.promotion}
            rowKey={(row, index) => `${row.event_date}-${row.sdk_key}-${row.promotion_id}-${index}`}
          />
        )}
      </section>

      <section className="section">
        <SectionHeader
          title="3) Campaign Funnel"
          description="세션 기준 퍼널 전환율(view→click→product_view/add_to_cart)을 확인합니다."
          meta={`Rows: ${formatInt(data.funnel.length)}`}
        />
        {sectionErrors.funnel ? (
          <div className="state-card state-card--error">
            <h2>{sectionErrors.funnel.errorCode}</h2>
            <p>{sectionErrors.funnel.message}</p>
            <p>{sectionErrors.funnel.hint}</p>
          </div>
        ) : (
          <DataTable
            columns={[
              { key: "event_date", label: "이벤트 일자" },
              { key: "sdk_key", label: "SDK 키" },
              { key: "campaign_id", label: "캠페인 ID" },
              { key: "campaign_name", label: "캠페인명" },
              {
                key: "promotion_view_sessions",
                label: "조회 세션수",
                align: "right",
                render: (v) => formatInt(Number(v))
              },
              {
                key: "promotion_click_sessions",
                label: "클릭 세션수",
                align: "right",
                render: (v) => formatInt(Number(v))
              },
              {
                key: "product_view_sessions",
                label: "상품조회 세션수",
                align: "right",
                render: (v) => formatInt(Number(v))
              },
              {
                key: "add_to_cart_sessions",
                label: "장바구니 세션수",
                align: "right",
                render: (v) => formatInt(Number(v))
              },
              {
                key: "view_to_click_rate",
                label: "조회→클릭 전환율",
                align: "right",
                render: (v) => renderRateBadge(Number(v)),
                emphasize: true
              },
              {
                key: "click_to_product_view_rate",
                label: "클릭→상품조회 전환율",
                align: "right",
                render: (v) => renderRateBadge(Number(v)),
                emphasize: true
              },
              {
                key: "click_to_add_to_cart_rate",
                label: "클릭→장바구니 전환율",
                align: "right",
                render: (v) => renderRateBadge(Number(v)),
                emphasize: true
              }
            ]}
            rows={data.funnel}
            rowKey={(row) => `${row.event_date}-${row.sdk_key}-${row.campaign_id}`}
          />
        )}
      </section>
    </main>
  )
}

export default App
