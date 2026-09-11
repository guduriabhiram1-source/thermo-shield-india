import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { RiskComponent, RiskHistory } from '../types';
import { useChartColors } from '../themes/ThemeContext';
import { fmtDay } from '../utils/format';

export function RiskHistoryChart({ history, height = 220 }: { history: RiskHistory[]; height?: number }) {
  const c = useChartColors();
  const data = history.map((h) => ({ t: new Date(h.computed_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }), score: h.score, level: h.level }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" />
        <ReferenceArea y1={0} y2={20} fill={c.risk.LOW} fillOpacity={0.08} /><ReferenceArea y1={20} y2={40} fill={c.risk.MODERATE} fillOpacity={0.08} /><ReferenceArea y1={40} y2={60} fill={c.risk.MEDIUM} fillOpacity={0.08} />
        <ReferenceArea y1={60} y2={80} fill={c.risk.HIGH} fillOpacity={0.08} /><ReferenceArea y1={80} y2={100} fill={c.risk.CRITICAL} fillOpacity={0.08} />
        <XAxis dataKey="t" stroke={c.axis} fontSize={10} /><YAxis domain={[0, 100]} stroke={c.axis} fontSize={11} />
        <Tooltip contentStyle={{ background: c.tooltipBg, borderColor: c.tooltipBorder, color: c.text, borderRadius: 8 }} labelStyle={{ color: c.text }} />
        <Line type="monotone" dataKey="score" name="Risk score" stroke="#ef4444" strokeWidth={2.5} dot={{ r: 4 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function RiskComponentsChart({ breakdown, height = 260 }: { breakdown: Record<string, any>; height?: number }) {
  const c = useChartColors();
  const data = Object.values(breakdown).filter((v): v is RiskComponent => typeof v === 'object' && v !== null && !Array.isArray(v) && 'points' in v).map((v) => ({ name: v.label, points: v.points, max: v.weight })).sort((a, b) => b.points - a.points);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" horizontal={false} /><XAxis type="number" stroke={c.axis} fontSize={10} /><YAxis type="category" dataKey="name" width={170} stroke={c.axis} fontSize={10} />
        <Tooltip contentStyle={{ background: c.tooltipBg, borderColor: c.tooltipBorder, color: c.text, borderRadius: 8 }} formatter={(v: number, _n, p: any) => [`${v} / ${p.payload.max} pts`, 'Contribution']} />
        <Bar dataKey="points" radius={[0, 4, 4, 0]}>{data.map((d, i) => <Cell key={i} fill={d.points / d.max > 0.66 ? '#ef4444' : d.points / d.max > 0.33 ? '#f97316' : '#22c55e'} />)}</Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DayRiskSeries({ series, height = 160 }: { series: { day: string; risk_score: number | null }[]; height?: number }) {
  const c = useChartColors();
  const data = series.filter((s) => s.risk_score != null && s.risk_score > 0).map((s) => ({ day: fmtDay(s.day), risk: s.risk_score }));
  if (!data.length) return <div className="text-xs text-ink-500">No per-day risk snapshots yet.</div>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}><CartesianGrid stroke={c.grid} strokeDasharray="3 3" /><XAxis dataKey="day" stroke={c.axis} fontSize={10} /><YAxis domain={[0, 100]} stroke={c.axis} fontSize={10} />
        <Tooltip contentStyle={{ background: c.tooltipBg, borderColor: c.tooltipBorder, color: c.text, borderRadius: 8 }} /><Line type="monotone" dataKey="risk" stroke="#f97316" strokeWidth={2} /></LineChart>
    </ResponsiveContainer>
  );
}
