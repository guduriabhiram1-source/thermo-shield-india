import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import { Api } from '../services/api';

interface Results { coordinates: { latitude: number; longitude: number } | null; incidents: any[]; places: any[]; facilities: any[]; classifications: any[]; states: any[]; districts: any[] }

export function SearchBox() {
  const [q, setQ] = useState('');
  const [res, setRes] = useState<Results | null>(null);
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (q.trim().length < 2) { setRes(null); return; }
    const t = setTimeout(() => Api.search(q).then((r) => { setRes(r); setOpen(true); }).catch(() => setRes(null)), 250);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);
  const go = (path: string) => { setOpen(false); setQ(''); nav(path); };
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (res?.coordinates) return go(`/location-analysis?lat=${res.coordinates.latitude}&lon=${res.coordinates.longitude}`);
    if (res?.incidents?.length) return go(`/incidents/${res.incidents[0].incident_id}`);
    go(`/incidents?q=${encodeURIComponent(q)}`);
  };
  const row = 'w-full text-left px-3 py-2 hover:bg-ink-50 dark:hover:bg-ink-800';
  return (
    <div ref={box} className="relative">
      <form onSubmit={submit} className="relative">
        <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-400" />
        <input className="input !pl-8" placeholder="Search incident ID, state, district, locality, facility, classification or “16.5062, 80.6480”" value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => res && setOpen(true)} aria-label="Global search" />
      </form>
      {open && res && (
        <div className="absolute z-50 mt-1 w-full card max-h-96 overflow-auto text-sm divide-y divide-ink-100 dark:divide-ink-800">
          {res.coordinates && <button className={row} onClick={() => go(`/location-analysis?lat=${res.coordinates!.latitude}&lon=${res.coordinates!.longitude}`)}>📍 Analyse coordinates {res.coordinates.latitude}, {res.coordinates.longitude}</button>}
          {res.incidents.map((i) => <button key={i.incident_id} className={row} onClick={() => go(`/incidents/${i.incident_id}`)}>🔥 <span className="font-mono">{i.incident_id}</span> · {i.classification_label} · {i.district}, {i.state} · <b>{i.risk_level}</b> · {i.data_status}</button>)}
          {res.states.map((s) => <button key={s.name} className={row} onClick={() => go(`/analytics/state/${encodeURIComponent(s.name)}`)}>🗺️ {s.name} — state analytics</button>)}
          {res.districts.map((d, i) => <button key={`d${i}`} className={row} onClick={() => go(`/incidents?state=${encodeURIComponent(d.state)}&district=${encodeURIComponent(d.name)}`)}>🏙️ {d.name} district, {d.state}</button>)}
          {res.places.map((p, i) => <button key={`p${i}`} className={row} onClick={() => go(`/location-analysis?lat=${p.latitude}&lon=${p.longitude}`)}>🏘️ {p.name} ({p.type}), {p.district}, {p.state}</button>)}
          {res.facilities.map((f, i) => <button key={`f${i}`} className={row} onClick={() => go(`/location-analysis?lat=${f.latitude}&lon=${f.longitude}`)}>🏭 {f.name} ({f.category}), {f.state}</button>)}
          {res.classifications.map((c) => <button key={c.classification} className={row} onClick={() => go(`/incidents?classification=${c.classification}`)}>🏷️ Events classified as {c.label}</button>)}
          {!res.coordinates && !res.incidents.length && !res.places.length && !res.facilities.length && !res.states.length && !res.classifications.length && !res.districts.length && <div className="px-3 py-2 text-ink-500">No matches</div>}
        </div>
      )}
    </div>
  );
}
