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

const fetchJson = async <T,>(path: string): Promise<T> => {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`Failed to load ${path}`)
  }
  return (await response.json()) as T
}

const formatInt = (value: number) => value.toLocaleString("ko-KR")
const formatRatio = (value: number) => `${(value * 100).toFixed(2)}%`

const sortByDateDesc = <T extends { event_date: string }>(rows: T[]) =>
  [...rows].sort((a, b) => b.event_date.localeCompare(a.event_date))

const App = () => {
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedSdkKey, setSelectedSdkKey] = useState<string>("all")

  useEffect(() => {
    const load = async () => {
      try {
        const [health, promotion, funnel] = await Promise.all([
          fetchJson<HealthRow[]>("/demo-data/health.json"),
          fetchJson<PromotionPerformanceRow[]>("/demo-data/promotion_performance.json"),
          fetchJson<CampaignFunnelRow[]>("/demo-data/campaign_funnel.json")
        ])

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
        setError(loadError instanceof Error ? loadError.message : "Unknown error")
      }
    }

    void load()
  }, [])

  const sdkKeyOptions = useMemo(() => {
    if (!data) return []
    const keys = new Set<string>()
    data.health.forEach((row) => keys.add(row.sdk_key))
    data.promotion.forEach((row) => keys.add(row.sdk_key))
    data.funnel.forEach((row) => keys.add(row.sdk_key))
    return [...keys].sort()
  }, [data])

  const filtered = useMemo(() => {
    if (!data) return null
    if (selectedSdkKey === "all") return data

    return {
      health: data.health.filter((row) => row.sdk_key === selectedSdkKey),
      promotion: data.promotion.filter((row) => row.sdk_key === selectedSdkKey),
      funnel: data.funnel.filter((row) => row.sdk_key === selectedSdkKey)
    }
  }, [data, selectedSdkKey])

  const healthSummary = useMemo(() => {
    if (!filtered) return null

    const raw = filtered.health.reduce((sum, row) => sum + row.raw_event_count, 0)
    const valid = filtered.health.reduce((sum, row) => sum + row.valid_event_count, 0)
    const invalid = filtered.health.reduce((sum, row) => sum + row.invalid_event_count, 0)
    const ratio = raw === 0 ? 0 : invalid / raw

    return { raw, valid, invalid, ratio }
  }, [filtered])

  if (error) {
    return <main className="app"><p className="error">{error}</p></main>
  }

  if (!filtered || !healthSummary) {
    return <main className="app"><p>Loading demo dashboard...</p></main>
  }

  return (
    <main className="app">
      <header className="hero">
        <div>
          <h1>Click Lake Demo Dashboard</h1>
          <p>Gold JSON 집계를 빠르게 시연하기 위한 read-only 화면입니다.</p>
        </div>
        <label>
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
        />
        <div className="summary-grid">
          <SummaryCard label="Raw Events" value={formatInt(healthSummary.raw)} />
          <SummaryCard label="Valid Events" value={formatInt(healthSummary.valid)} accent="good" />
          <SummaryCard label="Invalid Events" value={formatInt(healthSummary.invalid)} accent="warn" />
          <SummaryCard label="Invalid Ratio" value={formatRatio(healthSummary.ratio)} accent="danger" />
        </div>
        <DataTable
          columns={[
            { key: "event_date", label: "event_date" },
            { key: "sdk_key", label: "sdk_key" },
            { key: "raw_event_count", label: "raw", align: "right", render: (v) => formatInt(Number(v)) },
            { key: "valid_event_count", label: "valid", align: "right", render: (v) => formatInt(Number(v)) },
            { key: "invalid_event_count", label: "invalid", align: "right", render: (v) => formatInt(Number(v)) },
            {
              key: "invalid_event_ratio",
              label: "invalid_ratio",
              align: "right",
              render: (v) => formatRatio(Number(v))
            },
            {
              key: "distinct_sessions",
              label: "distinct_sessions",
              align: "right",
              render: (v) => formatInt(Number(v))
            },
            { key: "latest_event_time", label: "latest_event_time" },
            {
              key: "freshness_minutes",
              label: "freshness_minutes",
              align: "right",
              render: (v) => (v === null ? "-" : formatInt(Number(v)))
            }
          ]}
          rows={filtered.health}
          rowKey={(row) => `${row.event_date}-${row.sdk_key}`}
        />
      </section>

      <section className="section">
        <SectionHeader
          title="2) Promotion Performance"
          description="CTR 및 post-click 성과를 프로모션 단위로 확인합니다."
        />
        <DataTable
          columns={[
            { key: "event_date", label: "event_date" },
            { key: "sdk_key", label: "sdk_key" },
            { key: "campaign_id", label: "campaign_id" },
            { key: "promotion_id", label: "promotion_id" },
            { key: "promotion_name", label: "promotion_name" },
            { key: "placement", label: "placement" },
            { key: "promotion_views", label: "views", align: "right", render: (v) => formatInt(Number(v)) },
            { key: "promotion_clicks", label: "clicks", align: "right", render: (v) => formatInt(Number(v)) },
            { key: "ctr", label: "ctr", align: "right", render: (v) => formatRatio(Number(v)) },
            {
              key: "product_views_after_click",
              label: "pv_after_click",
              align: "right",
              render: (v) => formatInt(Number(v))
            },
            {
              key: "add_to_cart_after_click",
              label: "atc_after_click",
              align: "right",
              render: (v) => formatInt(Number(v))
            },
            {
              key: "product_view_rate_after_click",
              label: "pv_rate_after_click",
              align: "right",
              render: (v) => formatRatio(Number(v))
            },
            {
              key: "add_to_cart_rate_after_click",
              label: "atc_rate_after_click",
              align: "right",
              render: (v) => formatRatio(Number(v))
            }
          ]}
          rows={filtered.promotion}
          rowKey={(row, index) => `${row.event_date}-${row.sdk_key}-${row.promotion_id}-${index}`}
        />
      </section>

      <section className="section">
        <SectionHeader
          title="3) Campaign Funnel"
          description="세션 기준 퍼널 전환율(view→click→product_view/add_to_cart)을 확인합니다."
        />
        <DataTable
          columns={[
            { key: "event_date", label: "event_date" },
            { key: "sdk_key", label: "sdk_key" },
            { key: "campaign_id", label: "campaign_id" },
            { key: "campaign_name", label: "campaign_name" },
            {
              key: "promotion_view_sessions",
              label: "view_sessions",
              align: "right",
              render: (v) => formatInt(Number(v))
            },
            {
              key: "promotion_click_sessions",
              label: "click_sessions",
              align: "right",
              render: (v) => formatInt(Number(v))
            },
            {
              key: "product_view_sessions",
              label: "pv_sessions",
              align: "right",
              render: (v) => formatInt(Number(v))
            },
            {
              key: "add_to_cart_sessions",
              label: "atc_sessions",
              align: "right",
              render: (v) => formatInt(Number(v))
            },
            {
              key: "view_to_click_rate",
              label: "view_to_click_rate",
              align: "right",
              render: (v) => formatRatio(Number(v))
            },
            {
              key: "click_to_product_view_rate",
              label: "click_to_pv_rate",
              align: "right",
              render: (v) => formatRatio(Number(v))
            },
            {
              key: "click_to_add_to_cart_rate",
              label: "click_to_atc_rate",
              align: "right",
              render: (v) => formatRatio(Number(v))
            }
          ]}
          rows={filtered.funnel}
          rowKey={(row) => `${row.event_date}-${row.sdk_key}-${row.campaign_id}`}
        />
      </section>
    </main>
  )
}

export default App
