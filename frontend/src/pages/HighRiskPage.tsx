import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Api } from '../services/api';
import EventsPage from './EventsPage';
import { InfoBox, Section } from '../components/Common';
import { fmtDate } from '../utils/format';

export default function HighRiskPage() {
  const alerts = useQuery({ queryKey: ['alert-logs'], queryFn: Api.alertLogs });
  const notes = useQuery({ queryKey: ['notifications'], queryFn: Api.notifications });
  return (
    <div className="space-y-6">
      {notes.data && <InfoBox tone="live"><b>LIVE ALERT.</b> {notes.data.live_notice} E-mail delivery: {notes.data.email.configured ? `configured (${notes.data.email.provider})` : 'NOT configured — alerts are logged but not e-mailed'}.</InfoBox>}
      <Section title="📧 Live alert log (sent / suppressed / failed)">
        {!alerts.data?.length ? <div className="text-sm text-ink-500">No alert decisions recorded yet. Alerts are evaluated only for newly ingested LIVE HIGH / CRITICAL events.</div> : (
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>When</th><th>Incident</th><th>Risk</th><th>Data</th><th>Status</th><th>Reason / recipient</th></tr></thead>
            <tbody>{alerts.data.slice(0, 30).map((a: any) => (
              <tr key={a.id}><td className="text-xs">{fmtDate(a.created_at)}</td><td><Link className="font-mono text-brand-700 dark:text-brand-300 hover:underline" to={`/incidents/${a.incident_id}`}>{a.incident_id}</Link></td><td>{a.risk_level} · {Math.round(a.risk_score)}</td><td>{a.data_status}</td>
                <td><span className={`badge ${a.status === 'sent' ? 'bg-green-100 text-green-800' : a.status === 'failed' ? 'bg-red-100 text-red-800' : 'bg-ink-100 text-ink-700'}`}>{a.status}</span></td><td className="text-xs">{a.status === 'sent' ? a.recipient : a.reason}</td></tr>))}</tbody>
          </table></div>
        )}
      </Section>
      <EventsPage preset={{ risk_level: 'HIGH,CRITICAL', sort: 'risk' }} title="High / Critical Risk Incidents" subtitle="Live HIGH / CRITICAL incidents trigger e-mail alerts (deduplicated); historical HIGH / CRITICAL incidents never do." />
    </div>
  );
}
