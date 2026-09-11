import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Api } from '../services/api';
import { fmtDate, fmtNum } from '../utils/format';

export function NotificationBell() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const { data } = useQuery({ queryKey: ['notifications'], queryFn: Api.notifications, refetchInterval: 60_000 });
  useEffect(() => {
    const h = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);
  const items = data?.items ?? [];
  const unread = items.filter((i) => !i.acknowledged).length;
  return (
    <div ref={box} className="relative">
      <button className="btn-ghost p-2 relative" onClick={() => setOpen((o) => !o)} title="Live alerts" aria-label="Notifications">
        <Bell size={18} />
        {unread > 0 && <span className="absolute -top-0.5 -right-0.5 h-4 min-w-4 px-1 rounded-full bg-brand-600 text-white text-[10px] font-bold grid place-items-center">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-96 max-w-[90vw] card z-50 max-h-[70vh] overflow-auto">
          <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-ink-500 border-b border-ink-200 dark:border-ink-800">Live high-risk thermal events</div>
          {items.length === 0 && <div className="p-3 text-sm text-ink-500">No live HIGH / CRITICAL alerts.</div>}
          {items.slice(0, 20).map((n) => (
            <div key={n.id} className={`p-3 border-b border-ink-100 dark:border-ink-800 text-xs ${n.acknowledged ? 'opacity-60' : ''}`}>
              <div className="font-semibold text-red-700 dark:text-red-300">🚨 LIVE {n.severity}-RISK THERMAL EVENT</div>
              <div className="mt-1 text-ink-700 dark:text-ink-200">{n.message}</div>
              <div className="mt-1 grid grid-cols-2 gap-x-3 text-[11px] text-ink-500">
                <span>Risk {Math.round(n.payload?.risk ?? 0)}/100 · {n.payload?.confidence != null ? Math.round(n.payload.confidence * 100) + '%' : 'conf. unavailable'}</span>
                <span>Exposure: {n.payload?.population_exposure != null ? '≈ ' + fmtNum(n.payload.population_exposure) + ' (est.)' : 'Unavailable'}</span>
                <span>Wind: {n.payload?.wind ? `${n.payload.wind.direction_from} ${n.payload.wind.speed_kmh} km/h` : 'Unavailable'}</span>
                <span>{fmtDate(n.created_at)}</span>
              </div>
              <div className="mt-1.5 flex gap-2">
                <Link to={`/incidents/${n.incident_id}`} className="text-brand-600 font-semibold hover:underline" onClick={() => setOpen(false)}>Open incident</Link>
                {!n.acknowledged && <button className="text-ink-500 hover:underline" onClick={() => Api.ackNotification(n.id).then(() => qc.invalidateQueries({ queryKey: ['notifications'] }))}>Acknowledge</button>}
              </div>
            </div>
          ))}
          {data && <div className="p-2 text-[10px] text-ink-500 leading-snug">{data.live_notice}</div>}
        </div>
      )}
    </div>
  );
}
