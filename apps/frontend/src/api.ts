import type { AgentResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function sendMessage(
  message: string,
  sessionId: string = "frontend-user-session"
): Promise<AgentResponse> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(
      errorData?.detail || `Request failed with status ${response.status}`
    );
  }

  return response.json();
}

export async function checkHealth(): Promise<{
  status: string;
  endpoint_configured: boolean;
  token_configured: boolean;
}> {
  const response = await fetch(`${API_BASE}/health`);
  return response.json();
}
