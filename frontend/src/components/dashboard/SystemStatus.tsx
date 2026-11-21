const services = [
  { name: "Backend connection", status: "Not checked" },
  { name: "AI provider", status: "Not configured" },
  { name: "Local database", status: "Pending" },
  { name: "Execution engine", status: "Disabled" },
];

export default function SystemStatus() {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>System status</h2>
      </div>

      {services.map((service) => (
        <div className="service-row" key={service.name}>
          <span>{service.name}</span>
          <small>{service.status}</small>
        </div>
      ))}
    </section>
  );
}
