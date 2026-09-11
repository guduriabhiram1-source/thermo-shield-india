import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { UserPlus } from 'lucide-react';
import { Api, errorMessage } from '../services/api';
import { AuthShell } from './LoginPage';

export default function RegisterPage() {
  const nav = useNavigate();
  const [form, setForm] = useState({ email: '', password: '', confirm_password: '', full_name: '', organisation: '' });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (form.password !== form.confirm_password) { setErr('Passwords do not match'); return; }
    setBusy(true);
    try {
      const r = await Api.register(form);
      nav(`/verify-email?email=${encodeURIComponent(form.email)}`, { state: { message: `${r.message} ${r.detail ?? ''}` } });
    } catch (ex) { setErr(errorMessage(ex)); } finally { setBusy(false); }
  };
  return (
    <AuthShell title="Create account" subtitle="Step 1 of 2 — a 6-digit verification code will be sent to your Gmail / e-mail address.">
      <form onSubmit={submit} className="space-y-3">
        <div><label className="label" htmlFor="email">E-mail</label><input id="email" className="input" type="email" autoComplete="email" value={form.email} onChange={set('email')} required /></div>
        <div><label className="label" htmlFor="full_name">Full name (optional)</label><input id="full_name" className="input" value={form.full_name} onChange={set('full_name')} /></div>
        <div><label className="label" htmlFor="organisation">Organisation (optional)</label><input id="organisation" className="input" value={form.organisation} onChange={set('organisation')} /></div>
        <div><label className="label" htmlFor="password">Password (≥ 10 characters, letters + digits)</label><input id="password" className="input" type="password" autoComplete="new-password" minLength={10} value={form.password} onChange={set('password')} required /></div>
        <div><label className="label" htmlFor="confirm">Confirm password</label><input id="confirm" className="input" type="password" autoComplete="new-password" minLength={10} value={form.confirm_password} onChange={set('confirm_password')} required /></div>
        {err && <div role="alert" className="text-sm text-red-700 dark:text-red-300">{err}</div>}
        <button className="btn-primary w-full justify-center" disabled={busy}><UserPlus size={16} /> {busy ? 'Creating…' : 'Create account & send code'}</button>
      </form>
      <div className="mt-4 text-sm text-ink-600 dark:text-ink-300">Already registered? <Link className="text-brand-600 font-semibold hover:underline" to="/login">Sign in</Link></div>
    </AuthShell>
  );
}
