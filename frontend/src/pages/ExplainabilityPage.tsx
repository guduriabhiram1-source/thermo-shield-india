import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Api, errorMessage } from '../services/api';
import { ErrorBox, InfoBox, KV, Loading, Section } from '../components/Common';
import { HorizontalBars } from '../charts/DashboardCharts';
import { useAuth } from '../hooks/useAuth';
import { fmtDate, titleCase } from '../utils/format';

export default function ExplainabilityPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const m = useQuery({ queryKey: ['model'], queryFn: Api.model });
  const ds = useQuery({ queryKey: ['training-dataset'], queryFn: Api.trainingDataset });
  const train = useMutation({ mutationFn: () => Api.train({}), onSuccess: (r) => { setMsg(r.message); qc.invalidateQueries({ queryKey: ['model'] }); }, onError: (e) => setMsg(errorMessage(e)) });
  const promote = useMutation({ mutationFn: (v: string) => Api.promoteModel(v), onSuccess: (r) => { setMsg(r.message); qc.invalidateQueries({ queryKey: ['model'] }); }, onError: (e) => setMsg(errorMessage(e)) });
  if (m.error) return <ErrorBox error={errorMessage(m.error)} />;
  if (!m.data) return <Loading />;
  const d = m.data;
  const imp = Object.entries(d.production?.feature_importance ?? {}).map(([k, v]) => ({ name: d.feature_labels[k] ?? k, value: v as number }));
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-extrabold tracking-tight">AI Explainability</h1><p className="text-sm text-ink-500">LightGBM + SHAP architecture. Models train only on human-verified samples and are promoted only by an explicit ADMIN action after validation.</p></div>
      {!d.ml_model_available && <InfoBox tone="warn"><b>{d.status_message}</b> Every incident still shows a full classification, probability distribution, evidence and a documented contribution table — labelled as rule-based, not SHAP.</InfoBox>}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Section title="Production model">
          {d.ml_model_available ? <KV items={[['Version', d.production.version], ['Algorithm', d.production.algorithm], ['Training date', fmtDate(d.production.trained_at)], ['Training samples (human-verified)', d.production.training_samples], ['Accuracy', d.production.metrics?.accuracy], ['Precision (macro)', d.production.metrics?.precision_macro], ['Recall (macro)', d.production.metrics?.recall_macro], ['F1 (macro)', d.production.metrics?.f1_macro], ['Validation dataset', `${d.production.validation_dataset?.test_sample_ids?.length ?? 0} held-out verified samples`], ['Promoted at', fmtDate(d.production.promoted_at)]]} />
            : <KV items={[['Status', 'ML model unavailable — insufficient validated training data'], ['Active method', 'Rule-based attribution (documented weights on observed features)'], ['Verified samples available', d.training_dataset.total], ['Classes with ≥ 5 samples', d.training_dataset.classes_with_5plus], ['Required', `≥ ${d.training_dataset.min_total} samples across ≥ ${d.training_dataset.min_classes} classes`]]} />}
          <p className="text-xs text-ink-500 mt-2">{d.policy}</p>
        </Section>
        <Section title="Feature importance (gain)">{imp.length ? <HorizontalBars data={imp} nameKey="name" valueKey="value" color="#8b5cf6" valueName="Importance" height={340} /> : <div className="text-sm text-ink-500">Unavailable — no production model.</div>}</Section>
      </div>
      <Section title="Verified training dataset" right={can('ADMIN') ? <button className="btn-primary text-xs" onClick={() => train.mutate()} disabled={train.isPending}>{train.isPending ? 'Training…' : 'Train candidate model (ADMIN)'}</button> : undefined}>
        {msg && <div className="text-xs mb-2">{msg}</div>}
        {ds.data ? <><div className="text-sm mb-2">{ds.data.total} verified samples · by label: {ds.data.by_label.map((b: any) => `${b.label_name} ${b.count}`).join(', ') || 'none'}</div>
          {ds.data.items.length > 0 && <div className="overflow-x-auto max-h-80"><table className="table"><thead><tr><th>Incident</th><th>Verified label</th><th>Analyst</th><th>When</th><th>Model at prediction</th></tr></thead><tbody>{ds.data.items.slice(0, 50).map((s: any) => <tr key={s.id}><td className="font-mono text-xs">{s.incident_id}</td><td>{s.label_name}</td><td className="text-xs">{s.analyst}</td><td className="text-xs">{fmtDate(s.verification_timestamp)}</td><td className="text-xs">{s.model_version || '—'}</td></tr>)}</tbody></table></div>}</> : <Loading />}
      </Section>
      <Section title="Model registry (candidates and production)">
        {d.registry.length === 0 ? <div className="text-sm text-ink-500">No model trained yet.</div> : <div className="overflow-x-auto"><table className="table"><thead><tr><th>Version</th><th>Trained</th><th>Samples</th><th>Accuracy</th><th>F1</th><th>Validated</th><th>Production</th><th></th></tr></thead>
          <tbody>{d.registry.map((r: any) => <tr key={r.version}><td className="font-mono text-xs">{r.version}</td><td className="text-xs">{fmtDate(r.training_date)}</td><td>{r.training_samples}</td><td>{r.accuracy}</td><td>{r.f1}</td><td>{r.validated ? 'yes' : 'no'}</td><td>{r.is_production ? 'yes' : '—'}</td><td>{can('ADMIN') && r.validated && !r.is_production && <button className="btn-secondary text-xs" onClick={() => promote.mutate(r.version)}>Promote</button>}</td></tr>)}</tbody></table></div>}
      </Section>
      <Section title="Feature set (28 features)"><div className="flex flex-wrap gap-1">{d.features.map((f: string) => <span key={f} className="badge bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-300 normal-case tracking-normal">{d.feature_labels[f] ?? titleCase(f)}</span>)}</div></Section>
    </div>
  );
}
