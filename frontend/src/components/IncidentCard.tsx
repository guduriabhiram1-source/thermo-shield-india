import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Download, FileText, Image as ImageIcon, MapPin } from 'lucide-react';
import type { EventSummary } from '../types';
import { ClassBadge, DataStatusBadge, PersistenceBadge, RiskBadge, StatusBadge } from './Badges';
import { fmtDate, fmtNum, fmtPct, trendArrow, trendClass } from '../utils/format';
import { Api, errorMessage, fileUrl } from '../services/api';

export function IncidentCard({ e, compact = false }: { e: EventSummary; compact?: boolean }) {
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [hasReport, setHasReport] = useState(e.has_report);
  const generate = async () => {
    setBusy(true); setMsg(null);
    try { await Api.generatePdf(e.incident_id); setHasReport(true); setMsg('Report generated successfully'); } catch (err) { setMsg(errorMessage(err)); } finally { setBusy(false); }
  };
  return (
    <div className="card p-4 flex flex-col gap-3" data-testid="incident-card">
      <div className="flex flex-wrap items-center gap-2">
        <Link to={`/incidents/${e.incident_id}`} className="font-mono font-semibold text-brand-700 dark:text-brand-300 hover:underline">{e.incident_id}</Link>
        <DataStatusBadge status={e.data_status} />
        <RiskBadge level={e.risk_level} score={e.risk_score} />
        <ClassBadge classification={e.classification} label={e.classification_label} />
        <span className={`ml-auto text-xs font-semibold ${trendClass(e.risk_trend)}`}>{trendArrow(e.risk_trend)}</span>
      </div>
      <div className="text-sm text-ink-700 dark:text-ink-300 flex items-center gap-1"><MapPin size={14} className="text-ink-400" /> {e.locality || 'Locality unavailable'}, {e.district || 'District unavailable'}, <b>{e.state || 'State unavailable'}</b></div>
      {!compact && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1.5 text-xs">
          <div><span className="text-ink-500">Confidence</span><div className="font-semibold">{fmtPct(e.confidence, 1)}</div></div>
          <div><span className="text-ink-500">Peak FRP</span><div className="font-semibold">{fmtNum(e.max_frp, 1)} MW</div></div>
          <div><span className="text-ink-500">Population exposure</span><div className="font-semibold">{e.exposed_population === null ? 'Unavailable' : <>≈ {fmtNum(e.exposed_population)} <span className="font-normal text-ink-400">(est.)</span></>}</div></div>
          <div><span className="text-ink-500">First detected</span><div className="font-semibold">{fmtDate(e.first_detected_at)}</div></div>
          <div className="col-span-2"><span className="text-ink-500">Last updated</span><div className="font-semibold">{fmtDate(e.last_detected_at)}</div></div>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <PersistenceBadge cls={e.persistence_class} score={e.persistence_score} />
        <StatusBadge status={e.human_status} />
        {e.nearest_facility && <span className="text-[11px] text-ink-500">{e.nearest_facility.name} · {e.nearest_facility.distance_km} km</span>}
      </div>
      <div className="flex flex-wrap gap-1.5 pt-1 border-t border-ink-100 dark:border-ink-800">
        <button className="btn-primary !py-1 !px-2 text-xs" onClick={() => nav(`/incidents/${e.incident_id}`)}>View Incident</button>
        <button className="btn-secondary !py-1 !px-2 text-xs" onClick={() => nav(`/map?focus=${e.incident_id}`)}><MapPin size={13} /> View Map</button>
        <button className="btn-secondary !py-1 !px-2 text-xs" onClick={() => nav(`/incidents/${e.incident_id}/images`)}><ImageIcon size={13} /> View Images</button>
        <button className="btn-secondary !py-1 !px-2 text-xs" onClick={generate} disabled={busy}><FileText size={13} /> {busy ? 'Generating…' : 'Generate PDF'}</button>
        {hasReport && <a className="btn-secondary !py-1 !px-2 text-xs" href={fileUrl(`/api/events/${e.incident_id}/pdf`)} target="_blank" rel="noreferrer" onClick={(ev) => { ev.preventDefault(); downloadPdf(e.incident_id); }}><Download size={13} /> Download PDF</a>}
      </div>
      {msg && <div className="text-xs text-ink-600 dark:text-ink-300">{msg}</div>}
    </div>
  );
}

/** Authenticated download (the bearer token is not sent by a plain <a href>). */
export async function downloadPdf(incidentId: string, inline = false) {
  const { api } = await import('../services/api');
  const r = await api.get(`/api/events/${incidentId}/pdf`, { params: { download: !inline }, responseType: 'blob' });
  const url = URL.createObjectURL(r.data as Blob);
  if (inline) { window.open(url, '_blank'); return; }
  const a = document.createElement('a');
  a.href = url; a.download = `ThermoShield_Incident_${incidentId}.pdf`; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export async function downloadReport(reportId: number, fileName: string, inline = false) {
  const { api } = await import('../services/api');
  const r = await api.get(`/api/reports/${reportId}/${inline ? 'view' : 'download'}`, { responseType: 'blob' });
  const url = URL.createObjectURL(r.data as Blob);
  if (inline) { window.open(url, '_blank'); return; }
  const a = document.createElement('a');
  a.href = url; a.download = fileName; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
