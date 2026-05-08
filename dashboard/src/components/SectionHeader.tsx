interface SectionHeaderProps {
  title: string
  description: string
}

export const SectionHeader = ({ title, description }: SectionHeaderProps) => (
  <div className="section-header">
    <h2>{title}</h2>
    <p>{description}</p>
  </div>
)
