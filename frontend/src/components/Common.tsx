import { useEffect, useState, type ReactNode } from 'react';
import { api } from '../services/api';
import { AlertCircle, Info, Loader2 } from 'lucide-react';
import { UNAVAILABLE } from '../utils/format';

export function StatCard({ label, value, sub, accent = 'brand', icon }: { label: string; value: ReactNode; sub?: ReactNode; accent?: string; icon?: ReactNode }) {
  const accents: Record<string, string> = {
    brand: 'from-brand-500 to-ember-500', red: 'from-red-500 to-orange-500', orange: 'from-orange-400 to-amber-500', green: 'from-green-500 to-emerald-500', blue: 'from-sky-500 to-blue-600',
    violet: 'from-violet-500 to-fuchsia-500', slate: 'from-ink-500 to-ink-700', yellow: 'from-yellow-400 to-amber-500', purple: 'from-purple-600 to-fuchsia-600',
  };
  return (
    <div className="card p-4 relative overflow-hidden">
      <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${accents[accent] ?? accents.brand}`} />
      <div className="flex items-start justify-between gap-2"><div className="card-title">{label}</div>{icon && <div className="text-ink-400">{icon}</div>}</div>
      <div className="mt-2 text-2xl font-extrabold tracking-tight">{value}</div>
      {sub && <div className="mt-1 text-xs text-ink-500 dark:text-ink-400">{sub}</div>}
    </div>
  );
}

export function Section({ title, icon, children, right, className = '', id }: { title: ReactNode; icon?: ReactNode; children: ReactNode; right?: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={`card p-4 md:p-5 ${className}`}>
      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap"><h2 className="section-title">{icon}{title}</h2>{right}</div>
      {children}
    </section>
  );
}

export function Loading({ text = 'Loading…' }: { text?: string }) {
  return <div className="flex items-center gap-2 text-sm text-ink-500 py-8 justify-center" role="status"><Loader2 className="animate-spin" size={18} /> {text}</div>;
}

export function ErrorBox({ error }: { error: string }) {
  return <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 dark:bg-red-900/20 dark:border-red-800 p-3 text-sm text-red-800 dark:text-red-300"><AlertCircle size={16} className="mt-0.5 shrink-0" /> {error}</div>;
}

export function Empty({ text }: { text: string }) {
  return <div className="text-sm text-ink-500 dark:text-ink-400 py-6 text-center">{text}</div>;
}

export function Unavailable({ text = UNAVAILABLE }: { text?: string }) {
  return <span className="unavailable">{text}</span>;
}

export function KV({ items }: { items: [string, ReactNode][] }) {
  return <dl className="kv">{items.map(([k, v]) => (<div key={k} className="contents"><dt>{k}</dt><dd>{v === null || v === undefined || v === '' ? <Unavailable /> : v}</dd></div>))}</dl>;
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="text-xs text-ink-500 dark:text-ink-400 leading-relaxed">{children}</p>;
}

export function InfoBox({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'warn' | 'live' }) {
  const cls = tone === 'warn' ? 'border-amber-300 bg-amber-50 text-amber-900 dark:bg-amber-900/20 dark:border-amber-800 dark:text-amber-200' : tone === 'live' ? 'border-red-300 bg-red-50 text-red-900 dark:bg-red-900/20 dark:border-red-800 dark:text-red-200' : 'border-sky-300 bg-sky-50 text-sky-900 dark:bg-sky-900/20 dark:border-sky-800 dark:text-sky-200';
  return <div className={`flex items-start gap-2 rounded-lg border p-3 text-xs leading-relaxed ${cls}`}><Info size={14} className="mt-0.5 shrink-0" /><div>{children}</div></div>;
}

export const DATA_NOTICE = 'THERMO-SHIELD INDIA uses satellite, GIS, weather and other external datasets. Satellite detections represent observed thermal anomalies and do not by themselves prove a fire, its exact cause, severity, or ground impact. AI classifications and exposure estimates are decision-support outputs and require appropriate human/field verification.';

export function DataNotice() {
  return <InfoBox tone="warn"><b>Data limitation notice.</b> {DATA_NOTICE}</InfoBox>;
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: string }[]; value: T; onChange: (k: T) => void }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-ink-200 dark:border-ink-800" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} onClick={() => onChange(t.key)} className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${value === t.key ? 'border-brand-600 text-brand-700 dark:text-brand-300' : 'border-transparent text-ink-500 hover:text-ink-800 dark:hover:text-ink-200'}`}>{t.label}</button>
      ))}
    </div>
  );
}

/** Image loaded through the authenticated API client (plain <img> cannot send the bearer token). */
export function AuthImage({ src, alt, className, onClick }: { src: string; alt: string; className?: string; onClick?: (url: string) => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let obj: string | null = null;
    let cancelled = false;
    setUrl(null); setFailed(false);
    api.get(src, { responseType: 'blob' }).then((r) => { if (cancelled) return; obj = URL.createObjectURL(r.data as Blob); setUrl(obj); }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; if (obj) URL.revokeObjectURL(obj); };
  }, [src]);
  if (failed) return <div className="p-4 text-xs text-ink-500">Image unavailable</div>;
  if (!url) return <div className="p-4 text-xs text-ink-500">Loading image…</div>;
  return <img src={url} alt={alt} className={className} onClick={() => onClick?.(url)} />;
}
