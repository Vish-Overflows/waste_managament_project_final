export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    ...options,
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
    throw new Error((payload as { detail?: string }).detail || "Request failed");
  }
  return payload as T;
}
