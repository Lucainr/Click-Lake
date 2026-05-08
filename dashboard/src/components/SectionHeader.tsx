interface SectionHeaderProps {
  title: string
  description: string
  meta?: string
}

export const SectionHeader = ({ title, description, meta }: SectionHeaderProps) => (
  <div className="section-header">
    <div>
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
    {meta ? <span className="section-meta">{meta}</span> : null}
  </div>
)
