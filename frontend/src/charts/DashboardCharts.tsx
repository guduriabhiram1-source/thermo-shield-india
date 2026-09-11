import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useChartColors } from '../themes/ThemeContext';
import { classColor, riskColor } from '../utils/format';

const tip = (c: ReturnType<typeof useChartColors>) => ({ contentStyle: { background: c.tooltipBg, borderColor: c.tooltipBorder, color: c.text, borderRadius: 8 }, labelStyle: { color: c.text } });

export function EventsByStateChart({ data, height = 280 }: { data: { state: string; count: number }[]; height?: number }) {
  const c = useChartColors();
  if (!data.length) return <div className="text-xs text-ink-500 py-6 text-center">No events in the selected range.</div>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data.slice(0, 15)} margin={{ top: 4, right: 8, left: -12, bottom: 60 }}>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" vertical={false} /><XAxis dataKey="state" stroke={c.axis} fontSize={10} angle={-40} textAnchor="end" interval={0} /><YAxis stroke={c.axis} fontSize={10} allowDecimals={false} />
        <Tooltip {...tip(c)} /><Bar dataKey="count" name="Events" fill="#f43f5e" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function EventsOverTimeChart({ data, height = 260 }: { data: { day: string; new_events: number; detections: number; frp: number }[]; height?: number }) {
  const c = useChartColors();
  const d = data.map((x) => ({ ...x, day: x.day.slice(5) }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={d} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
        <defs><linearGradient id="gFrp" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#f97316" stopOpacity={0.6} /><stop offset="100%" stopColor="#f97316" stopOpacity={0.05} /></linearGradient></defs>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" /><XAxis dataKey="day" stroke={c.axis} fontSize={10} interval="preserveStartEnd" /><YAxis yAxisId="l" stroke={c.axis} fontSize={10} /><YAxis yAxisId="r" orientation="right" stroke={c.axis} fontSize={10} />
        <Tooltip {...tip(c)} /><Legend wrapperStyle={{ fontSize: 11 }} />
        <Area yAxisId="l" type="monotone" dataKey="frp" name="Total FRP (MW)" stroke="#f97316" fill="url(#gFrp)" />
        <Area yAxisId="r" type="monotone" dataKey="detections" name="Detections" stroke="#0ea5e9" fill="#0ea5e9" fillOpacity={0.15} />
        <Area yAxisId="r" type="step" dataKey="new_events" name="New events" stroke="#f43f5e" fill="#f43f5e" fillOpacity={0.15} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function ClassificationPie({ data, height = 260 }: { data: { classification: string; label: string; count: number }[]; height?: number }) {
  const c = useChartColors();
  if (!data.length) return <div className="text-xs text-ink-500 py-6 text-center">No events in the selected range.</div>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={data} dataKey="count" nameKey="label" innerRadius={55} outerRadius={95} paddingAngle={2}>{data.map((d) => <Cell key={d.classification} fill={classColor[d.classification] ?? '#64748b'} />)}</Pie>
        <Tooltip {...tip(c)} /><Legend wrapperStyle={{ fontSize: 10 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function RiskDistributionChart({ data, height = 220 }: { data: { level: string; count: number }[]; height?: number }) {
  const c = useChartColors();
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" vertical={false} /><XAxis dataKey="level" stroke={c.axis} fontSize={10} /><YAxis stroke={c.axis} fontSize={10} allowDecimals={false} />
        <Tooltip {...tip(c)} /><Bar dataKey="count" name="Events" radius={[4, 4, 0, 0]}>{data.map((d) => <Cell key={d.level} fill={riskColor[d.level]} />)}</Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function HorizontalBars({ data, nameKey, valueKey, color = '#8b5cf6', height = 260, valueName = 'Value', emptyText = 'No data in the selected range.' }: { data: any[]; nameKey: string; valueKey: string; color?: string; height?: number; valueName?: string; emptyText?: string }) {
  const c = useChartColors();
  if (!data.length) return <div className="text-xs text-ink-500 py-6 text-center">{emptyText}</div>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" horizontal={false} /><XAxis type="number" stroke={c.axis} fontSize={10} /><YAxis type="category" dataKey={nameKey} width={150} stroke={c.axis} fontSize={10} />
        <Tooltip {...tip(c)} formatter={(v: number) => [v.toLocaleString('en-IN'), valueName]} /><Bar dataKey={valueKey} fill={color} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
