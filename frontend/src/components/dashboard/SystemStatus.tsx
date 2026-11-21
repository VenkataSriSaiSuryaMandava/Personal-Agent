"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import {
  getSystemStatus,
  type SystemStatusResponse,
} from "@/lib/api";

export default function SystemStatus() {
  const [status, setStatus] =
    useState<SystemStatusResponse | null>(null);

  const [connection, setConnection] =
    useState("Checking");

  const [checking, setChecking] = useState(false);

  async function refresh() {
    setChecking(true);

    try {
      const result = await getSystemStatus();

      setStatus(result);
      setConnection("Online");
    } catch {
      setStatus(null);
      setConnection("Unavailable");
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(refresh, 0);

    return () => window.clearTimeout(timer);
  }, []);

  const services = [
    {
      name: "Backend connection",
      status: connection,
    },
    {
      name: "AI provider",
      status: status?.ai_provider
        ? status.ai_provider.replaceAll("_", " ")
        : "Unknown",
    },
    {
      name: "Local database",
      status: status?.database
        ? status.database.replaceAll("_", " ")
        : "Unknown",
    },
    {
      name: "Execution engine",
      status: status
        ? status.execution_enabled
          ? "Enabled"
          : "Disabled"
        : "Unknown",
    },
    {
      name: "Cloud requests",
      status: status
        ? status.cloud_requests_enabled
          ? "Enabled"
          : "Disabled"
        : "Unknown",
    },
  ];

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>System status</h2>

        <button
          className="icon-button"
          onClick={refresh}
          disabled={checking}
          aria-label="Refresh system status"
        >
          <RefreshCw size={16} />
        </button>
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
