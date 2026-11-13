export class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem("access_token", token);
  else localStorage.removeItem("access_token");
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  // 0. Р—Р°РіРѕР»РѕРІРєРё
  const headers = new Headers(init.headers || {});
  if (!headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  // 1. Р—Р°РїСЂРѕСЃ
  const response = await fetch(`${API_URL}${path}`, { ...init, headers, signal: init.signal || AbortSignal.timeout(120000) });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      /* ignore */
    }
    throw new ApiError(typeof detail === "string" ? detail : "Ошибка запроса", response.status);
  }

  // 2. РџСѓСЃС‚РѕР№ РѕС‚РІРµС‚
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export { API_URL };
