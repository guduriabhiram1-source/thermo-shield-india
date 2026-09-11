import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Moon, Sun } from 'lucide-react';
import { Api, errorMessage } from '../services/api';
import { ErrorBox, InfoBox, KV, Loading, Section } from '../components/Common';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../themes/ThemeContext';
import { fmtDate } from '../utils/format';
import type { AlertSettings } from '../types';

export default function SettingsPage() {
  const { user, can } = useAuth();
  const { theme, setTheme } = useTheme();
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const ov = useQuery({ queryKey: ['overview'], queryFn: Api.overview });
  const alerts = useQuery({ queryKey: ['alert-settings'], queryFn: Api.alertSettings });
  const users = useQuery({ queryKey: ['users'], queryFn: Api.users, enabled: can('ADMIN') });
  const audit = useQuery({ queryKey: ['audit'], queryFn: Api.audit, enabled: can('ADMIN') });
  const [form, setForm] = useState<Partial<AlertSettings> | null>(null);
  const [backfill, setBackfill] = useState({ start: new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10), end: new Date().toISOString().slice(0, 10) });
  const [testTo, setTestTo] = useState(user?.email ?? '');
  const save = useMutation({ mutationFn: (b: Partial<AlertSettings>) => Api.updateAlertSettings(b), onSuccess: () => { setMsg('Alert settings saved'); qc.invalidateQueries({ queryKey: ['alert-settings'] }); }, onError: (e) => setMsg(errorMessage(e)) });
  const act = (fn: () => Promise<any>) => fn().then((r) => setMsg(r.message ?? JSON.stringify(r))).catch((e) => setMsg(errorMessage(e)));
  if (ov.error) return <ErrorBox error={errorMessage(ov.error)} />;
  if (!ov.data) return <Loading />;
  const o = ov.data;
  const a = alerts.data;
  const f = { ...(a ?? {}), ...(form ?? {}) } as AlertSettings;
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Settings</h1><p className="text-sm text-ink-500">Signed in as {user?.email} ({user?.role}).</p></div>
      {msg && <InfoBox>{msg}</InfoBox>}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Section title="Appearance"><div className="flex gap-2"><button className={theme === 'light' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTheme('light')}><Sun size={15} /> ☀️ Light</button><button className={theme === 'dark' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTheme('dark')}><Moon size={15} /> 🌙 Dark</button></div><p className="text-xs text-ink-500 mt-2">Stored in localStorage; applies to dashboard, maps, cards, charts, tables, modals, forms and PDF preview.</p></Section>
        <Section title="Data sources & providers">
          <KV items={[['FIRMS', o.providers.firms], ['FIRMS archive (12 months)', o.providers.firms_archive], ['Weather', o.providers.weather], ['OSM', `${o.providers.osm} (Nominatim ${o.providers.nominatim ? 'on' : 'off'})`], ['Satellite', o.providers.satellite], ['Land cover', o.providers.landcover], ['Population', o.providers.population], ['ML model', o.providers.ml_model], ['E-mail', o.providers.email.configured ? `configured (${o.providers.email.provider})` : o.providers.email.dev_log_only ? 'DEV log-only mode (nothing is sent)' : 'NOT configured'], ['Scheduler', o.scheduler_enabled ? `every ${o.firms_poll_minutes} min` : 'disabled'], ['Events / live', `${o.counts.events} / ${o.counts.live_events}`], ['Detections / live', `${o.counts.detections} / ${o.counts.live_detections}`], ['Reports', o.counts.reports]]} />
          <div className="mt-3 text-xs"><div className="card-title mb-1">Freshness</div>{o.freshness.map((x: any) => <div key={x.source}>{x.source}: {x.status} · source {fmtDate(x.source_timestamp)} · retrieved {fmtDate(x.retrieved_at)}</div>)}{o.freshness.length === 0 && <div className="text-ink-500">No dataset retrieved yet.</div>}</div>
        </Section>
      </div>
      <Section title="Live alert settings (ADMIN)">
        {!a ? <Loading /> : (
          <div className="space-y-3 text-sm">
            <div className={`text-xs font-semibold ${a.effective === 'active' ? 'text-green-700' : 'text-amber-700'}`}>Status: {a.effective}</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <label className="flex items-center gap-2"><input type="checkbox" disabled={!can('ADMIN')} checked={f.live_alerts_enabled} onChange={(e) => setForm({ ...form, live_alerts_enabled: e.target.checked })} /> Enable live alerts</label>
              <label className="flex items-center gap-2"><input type="checkbox" disabled={!can('ADMIN')} checked={f.high_enabled} onChange={(e) => setForm({ ...form, high_enabled: e.target.checked })} /> HIGH alert enabled</label>
              <label className="flex items-center gap-2"><input type="checkbox" disabled={!can('ADMIN')} checked={f.critical_enabled} onChange={(e) => setForm({ ...form, critical_enabled: e.target.checked })} /> CRITICAL alert enabled</label>
              <label className="md:col-span-3"><span className="label">E-mail recipients (comma separated)</span><input className="input" disabled={!can('ADMIN')} value={f.recipients ?? ''} onChange={(e) => setForm({ ...form, recipients: e.target.value })} /></label>
              <label><span className="label">Cooldown (hours)</span><input className="input" type="number" min={0} disabled={!can('ADMIN')} value={f.cooldown_hours ?? 12} onChange={(e) => setForm({ ...form, cooldown_hours: Number(e.target.value) })} /></label>
              <label><span className="label">Minimum confidence (0–1)</span><input className="input" type="number" min={0} max={1} step={0.05} disabled={!can('ADMIN')} value={f.min_confidence ?? 0} onChange={(e) => setForm({ ...form, min_confidence: Number(e.target.value) })} /></label>
            </div>
            {can('ADMIN') && <div className="flex flex-wrap gap-2 items-end"><button className="btn-primary" onClick={() => form && save.mutate(form)} disabled={!form || save.isPending}>Save</button><label><span className="label">Send test alert to</span><input className="input !w-64" value={testTo} onChange={(e) => setTestTo(e.target.value)} /></label><button className="btn-secondary" onClick={() => act(() => Api.testAlert(testTo))}>Send test</button></div>}
            <p className="text-xs text-ink-500">Updated by {a.updated_by} at {fmtDate(a.updated_at)}. Alerts are generated only from newly ingested LIVE data; historical data never triggers e-mails. Nothing is sent until SMTP is configured.</p>
          </div>
        )}
      </Section>
      {can('ADMIN') && (
        <Section title="System operations (ADMIN)">
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary" onClick={() => act(Api.liveIngest)}>Pull live FIRMS now</button>
            <button className="btn-secondary" onClick={() => act(() => Api.reanalyseAll(false))}>Re-analyse all (reference)</button>
            <button className="btn-secondary" onClick={() => act(() => Api.reanalyseAll(true))}>Re-analyse all (live enrichment)</button>
            <button className="btn-secondary" onClick={() => act(Api.maintenance)}>Run maintenance (age LIVE → HISTORICAL, 12-month purge)</button>
            <button className="btn-secondary" onClick={() => act(Api.generateVisuals)}>Generate images + PDFs</button>
          </div>
          <div className="mt-3 flex flex-wrap items-end gap-2"><label><span className="label">Historical backfill from</span><input className="input" type="date" value={backfill.start} onChange={(e) => setBackfill({ ...backfill, start: e.target.value })} /></label><label><span className="label">to</span><input className="input" type="date" value={backfill.end} onChange={(e) => setBackfill({ ...backfill, end: e.target.value })} /></label><button className="btn-secondary" onClick={() => act(() => Api.backfill(backfill.start + 'T00:00:00Z', backfill.end + 'T23:59:59Z'))}>Backfill FIRMS archive (needs MAP_KEY)</button></div>
          <p className="text-xs text-ink-500 mt-2">Backfilled rows are always HISTORICAL and never enter the live alert pipeline. Maximum 12 months.</p>
        </Section>
      )}
      {can('ADMIN') && users.data && (
        <Section title="Users (ADMIN)">
          <div className="overflow-x-auto"><table className="table"><thead><tr><th>E-mail</th><th>Name</th><th>Role</th><th>Verified</th><th>Active</th><th>Last login</th><th>Actions</th></tr></thead>
            <tbody>{users.data.map((u: any) => <tr key={u.id}><td>{u.email}</td><td>{u.full_name}</td><td><select className="input !w-32" value={u.role} disabled={u.id === user?.id} onChange={(e) => Api.updateUser(u.id, { role: e.target.value }).then(() => qc.invalidateQueries({ queryKey: ['users'] })).catch((er) => setMsg(errorMessage(er)))}><option>VIEWER</option><option>ANALYST</option><option>ADMIN</option></select></td><td>{u.is_verified ? 'yes' : 'no'}</td><td>{u.is_active ? 'yes' : 'no'}</td><td className="text-xs">{fmtDate(u.last_login_at)}</td><td>{u.id !== user?.id && <button className="btn-ghost text-xs" onClick={() => Api.updateUser(u.id, { is_active: !u.is_active }).then(() => qc.invalidateQueries({ queryKey: ['users'] }))}>{u.is_active ? 'Deactivate' : 'Activate'}</button>}</td></tr>)}</tbody></table></div>
        </Section>
      )}
      {can('ADMIN') && audit.data && <Section title="Audit log (latest 100)"><div className="overflow-x-auto max-h-80"><table className="table"><thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th></tr></thead><tbody>{audit.data.map((x: any) => <tr key={x.id}><td className="text-xs">{fmtDate(x.timestamp)}</td><td className="text-xs">{x.actor}</td><td>{x.action}</td><td className="text-xs">{x.entity_type} {x.entity_id}</td></tr>)}</tbody></table></div></Section>}
    </div>
  );
}
