const AUTH_TOKEN_KEY = "euroqa_auth_token";
const AUTH_EXPIRED_EVENT = "euroqa:auth-expired";

function storage(): Storage | null {
  return typeof localStorage !== "undefined" ? localStorage : null;
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

export function isAuthenticated(): boolean {
  return getToken() !== null;
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
