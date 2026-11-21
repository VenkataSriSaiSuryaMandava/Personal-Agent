interface StatusCardProps {
  title: string;
  value: string;
  description: string;
}

export default function StatusCard({
  title,
  value,
  description,
}: StatusCardProps) {
  return (
    <section className="status-card">
      <p>{title}</p>
      <h2>{value}</h2>
      <small>{description}</small>
    </section>
  );
}
