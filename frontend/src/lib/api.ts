const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/+$/, "");
const STORAGE_KEY = "campus_waste_access_token";

export function getAuthToken(): string | null {
  return window.localStorage.getItem(STORAGE_KEY);
}

export function setAuthToken(token: string) {
  window.localStorage.setItem(STORAGE_KEY, token);
}

export function clearAuthToken() {
  window.localStorage.removeItem(STORAGE_KEY);
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAuthToken();
  const headers = new Headers(options.headers ?? {});
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    ...options,
    headers,
  });

  const rawPayload = await response.text();
  let payload: unknown = {};
  if (rawPayload) {
    try {
      payload = JSON.parse(rawPayload) as unknown;
    } catch {
      payload = {};
    }
  }
  if (!response.ok) {
    if (response.status === 401) {
      clearAuthToken();
    }
    throw new Error((payload as { detail?: string }).detail || "Request failed");
  }
  return payload as T;
}

export async function apiDownload(path: string): Promise<Blob> {
  const token = getAuthToken();
  const headers = new Headers();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers,
  });

  if (!response.ok) {
    if (response.status === 401) {
      clearAuthToken();
    }
    throw new Error("Download failed");
  }
  return response.blob();
}
