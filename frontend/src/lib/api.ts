export interface SystemStatusResponse {
  backend: string;
  mode: string;
  ai_provider: string;
  database: string;
  execution_enabled: boolean;
  cloud_requests_enabled: boolean;
}

export interface ChatResponse {
  status: "preview";
  message: string;
  transmitted: false;
  executed: false;
}

async function request<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    cache: "no-store",
    signal: AbortSignal.timeout(8000),
  });

  if (response.status === 401) {
    window.dispatchEvent(
      new Event("aegis-session-expired")
    );
  }

  if (!response.ok) {
    throw new Error(
      `Request failed (${response.status})`
    );
  }

  return response.json() as Promise<T>;
}

export function getSystemStatus() {
  return request<SystemStatusResponse>(
    "/api/agent/status"
  );
}

export function sendMessage(message: string) {
  return request<ChatResponse>(
    "/api/agent/chat",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message }),
    }
  );
}
