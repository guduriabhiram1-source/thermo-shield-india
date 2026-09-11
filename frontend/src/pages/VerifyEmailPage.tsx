import { useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { MailCheck, RefreshCw } from 'lucide-react';
import { Api, errorMessage } from '../services/api';
import { AuthShell } from './LoginPage';

export default function VerifyEmailPage() {
  const [params] = useSearchParams();
  const loc = useLocation() as { state?: { message?: string } };
  const nav = useNavigate();
  const [email, setEmail] = useState(params.get('email') ?? '');
  const [code, setCode] = useState('');
  const [msg, setMsg] = useState<string | null>(loc.state?.message ?? null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { const r = await Api.verifyEmail(email, code); setMsg(r.message); setTimeout(() => nav('/login'), 1200); } catch (ex) { setErr(errorMessage(ex)); } finally { setBusy(false); }
  };
  const resend = async () => {
    setErr(null);
    try { const r = await Api.resendVerification(email); setMsg(`${r.message} ${r.detail ?? ''}`); } catch (ex) { setErr(errorMessage(ex)); }
  };
  return (
    <AuthShell title="Verify your e-mail" subtitle="Step 2 of 2 — open Gmail and enter the 6-digit code (valid for 10 minutes).">
      <form onSubmit={submit} className="space-y-3">
        <div><label className="label" htmlFor="email">E-mail</label><input id="email" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div><label className="label" htmlFor="code">Verification code</label><input id="code" className="input font-mono text-lg tracking-[0.4em]" inputMode="numeric" pattern="\d{6}" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} required placeholder="000000" /></div>
        {msg && <div className="text-sm text-green-700 dark:text-green-300">{msg}</div>}
        {err && <div role="alert" className="text-sm text-red-700 dark:text-red-300">{err}</div>}
        <button className="btn-primary w-full justify-center" disabled={busy || code.length !== 6}><MailCheck size={16} /> {busy ? 'Verifying…' : 'Verify e-mail'}</button>
        <button type="button" className="btn-secondary w-full justify-center" onClick={resend} disabled={!email}><RefreshCw size={14} /> Resend verification code</button>
      </form>
      <div className="mt-4 text-sm text-ink-600 dark:text-ink-300"><Link className="text-brand-600 font-semibold hover:underline" to="/login">Back to sign in</Link></div>
    </AuthShell>
  );
}
