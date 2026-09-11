import { useQuery } from '@tanstack/react-query';
import { Api, errorMessage } from '../services/api';
import { ErrorBox, InfoBox, Loading, Section } from '../components/Common';
import { IncidentCard } from '../components/IncidentCard';
import { useAuth } from '../hooks/useAuth';

export default function VerificationPage() {
  const { can, user } = useAuth();
  const q = useQuery({ queryKey: ['verification-queue'], queryFn: Api.verificationQueue });
  if (q.error) return <ErrorBox error={errorMessage(q.error)} />;
  if (!q.data) return <Loading />;
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Human Verification</h1><p className="text-sm text-ink-500">Analysts confirm, correct or mark uncertain each AI inference. Verified records feed the training dataset; nothing is retrained automatically.</p></div>
      {!can('ANALYST') && <InfoBox>Your role ({user?.role}) can view the queue but cannot verify. ANALYST or ADMIN role is required.</InfoBox>}
      <Section title={`Pending (${q.data.pending.length}) — live incidents first`}>{q.data.pending.length === 0 ? <div className="text-sm text-ink-500">Nothing pending.</div> : <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-3">{q.data.pending.map((e) => <IncidentCard key={e.incident_id} e={e} compact />)}</div>}</Section>
      <Section title={`Completed (${q.data.completed.length})`}>{q.data.completed.length === 0 ? <div className="text-sm text-ink-500">No verification recorded yet.</div> : <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-3">{q.data.completed.map((e) => <IncidentCard key={e.incident_id} e={e} compact />)}</div>}</Section>
    </div>
  );
}
