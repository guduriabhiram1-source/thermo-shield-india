import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Flame, LogIn } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { errorMessage } from '../services/api';
import { DATA_NOTICE } from '../components/Common';

export function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-ink-100 dark:bg-ink-950 text-ink-900 dark:text-ink-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-3 justify-center mb-6">
          <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-brand-500 to-ember-500 grid place-items-center text-white shadow"><Flame size={24} /></div>
          <div className="leading-tight"><div className="font-extrabold tracking-tight text-lg">THERMO-SHIELD INDIA</div><div className="text-[10px] font-semibold text-ink-500 tracking-[0.2em]">THERMAL INCIDENT INTELLIGENCE</div></div>
        </div>
        <div className="card p-6">
          <h1 className="text-xl font-bold">{title}</h1>
          <p className="text-sm text-ink-500 dark:text-ink-400 mb-4">{subtitle}</p>
          {children}
        </div>
        <p className="mt-4 text-[11px] text-ink-500 dark:text-ink-400 leading-relaxed">{DATA_NOTICE}</p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const needsVerify = err?.toLowerCase().includes('verification required');
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { await login(email, password); nav(loc.state?.from ?? '/dashboard'); } catch (ex) { setErr(errorMessage(ex)); } finally { setBusy(false); }
  };
  return (
    <AuthShell title="Sign in" subtitle="Registered and e-mail-verified accounts only.">
      <form onSubmit={submit} className="space-y-3">
        <div><label className="label" htmlFor="email">E-mail</label><input id="email" className="input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div><label className="label" htmlFor="password">Password</label><input id="password" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
        {err && <div role="alert" className="text-sm text-red-700 dark:text-red-300">{err}{needsVerify && <> — <Link className="underline" to={`/verify-email?email=${encodeURIComponent(email)}`}>enter your verification code</Link></>}</div>}
        <button className="btn-primary w-full justify-center" disabled={busy}><LogIn size={16} /> {busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
      <div className="mt-4 text-sm text-ink-600 dark:text-ink-300">No account? <Link className="text-brand-600 font-semibold hover:underline" to="/register">Create one</Link> · <Link className="text-brand-600 font-semibold hover:underline" to="/verify-email">Verify e-mail</Link></div>
    </AuthShell>
  );
}
