import test from "node:test";
import assert from "node:assert/strict";

import { getToken, isAuthenticated, isTokenUsable, setToken } from "./auth.ts";

function createToken(exp: number): string {
  const payload = Buffer.from(JSON.stringify({ iat: exp - 60, exp }))
    .toString("base64url")
    .replace(/=+$/, "");
  return `${payload}.signature`;
}

function installLocalStorage() {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key)
  };

  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: storage
  });

  return storage;
}

test("isTokenUsable rejects expired tokens", () => {
  const token = createToken(100);

  assert.equal(isTokenUsable(token, 101_000), false);
});

test("isTokenUsable accepts tokens that have not expired", () => {
  const token = createToken(200);

  assert.equal(isTokenUsable(token, 199_000), true);
});

test("isAuthenticated clears expired persisted auth token", () => {
  installLocalStorage();
  setToken(createToken(100));

  assert.equal(isAuthenticated(), false);
  assert.equal(getToken(), null);
});

test("isAuthenticated clears malformed persisted auth token", () => {
  installLocalStorage();
  setToken("not-a-token");

  assert.equal(isAuthenticated(), false);
  assert.equal(getToken(), null);
});

test("isAuthenticated keeps valid persisted auth token", () => {
  installLocalStorage();
  const token = createToken(Math.floor(Date.now() / 1000) + 60);
  setToken(token);

  assert.equal(isAuthenticated(), true);
  assert.equal(getToken(), token);
});
