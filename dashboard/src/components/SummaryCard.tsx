interface SummaryCardProps {
  label: string
  value: string
  hint?: string
  accent?: "neutral" | "good" | "warn" | "danger"
}

export const SummaryCard = ({ label, value, hint, accent = "neutral" }: SummaryCardProps) => (
  <article className={`summary-card summary-card--${accent}`}>
    <span>{label}</span>
    <strong>{value}</strong>
    {hint ? <small>{hint}</small> : null}
  </article>
)
