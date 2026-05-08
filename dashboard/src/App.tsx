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

const fetchJson = async <T,>(path: string): Promise<T> => {
  const url = buildApiUrl(path)
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Failed to load ${path}`)
  }
  const contentType = response.headers.get("content-type") ?? ""
  if (!contentType.includes("application/json")) {
    const body = await response.text()
    throw new Error(`Expected JSON from ${url}, received: ${body.slice(0, 60)}`)
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
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [selectedSdkKey, setSelectedSdkKey] = useState<string>("all")
  const [sdkKeyOptions, setSdkKeyOptions] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false

    const loadSdkKeyOptions = async () => {
      try {
        const healthRows = await fetchJson<HealthRow[]>("/api/gold/health")
        if (cancelled) return

        const keys = [...new Set(healthRows.map((row) => row.sdk_key))].sort()
        setSdkKeyOptions(keys)
      } catch {
        if (cancelled) return
        setSdkKeyOptions([])
      }
    }

    void loadSdkKeyOptions()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError(null)

      try {
        const [health, promotion, funnel] = await Promise.all([
          fetchJson<HealthRow[]>(withSdkKeyQuery("/api/gold/health", selectedSdkKey)),
          fetchJson<PromotionPerformanceRow[]>(
            withSdkKeyQuery("/api/gold/promotion-performance", selectedSdkKey)
          ),
          fetchJson<CampaignFunnelRow[]>(withSdkKeyQuery("/api/gold/campaign-funnel", selectedSdkKey))
        ])

        if (cancelled) return
        setData({
          health: sortByDateDesc(health),
          promotion: [...promotion].sort((a, b) => {
            const byDate = b.event_date.localeCompare(a.event_date)
            if (byDate !== 0) return byDate
            return b.ctr - a.ctr
          }),
          funnel: [...funnel].sort((a, b) => {
            const byDate = b.event_date.localeCompare(a.event_date)
            if (byDate !== 0) return byDate
            return b.promotion_view_sessions - a.promotion_view_sessions
          })
        })
      } catch (loadError) {
        if (cancelled) return
        setError(loadError instanceof Error ? loadError.message : "Unknown error")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [selectedSdkKey])

  const healthSummary = useMemo(() => {
    if (!data) return null

    const raw = data.health.reduce((sum, row) => sum + row.raw_event_count, 0)
    const valid = data.health.reduce((sum, row) => sum + row.valid_event_count, 0)
    const invalid = data.health.reduce((sum, row) => sum + row.invalid_event_count, 0)
    const ratio = raw === 0 ? 0 : invalid / raw

    return { raw, valid, invalid, ratio }
  }, [data])

  if (error) {
    return (
      <main className="app">
        <div className="state-card state-card--error">
          <h2>Failed to load dashboard data</h2>
          <p>{error}</p>
        </div>
      </main>
    )
  }

  if (loading || !data || !healthSummary) {
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
      </section>

      <section className="section">
        <SectionHeader
          title="2) Promotion Performance"
          description="CTR 및 post-click 성과를 프로모션 단위로 확인합니다."
          meta={`Rows: ${formatInt(data.promotion.length)}`}
        />
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
      </section>

      <section className="section">
        <SectionHeader
          title="3) Campaign Funnel"
          description="세션 기준 퍼널 전환율(view→click→product_view/add_to_cart)을 확인합니다."
          meta={`Rows: ${formatInt(data.funnel.length)}`}
        />
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
      </section>
    </main>
  )
}

export default App
