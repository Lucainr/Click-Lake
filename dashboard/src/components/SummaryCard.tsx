interface SummaryCardProps {
  label: string
  value: string
  accent?: "neutral" | "good" | "warn" | "danger"
}

export const SummaryCard = ({ label, value, accent = "neutral" }: SummaryCardProps) => (
  <article className={`summary-card summary-card--${accent}`}>
    <span>{label}</span>
    <strong>{value}</strong>
  </article>
)
