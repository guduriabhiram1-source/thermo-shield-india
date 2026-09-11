import { classColor, persistenceLabel, riskBadgeClass } from '../utils/format';

export function RiskBadge({ level, score }: { level: string; score?: number }) {
  return <span className={`badge ${riskBadgeClass[level] ?? 'bg-ink-100 text-ink-700'}`}>{level}{score !== undefined ? ` · ${Math.round(score)}` : ''}</span>;
}

export function ClassBadge({ classification, label }: { classification: string; label?: string }) {
  return <span className="badge text-white" style={{ backgroundColor: classColor[classification] ?? '#64748b' }}>{label ?? classification.replace(/_/g, ' ')}</span>;
}

export function PersistenceBadge({ cls, score }: { cls: string; score?: number }) {
  const color = cls === 'PERSISTENT' ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300' : cls === 'RECURRING' ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300' : 'bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-300';
  return <span className={`badge ${color}`}>{persistenceLabel[cls] ?? cls}{score !== undefined ? ` · ${Math.round(score)}/100` : ''}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    PENDING: 'bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-300', VERIFIED: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300', CORRECTED: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
    UNCERTAIN: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300', ACTIVE: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300', INACTIVE: 'bg-ink-100 text-ink-600 dark:bg-ink-800 dark:text-ink-400',
    CLOSED: 'bg-ink-100 text-ink-600', PREDICTED: 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300', INSUFFICIENT_EVIDENCE: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
  };
  return <span className={`badge ${map[status] ?? 'bg-ink-100 text-ink-700'}`}>{status.replace(/_/g, ' ')}</span>;
}

export function DataStatusBadge({ status, big = false }: { status: 'LIVE' | 'HISTORICAL' | string; big?: boolean }) {
  const live = status === 'LIVE';
  return <span className={`${live ? 'live-tag' : 'hist-tag'} ${big ? 'text-sm px-3 py-1' : ''}`} title={live ? 'Newly observed within the live window' : 'Historical observation (≤ 12 months)'}>{live ? '🟢 LIVE DATA' : '🔵 HISTORICAL DATA'}</span>;
}

export function OriginTag({ kind }: { kind: 'OBSERVED' | 'MODEL' | 'ESTIMATE' | 'HUMAN' | 'CALCULATED' | 'UNAVAILABLE'; }) {
  const map: Record<string, string> = {
    OBSERVED: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300', MODEL: 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300', CALCULATED: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300',
    ESTIMATE: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300', HUMAN: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300', UNAVAILABLE: 'bg-ink-100 text-ink-500 dark:bg-ink-800 dark:text-ink-400',
  };
  const title: Record<string, string> = { OBSERVED: 'Directly obtained from a data source', MODEL: 'AI / rule inference', CALCULATED: 'Derived from observed data by documented formulas', ESTIMATE: 'Calculated approximation', HUMAN: 'Human-verified information', UNAVAILABLE: 'No data from any source' };
  return <span className={`badge ${map[kind]}`} title={title[kind]}>{kind === 'MODEL' ? 'MODEL INFERENCE' : kind === 'HUMAN' ? 'HUMAN VERIFIED' : kind}</span>;
}

export function ExposureBadge({ level }: { level: string }) {
  const map: Record<string, string> = { LOW: riskBadgeClass.LOW, MODERATE: riskBadgeClass.MEDIUM, HIGH: riskBadgeClass.HIGH, CRITICAL: riskBadgeClass.CRITICAL, UNAVAILABLE: riskBadgeClass.UNAVAILABLE };
  return <span className={`badge ${map[level] ?? riskBadgeClass.UNAVAILABLE}`}>{level}</span>;
}
