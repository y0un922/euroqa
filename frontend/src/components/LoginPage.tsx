import { useState, type FormEvent } from "react";
import { LockKeyhole, LogIn } from "lucide-react";

import { login } from "../lib/api";
import { setToken } from "../lib/auth";

type LoginPageProps = {
  onLogin: () => void;
};

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { token } = await login(password);
      setToken(token);
      onLogin();
    } catch {
      setError("密码不正确，请重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-stone-50 px-6 text-stone-900">
      <section className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-cyan-800 text-white">
            <LockKeyhole className="h-5 w-5" />
          </div>
          <div>
            <h1 className="font-serif text-2xl font-semibold tracking-tight">
              Euro_QA
            </h1>
            <p className="text-sm text-stone-500">请输入访问密码</p>
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-lg border border-stone-200 bg-white p-6 shadow-sm"
        >
          <label
            htmlFor="access-password"
            className="text-sm font-medium text-stone-700"
          >
            访问密码
          </label>
          <input
            id="access-password"
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-2 w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition placeholder:text-stone-400 focus:border-cyan-700 focus:ring-2 focus:ring-cyan-100"
            placeholder="输入密码"
          />

          {error && (
            <p className="mt-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-md bg-cyan-800 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-cyan-900 disabled:cursor-not-allowed disabled:bg-stone-300"
          >
            <LogIn className="h-4 w-4" />
            {loading ? "登录中..." : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}
