import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { ContribRow } from '../types';
import { useChartColors } from '../themes/ThemeContext';

export function ContributionChart({ rows, shap, height = 300 }: { rows: ContribRow[]; shap: boolean; height?: number }) {
  const c = useChartColors();
  const data = rows.slice(0, 10).map((r) => ({ name: r.description, v: r.contribution }));
  if (!data.length) return <div className="text-xs text-ink-500">Contribution values unavailable.</div>;
  const unit = shap ? 'log-odds' : 'rule weight';
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 30, left: 8, bottom: 0 }}>
        <XAxis type="number" stroke={c.axis} fontSize={10} tickFormatter={(v) => (v > 0 ? `+${v}` : `${v}`)} /><YAxis type="category" dataKey="name" width={210} stroke={c.axis} fontSize={10} /><ReferenceLine x={0} stroke={c.axis} />
        <Tooltip contentStyle={{ background: c.tooltipBg, borderColor: c.tooltipBorder, color: c.text, borderRadius: 8 }} formatter={(v: number) => [`${v > 0 ? '+' : ''}${v.toFixed(3)} ${unit}`, shap ? 'SHAP contribution' : 'Rule contribution']} />
        <Bar dataKey="v" radius={[0, 4, 4, 0]} label={{ position: 'right', fontSize: 10, fill: c.text, formatter: (v: number) => (v > 0 ? `+${v.toFixed(2)}` : v.toFixed(2)) }}>{data.map((d, i) => <Cell key={i} fill={d.v > 0 ? '#ef4444' : '#3b82f6'} />)}</Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ProbabilityBars({ probs, labels }: { probs: Record<string, number>; labels: Record<string, string> }) {
  const rows = Object.entries(probs).sort((a, b) => b[1] - a[1]).slice(0, 6);
  return (
    <div className="space-y-1.5">
      {rows.map(([k, p]) => (
        <div key={k} className="text-xs">
          <div className="flex justify-between"><span>{labels[k] ?? k}</span><span className="font-semibold">{(p * 100).toFixed(1)}%</span></div>
          <div className="h-1.5 rounded bg-ink-100 dark:bg-ink-800 overflow-hidden"><div className="h-full bg-brand-500" style={{ width: `${Math.max(1, p * 100)}%` }} /></div>
        </div>
      ))}
    </div>
  );
}
