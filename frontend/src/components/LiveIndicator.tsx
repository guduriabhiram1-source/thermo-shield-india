import { useQuery } from '@tanstack/react-query';
import { Api } from '../services/api';
import { fmtDate } from '../utils/format';

export function LiveIndicator() {
  const { data } = useQuery({ queryKey: ['dashboard-live'], queryFn: () => Api.dashboard({ range: 'live' }), refetchInterval: 120_000 });
  if (!data) return null;
  const stale = data.live.is_stale;
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs" data-testid="live-indicator">
      <span className={`inline-flex items-center gap-1.5 font-semibold ${stale ? 'text-amber-600 dark:text-amber-400' : 'text-green-700 dark:text-green-400'}`}>
        <span className={`h-2 w-2 rounded-full ${stale ? 'bg-amber-500' : 'bg-green-500 animate-pulse'}`} />
        {stale ? 'LIVE FEED STALE' : 'LIVE DATA'}
      </span>
      <span className="text-ink-500">Last live observation: {data.live.latest_observation_ist ?? 'no live observation yet'}</span>
      <span className="text-ink-500">Historical: {data.history_window.label}</span>
    </div>
  );
}
