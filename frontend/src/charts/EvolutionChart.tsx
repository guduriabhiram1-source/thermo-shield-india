import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { Evolution } from '../types';
import { useChartColors } from '../themes/ThemeContext';

export function EvolutionChart({ evo, height = 260 }: { evo: Evolution; height?: number }) {
  const c = useChartColors();
  const data = evo.series.map((s) => ({ ...s, day: s.day.slice(5), brightness_c: Math.round((s.max_brightness - 273.15) * 10) / 10 }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" /><XAxis dataKey="day" stroke={c.axis} fontSize={11} />
        <YAxis yAxisId="l" stroke={c.axis} fontSize={11} label={{ value: 'FRP (MW)', angle: -90, position: 'insideLeft', fill: c.axis, fontSize: 10 }} /><YAxis yAxisId="r" orientation="right" stroke={c.axis} fontSize={11} />
        <Tooltip contentStyle={{ background: c.tooltipBg, borderColor: c.tooltipBorder, color: c.text, borderRadius: 8 }} labelStyle={{ color: c.text }} /><Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar yAxisId="r" dataKey="detections" name="Detections / day" fill="#93c5fd" opacity={0.7} radius={[3, 3, 0, 0]} />
        <Line yAxisId="l" type="monotone" dataKey="max_frp" name="Peak FRP (MW)" stroke="#ef4444" strokeWidth={2.5} dot={{ r: 3 }} />
        <Line yAxisId="l" type="monotone" dataKey="brightness_c" name="Peak brightness (°C)" stroke="#f59e0b" strokeDasharray="5 3" dot={false} />
        <Line yAxisId="r" type="monotone" dataKey="spread_km" name="Spread (km)" stroke="#8b5cf6" dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
