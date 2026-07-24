const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

const TOKEN_KEY = "cctvbot_token";
const ROLE_KEY = "cctvbot_role";
const USER_KEY = "cctvbot_username";

export type Role = "admin" | "viewer" | string;

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: string;
}

export interface Event {
  event_id: string;
  camera_id: string;
  event_type: string;
  severity: string;
  status: string;
  confidence: number | null;
  started_at: string | null;
  ended_at: string | null;
  detected_at: string | null;
  rule: unknown;
  objects: unknown;
  evidence: {
    thumb?: string | null;
    clip?: string | null;
    relative_path?: string;
    clip_before_seconds?: number;
    clip_after_seconds?: number;
  } | null;
  review: {
    reviewed_by?: string;
    reviewed_at?: string;
    decision?: string;
    note?: string | null;
  } | null;
  notifications: unknown;
  message_th: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Camera {
  camera_id: string;
  name: string;
  stream_type: string;
  zone: string | null;
  is_online: boolean;
  last_seen_at: string | null;
  created_at: string | null;
}

export interface EventFilters {
  status?: string;
  camera_id?: string;
  event_type?: string;
  limit?: number;
  offset?: number;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getRole(): Role | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ROLE_KEY);
}

export function getUsername(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(USER_KEY);
}

export function setSession(token: string, role: string, username?: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(ROLE_KEY, role);
  if (username) localStorage.setItem(USER_KEY, username);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ROLE_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getToken());
}

export function isAdmin(): boolean {
  return getRole() === "admin";
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  auth = true,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (auth) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearSession();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function login(
  username: string,
  password: string,
): Promise<LoginResponse> {
  const data = await request<LoginResponse>(
    "/api/auth/login",
    {
      method: "POST",
      body: JSON.stringify({ username, password }),
    },
    false,
  );
  setSession(data.access_token, data.role, username);
  return data;
}

export async function listEvents(filters: EventFilters = {}): Promise<Event[]> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.camera_id) params.set("camera_id", filters.camera_id);
  if (filters.event_type) params.set("event_type", filters.event_type);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.offset != null) params.set("offset", String(filters.offset));
  const qs = params.toString();
  return request<Event[]>(`/api/events${qs ? `?${qs}` : ""}`);
}

export async function getEvent(eventId: string): Promise<Event> {
  return request<Event>(`/api/events/${encodeURIComponent(eventId)}`);
}

export async function reviewEvent(
  eventId: string,
  decision: "confirmed" | "false_positive",
  note?: string,
): Promise<Event> {
  return request<Event>(`/api/events/${encodeURIComponent(eventId)}/review`, {
    method: "PATCH",
    body: JSON.stringify({ decision, note: note || null }),
  });
}

export async function listCameras(): Promise<Camera[]> {
  return request<Camera[]>("/api/cameras");
}

export async function getEvidence(eventId: string) {
  return request<{
    event_id: string;
    evidence_root: string;
    relative_path: string;
    thumb: string | null;
    clip: string | null;
    paths: Record<string, string | null>;
  }>(`/api/events/${encodeURIComponent(eventId)}/evidence`);
}

/** Fetch evidence binary (admin JWT) and return an object URL for <img>/<video>. */
export async function fetchEvidenceFileBlobUrl(
  eventId: string,
  name: "thumb.jpg" | "clip.mp4" | "event.json",
): Promise<string> {
  const token = getToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(
    `${API_URL}/api/events/${encodeURIComponent(eventId)}/evidence/file?name=${encodeURIComponent(name)}`,
    { headers },
  );

  if (res.status === 401) {
    clearSession();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    throw new ApiError(res.status, res.statusText || "Failed to load evidence file");
  }

  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export { ApiError, API_URL };
