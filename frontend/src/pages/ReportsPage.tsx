import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, Eye, RefreshCw } from 'lucide-react';
import { Api, errorMessage } from '../services/api';
import { ErrorBox, Loading, Section } from '../components/Common';
import { DataStatusBadge, RiskBadge } from '../components/Badges';
import { downloadReport } from '../components/IncidentCard';
import { fmtDate } from '../utils/format';

export default function ReportsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['reports'], queryFn: Api.reports });
  const regen = useMutation({ mutationFn: (id: number) => Api.regenerateReport(id), onSuccess: () => qc.invalidateQueries({ queryKey: ['reports'] }) });
  if (q.error) return <ErrorBox error={errorMessage(q.error)} />;
  if (!q.data) return <Loading />;
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Report History</h1><p className="text-sm text-ink-500">ThermoShield_Incident_&lt;id&gt;.pdf — 13-section automatic incident reports (ReportLab). Every value is labelled OBSERVED / MODEL INFERENCE / ESTIMATE / HUMAN VERIFIED / UNAVAILABLE.</p></div>
      <Section title={`${q.data.length} report(s)`}>
        {q.data.length === 0 ? <div className="text-sm text-ink-500">No PDF generated yet — open an incident and click “Generate PDF”.</div> : (
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>Incident ID</th><th>Date</th><th>Location</th><th>Classification</th><th>Risk</th><th>Data</th><th>PDF status</th><th>Created</th><th>Actions</th></tr></thead>
            <tbody>{q.data.map((r) => (
              <tr key={r.id}>
                <td><Link className="font-mono text-brand-700 dark:text-brand-300 hover:underline" to={`/reports/${r.id}`}>{r.incident_id}</Link></td><td className="text-xs">{fmtDate(r.event_date)}</td><td className="text-xs">{r.locality || '—'}, {r.district || '—'}, {r.state}</td>
                <td>{r.classification_label}</td><td><RiskBadge level={r.risk_level ?? 'LOW'} score={r.risk_score} /></td><td>{r.data_status && <DataStatusBadge status={r.data_status} />}</td>
                <td><span className={`badge ${r.status === 'generated' ? 'bg-green-100 text-green-800' : r.status === 'stale' ? 'bg-ink-100 text-ink-600' : 'bg-red-100 text-red-800'}`}>{r.status}</span></td><td className="text-xs">{fmtDate(r.created_at)}</td>
                <td className="whitespace-nowrap"><button className="btn-ghost !p-1" title="View" onClick={() => downloadReport(r.id, r.file_name, true)}><Eye size={15} /></button><button className="btn-ghost !p-1" title="Download" onClick={() => downloadReport(r.id, r.file_name)} data-testid={`download-${r.id}`}><Download size={15} /></button><button className="btn-ghost !p-1" title="Regenerate" onClick={() => regen.mutate(r.id)}><RefreshCw size={15} /></button></td>
              </tr>))}</tbody>
          </table></div>
        )}
      </Section>
    </div>
  );
}
