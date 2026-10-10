import { useState, type FormEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { ShieldAlert, LogIn, AlertCircle } from "lucide-react";
import { useAuth } from "../lib/auth";

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from: string = (location.state as { from?: string })?.from ?? "/";

  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gem-bg flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">

        {/* Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-gem-emerald-soft border border-emerald-200 mb-4">
            <ShieldAlert size={22} className="text-gem-emerald" />
          </div>
          <h1 className="text-xl font-bold text-gem-text">GeM Astra</h1>
          <p className="text-xs text-gem-muted mt-1 uppercase tracking-widest">
            Procurement Intelligence Platform
          </p>
        </div>

        {/* Card */}
        <div className="card space-y-5">
          <div>
            <h2 className="text-base font-semibold text-gem-text">Sign in</h2>
            <p className="text-xs text-gem-muted mt-1">
              Authorised procurement reviewers and registered bidders only.
            </p>
          </div>

          {error && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
              <AlertCircle size={14} className="shrink-0 mt-0.5 text-red-500" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-xs text-gem-muted mb-1">
                Email address
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
                placeholder="you@organisation.gov.in"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-xs text-gem-muted mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full flex items-center justify-center gap-2"
            >
              <LogIn size={15} />
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="text-xs text-gem-subtle text-center">
            Public self-registration is not available.
            Contact your system administrator for access.
          </p>
        </div>

        {/* Demo hint */}
        <div className="mt-4 p-3 rounded-lg bg-amber-50 border border-amber-200">
          <p className="text-xs text-amber-800 text-center">
            <span className="font-semibold">Demo mode — </span>
            Run <code className="bg-amber-100 px-1 rounded">POST /api/auth/seed-demo</code> to
            create fictional demo accounts. These are not real government identities.
          </p>
        </div>
      </div>
    </div>
  );
}
