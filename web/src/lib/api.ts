import type { SearchRequest, SearchResponse } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  search: (req: SearchRequest) =>
    request<SearchResponse>("/api/search", {
      method: "POST",
      body: JSON.stringify(req),
    }),
};

/** Default demo context: Purdue Memorial Union-ish, right now. */
export function demoContext() {
  const now = new Date();
  return {
    lat: 40.4249,
    lng: -86.9111,
    campus_id: "purdue",
    now_minutes: now.getHours() * 60 + now.getMinutes(),
    exclude_allergens: [] as string[],
    diet_flags: [] as string[],
    goal: "none" as const,
    radius_mi: 3.0,
  };
}
