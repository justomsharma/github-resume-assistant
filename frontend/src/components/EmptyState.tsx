interface EmptyStateProps {
  icon: string;
  title: string;
  description: string;
}

/** A reusable empty-state message for panels with no data to show yet (dashboard theme). */
export default function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <div className="dempty">
      <span className="dempty-ic" aria-hidden="true">
        {icon}
      </span>
      <div className="dempty-t">{title}</div>
      <p className="dempty-d">{description}</p>
    </div>
  );
}
