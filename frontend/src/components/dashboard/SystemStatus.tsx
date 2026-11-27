"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { getStorage, type StorageResponse } from "@/lib/settings";
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
  const [storage, setStorage] =
    useState<StorageResponse | null>(null);

  async function refresh() {
    setChecking(true);

    try {
      const result = await getSystemStatus();

      setStatus(result);
      setConnection("Online");
    } catch {
      setStatus(null);
      setConnection("Unavailable");
    }

    try {
      setStorage(await getStorage());
    } catch {
      setStorage(null);
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
      name: "Workspace database",
      status: storage
        ? `${storage.database} · schema ${storage.schema_version} · ${storage.integrity}`
        : "Not verified",
    },
    {
      name: "External execution",
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
