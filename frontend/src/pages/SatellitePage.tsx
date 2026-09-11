import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Api, errorMessage } from '../services/api';
import { ErrorBox, InfoBox, KV, Loading, Section } from '../components/Common';
import { DataStatusBadge } from '../components/Badges';
import { useDateRange } from '../hooks/useDateRange';
import { DateRangeSelector } from '../components/DateRangeSelector';
import { fmtDate, fmtNum } from '../utils/format';

export default function SatellitePage() {
  const { params } = useDateRange();
  const latest = useQuery({ queryKey: ['firms-latest'], queryFn: () => Api.firmsLatest(200) });
  const runs = useQuery({ queryKey: ['firms-runs'], queryFn: Api.firmsRuns });
  const events = useQuery({ queryKey: ['events-sat', params], queryFn: () => Api.events({ ...params, limit: 30, sort: 'priority' }) });
  const [sel, setSel] = useState<string | null>(null);
  const sat = useQuery({ queryKey: ['satellite', sel], queryFn: () => Api.satellite(sel!, false), enabled: !!sel });
  if (latest.error) return <ErrorBox error={errorMessage(latest.error)} />;
  if (!latest.data) return <Loading />;
  const l = latest.data;
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Satellite Data</h1><p className="text-sm text-ink-500">NASA FIRMS thermal detections (VIIRS SNPP / NOAA-20 / NOAA-21, MODIS) and Sentinel-2 L2A optical scenes (Earth Search STAC). Thermal detection ≠ optical confirmation ≠ post-event evidence.</p></div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Section title="NASA FIRMS feed status"><KV items={[['Source', l.source], ['Map key configured', l.firms_key_configured ? 'yes (area API + 12-month archive)' : 'no (keyless public feed, last 24h–7d only)'], ['Total detections stored', fmtNum(l.total_detections)], ['LIVE detections', fmtNum(l.live_detections)], ['Latest live observation', fmtDate(l.latest_live_observation)], ['Latest observation', fmtDate(l.latest_observation)], ['Live window', `${l.live_window_hours} h`], ['History window', `${fmtDate(l.history_window.from)} → ${fmtDate(l.history_window.to)}`], ['Last run', l.last_run ? `${l.last_run.mode} · ${l.last_run.message}` : null]]} />
          {!l.firms_key_configured && <div className="mt-2"><InfoBox tone="warn">Historical data older than the public 7-day feed is unavailable until NASA_FIRMS_MAP_KEY is configured (free at firms.modaps.eosdis.nasa.gov/api/map_key). Nothing is fabricated for the missing period.</InfoBox></div>}
          <div className="mt-3 text-xs"><div className="card-title mb-1">Public feed URLs</div>{Object.entries(l.public_feeds ?? {}).map(([k, v]) => <div key={k} className="font-mono break-all">{k}: {String(v)}</div>)}</div>
        </Section>
        <Section title="Ingestion runs">{!runs.data?.length ? <div className="text-sm text-ink-500">No ingestion run yet.</div> : <div className="overflow-x-auto max-h-72"><table className="table"><thead><tr><th>Started</th><th>Source</th><th>Mode</th><th>Valid</th><th>Live</th><th>Hist.</th><th>Dup</th><th>Rej.</th><th>Events</th><th>Alerts</th></tr></thead><tbody>{runs.data.map((r: any) => <tr key={r.id}><td className="text-xs">{fmtDate(r.started_at)}</td><td className="text-xs">{r.source}</td><td>{r.mode}</td><td>{r.rows_valid}</td><td>{r.rows_live}</td><td>{r.rows_historical}</td><td>{r.rows_duplicate}</td><td>{r.rows_rejected}</td><td>{r.events_formed}/{r.events_touched}</td><td>{r.alerts_sent}</td></tr>)}</tbody></table></div>}</Section>
      </div>
      <DateRangeSelector />
      <Section title="Sentinel-2 optical evidence by incident">
        <div className="flex flex-wrap gap-1 mb-3">{events.data?.items.map((e) => <button key={e.incident_id} className={sel === e.incident_id ? 'btn-primary text-xs' : 'btn-secondary text-xs'} onClick={() => setSel(e.incident_id)}>{e.incident_id} <DataStatusBadge status={e.data_status} /></button>)}</div>
        {sel && sat.data && (<div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div className="rounded-lg border border-ink-200 dark:border-ink-800 p-3"><div className="font-semibold">Thermal detection</div>{sat.data.thermal_detection.note}</div>
          <div className="rounded-lg border border-ink-200 dark:border-ink-800 p-3"><div className="font-semibold">Sentinel-2 ({sat.data.sentinel2.status})</div>{sat.data.sentinel2.note} <Link className="text-brand-600 hover:underline" to={`/incidents/${sel}/images`}>Open incident images →</Link></div>
          <div className="rounded-lg border border-ink-200 dark:border-ink-800 p-3"><div className="font-semibold">Post-event evidence ({sat.data.post_event_evidence.status})</div>{sat.data.post_event_evidence.note}</div>
          <div className="md:col-span-3 grid grid-cols-1 md:grid-cols-2 gap-3"><figure><img src={sat.data.optical_reference.before.url} alt="before" className="rounded-lg w-full" loading="lazy" /><figcaption>Before ({sat.data.optical_reference.before.date}) — {sat.data.optical_reference.before.provider}</figcaption></figure><figure><img src={sat.data.optical_reference.after.url} alt="after" className="rounded-lg w-full" loading="lazy" /><figcaption>After ({sat.data.optical_reference.after.date}) — {sat.data.optical_reference.after.provider}</figcaption></figure></div>
          <div className="md:col-span-3 text-amber-700 dark:text-amber-300">{sat.data.disclaimer}</div>
        </div>)}
      </Section>
      <Section title="Latest FIRMS detections (200)"><div className="overflow-x-auto max-h-96"><table className="table"><thead><tr><th>Observed (UTC)</th><th>Status</th><th>Lat / Lon</th><th>Satellite</th><th>FRP (MW)</th><th>Brightness (K)</th><th>Conf.</th><th>Source</th><th>Event</th></tr></thead><tbody>{l.items.map((d: any) => <tr key={d.id}><td className="text-xs">{d.acq_date} {d.acq_time}Z</td><td><DataStatusBadge status={d.data_status} /></td><td className="font-mono text-xs">{d.latitude.toFixed(4)}, {d.longitude.toFixed(4)}</td><td>{d.satellite}/{d.instrument}</td><td>{d.frp}</td><td>{d.brightness}</td><td>{d.confidence}</td><td className="text-xs">{d.source}</td><td className="text-xs">{d.event_id ?? '—'}</td></tr>)}</tbody></table></div></Section>
    </div>
  );
}
