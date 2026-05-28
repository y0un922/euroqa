const AUTH_TOKEN_KEY = "euroqa_auth_token";
const AUTH_EXPIRED_EVENT = "euroqa:auth-expired";

function storage(): Storage | null {
  try {
    return typeof localStorage !== "undefined" ? localStorage : null;
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  return storage()?.getItem(AUTH_TOKEN_KEY) ?? null;
}

export function setToken(token: string): void {
  storage()?.setItem(AUTH_TOKEN_KEY, token);
}

export function clearToken(): void {
  storage()?.removeItem(AUTH_TOKEN_KEY);
}

function decodeTokenPayload(token: string): Record<string, unknown> | null {
  const parts = token.split(".");
  if (parts.length !== 2 || !parts[0]) {
    return null;
  }

  try {
    const base64 = parts[0].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const payload = JSON.parse(globalThis.atob(padded)) as unknown;
    return typeof payload === "object" && payload !== null
      ? (payload as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

export function isTokenUsable(token: string, nowMs = Date.now()): boolean {
  const payload = decodeTokenPayload(token);
  if (!payload || typeof payload.exp !== "number") {
    return false;
  }

  return payload.exp * 1000 >= nowMs;
}

export function isAuthenticated(): boolean {
  const token = getToken();
  if (!token) {
    return false;
  }

  if (!isTokenUsable(token)) {
    clearToken();
    return false;
  }

  return true;
}

export function dispatchAuthExpired(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
}

export function onAuthExpired(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(AUTH_EXPIRED_EVENT, listener);
  return () => window.removeEventListener(AUTH_EXPIRED_EVENT, listener);
}
