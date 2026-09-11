export const UNAVAILABLE = 'Unavailable';
export const fmtNum = (n: number | null | undefined, digits = 0) => (n === null || n === undefined || Number.isNaN(n) ? UNAVAILABLE : n.toLocaleString('en-IN', { maximumFractionDigits: digits, minimumFractionDigits: digits }));
export const fmtPct = (n: number | null | undefined, digits = 0) => (n === null || n === undefined ? UNAVAILABLE : `${(n * 100).toFixed(digits)}%`);
export const fmtDate = (iso: string | null | undefined) => {
  if (!iso) return UNAVAILABLE;
  return new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata', hour12: false }) + ' IST';
};
export const fmtDateUtc = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', hour12: false }) + ' UTC' : UNAVAILABLE);
export const fmtDay = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }) : UNAVAILABLE);
export const fmtKm = (n: number | null | undefined) => (n === null || n === undefined ? UNAVAILABLE : `${n.toFixed(n < 10 ? 1 : 0)} km`);
export const fmtCoord = (lat: number, lon: number) => `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
export const titleCase = (s: string) => s.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
export const riskColor: Record<string, string> = { LOW: '#22c55e', MODERATE: '#a3e635', MEDIUM: '#eab308', HIGH: '#f97316', CRITICAL: '#ef4444' };
export const riskBadgeClass: Record<string, string> = {
  LOW: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300', MODERATE: 'bg-lime-100 text-lime-800 dark:bg-lime-900/40 dark:text-lime-300',
  MEDIUM: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300', HIGH: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300',
  CRITICAL: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300', UNAVAILABLE: 'bg-ink-100 text-ink-500 dark:bg-ink-800 dark:text-ink-400',
};
export const classColor: Record<string, string> = {
  INDUSTRIAL_FIRE: '#ef4444', PERSISTENT_INDUSTRIAL_HEAT: '#f97316', WILDFIRE: '#16a34a', AGRICULTURAL_BURN: '#ca8a04', GAS_FLARE: '#db2777', REFINERY_ACTIVITY: '#7c3aed',
  POWER_PLANT_ACTIVITY: '#0ea5e9', MINING_ACTIVITY: '#a16207', OTHER_THERMAL_SOURCE: '#64748b', UNKNOWN: '#94a3b8',
};
export const CLASSES = ['INDUSTRIAL_FIRE', 'PERSISTENT_INDUSTRIAL_HEAT', 'WILDFIRE', 'AGRICULTURAL_BURN', 'GAS_FLARE', 'REFINERY_ACTIVITY', 'POWER_PLANT_ACTIVITY', 'MINING_ACTIVITY', 'OTHER_THERMAL_SOURCE', 'UNKNOWN'];
export const RISKS = ['LOW', 'MODERATE', 'MEDIUM', 'HIGH', 'CRITICAL'];
export const PERSISTENCE = ['ISOLATED', 'TEMPORARY', 'RECURRING', 'PERSISTENT'];
export const persistenceLabel: Record<string, string> = { ISOLATED: 'Isolated', TEMPORARY: 'Temporary', RECURRING: 'Recurring', PERSISTENT: 'Persistent source' };
export const trendArrow = (t: string) => (t === 'INCREASING' ? '↑ Risk Increasing' : t === 'DECREASING' ? '↓ Risk Decreasing' : '→ Stable');
export const trendClass = (t: string) => (t === 'INCREASING' ? 'text-red-600 dark:text-red-400' : t === 'DECREASING' ? 'text-green-600 dark:text-green-400' : 'text-ink-500');

export function markerColor(e: { risk_level: string; persistence_class: string; classification: string; data_status?: string }) {
  if (e.classification === 'UNKNOWN') return '#cbd5e1';
  if (e.risk_level === 'CRITICAL') return '#a21caf';
  if (e.risk_level === 'HIGH') return '#ef4444';
  if (e.persistence_class === 'PERSISTENT') return '#f97316';
  if (e.risk_level === 'MEDIUM' || e.risk_level === 'MODERATE') return '#eab308';
  return '#22c55e';
}
