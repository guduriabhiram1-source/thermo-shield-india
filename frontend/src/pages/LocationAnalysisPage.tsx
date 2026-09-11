import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CircleMarker, MapContainer, Marker, Popup, Tooltip } from 'react-leaflet';
import L from 'leaflet';
import { Crosshair } from 'lucide-react';
import { Api, errorMessage } from '../services/api';
import { ErrorBox, KV, Loading, Section, Unavailable } from '../components/Common';
import { BaseLayers, ClickCapture } from '../maps/IndiaMap';
import { DataStatusBadge, OriginTag, RiskBadge } from '../components/Badges';
import { fmtDate, fmtNum, titleCase } from '../utils/format';

const pin = L.divIcon({ className: '', html: '<div style="width:16px;height:16px;border-radius:50%;background:#dc2626;border:3px solid #fff;box-shadow:0 0 0 2px #dc2626"></div>', iconSize: [16, 16], iconAnchor: [8, 8] });

export default function LocationAnalysisPage() {
  const [params, setParams] = useSearchParams();
  const [lat, setLat] = useState(params.get('lat') ?? '16.5062');
  const [lon, setLon] = useState(params.get('lon') ?? '80.6480');
  const [radius, setRadius] = useState('25');
  const active = params.get('lat') && params.get('lon') ? { lat: Number(params.get('lat')), lon: Number(params.get('lon')) } : null;
  const q = useQuery({ queryKey: ['location', active, radius], queryFn: () => Api.location(active!.lat, active!.lon, Number(radius), true), enabled: !!active });
  const run = (la = lat, lo = lon) => { setLat(la); setLon(lo); setParams({ lat: la, lon: lo }); };
  const d = q.data;
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Coordinate Analysis</h1><p className="text-sm text-ink-500">Latitude / longitude → FIRMS observations, locality, district, state, nearby facilities, land cover, population, historical activity (12 months), live activity, weather, wind and risk. Click the map to move the point.</p></div>
      <div className="card p-3 flex flex-wrap items-end gap-2">
        <label className="text-xs"><span className="label">Latitude</span><input className="input !w-36" value={lat} onChange={(e) => setLat(e.target.value)} aria-label="Latitude" /></label>
        <label className="text-xs"><span className="label">Longitude</span><input className="input !w-36" value={lon} onChange={(e) => setLon(e.target.value)} aria-label="Longitude" /></label>
        <label className="text-xs"><span className="label">Radius (km)</span><input className="input !w-24" type="number" min={1} max={100} value={radius} onChange={(e) => setRadius(e.target.value)} /></label>
        <button className="btn-primary" onClick={() => run()}><Crosshair size={15} /> Analyze</button>
        {d && <span className="text-xs text-ink-500">Analysed {fmtDate(d.query.analysed_at)} · {d.query.in_india ? 'inside India outline' : 'outside India outline'}</span>}
      </div>
      <div className="card p-2"><div className="h-[380px]">
        <MapContainer center={active ? [active.lat, active.lon] : [22.5, 80.5]} zoom={active ? 10 : 5} style={{ height: '100%', width: '100%' }} className="rounded-xl z-0">
          <BaseLayers /><ClickCapture onClick={(la, lo) => run(la.toFixed(5), lo.toFixed(5))} />
          {active && <Marker position={[active.lat, active.lon]} icon={pin}><Tooltip permanent direction="top">Query point</Tooltip></Marker>}
          {d?.live_events.map((e: any) => <CircleMarker key={e.incident_id} center={[e.latitude, e.longitude]} radius={7} pathOptions={{ color: '#111', fillColor: '#ef4444', fillOpacity: 0.9 }}><Popup><Link to={`/incidents/${e.incident_id}`}>{e.incident_id}</Link> · {e.risk_level} · LIVE</Popup></CircleMarker>)}
          {d?.historical_events.map((e: any) => <CircleMarker key={e.incident_id} center={[e.latitude, e.longitude]} radius={6} pathOptions={{ color: '#64748b', dashArray: '2 2', fillColor: '#0ea5e9', fillOpacity: 0.7 }}><Popup><Link to={`/incidents/${e.incident_id}`}>{e.incident_id}</Link> · {e.risk_level} · HISTORICAL</Popup></CircleMarker>)}
          {d?.recent_detections_30d.slice(0, 200).map((x: any) => <CircleMarker key={x.id} center={[x.latitude, x.longitude]} radius={3} pathOptions={{ color: '#7f1d1d', fillColor: '#f59e0b', fillOpacity: 0.8 }}><Tooltip>{x.acq_date} {x.acq_time}Z · FRP {x.frp} MW · {x.data_status}</Tooltip></CircleMarker>)}
        </MapContainer></div></div>
      {q.error && <ErrorBox error={errorMessage(q.error)} />}
      {q.isLoading && active && <Loading text="Running coordinate intelligence pipeline (Nominatim, Overpass, Open-Meteo)…" />}
      {d && (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
          <Section title="Location" right={<OriginTag kind="OBSERVED" />}><KV items={[['State', d.location.state], ['District', d.location.district], ['Nearest locality', d.location.locality ? `${d.location.locality} (${d.location.locality_type || 'place'}${d.location.locality_distance_km ? `, ${d.location.locality_distance_km} km ${d.location.locality_direction}` : ''})` : null], ['Road (OSM)', d.location.road], ['Geocoder', d.location.provider], ['Nearest OSM district centre', d.nearest_district_centre ? `${d.nearest_district_centre.name} (${d.nearest_district_centre.distance_km} km)` : null], ['Districts in state', d.district_candidates.length]]} /></Section>
          <Section title="Risk snapshot & weather" right={<OriginTag kind="ESTIMATE" />}>
            <div className="flex items-center gap-3 mb-2"><span className="text-3xl font-extrabold">{Math.round(d.risk.score)}</span><RiskBadge level={d.risk.level} /></div><p className="text-xs text-ink-500 mb-3">{d.risk.basis}</p>
            {d.weather.available ? <KV items={[['Wind', `${d.weather.wind_speed_kmh} km/h from ${d.weather.wind_direction_compass}`], ['Temperature / humidity', `${d.weather.temperature_c} °C / ${d.weather.humidity_pct} %`], ['Weather time', fmtDate(d.weather.weather_timestamp)], ['Source', d.weather.weather_source]]} /> : <div className="text-sm">Weather data unavailable — {d.weather.reason}</div>}
          </Section>
          <Section title="Land cover & population" right={<OriginTag kind="ESTIMATE" />}>
            <KV items={[['Land cover', d.land_cover.available ? `${d.land_cover.label} [${d.land_cover.provenance}]` : null], ['Basis', d.land_cover.basis?.join('; ')], ['Local density', d.density.available ? `${fmtNum(d.density.density_per_km2)} /km² (${d.density.basis})` : null], ['Population within radius (est.)', `≈ ${fmtNum(d.population.total_estimate)} (settlements ${fmtNum(d.population.settlement_population)}, background ${d.population.background_population === null ? 'unavailable' : fmtNum(d.population.background_population)})`]]} />
          </Section>
          <Section title="Nearby facilities & infrastructure" className="xl:col-span-3" right={<OriginTag kind="OBSERVED" />}>
            <div className="text-xs text-ink-500 mb-2">{d.gis.provider} · OSM live: {d.gis.osm_live_status}</div>
            <ul className="text-sm space-y-1 mb-3">{d.gis.summary.map((s: string, i: number) => <li key={i}>• {s}</li>)}</ul>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <table className="table"><thead><tr><th>Facility</th><th>Type</th><th>Distance</th><th>Source</th></tr></thead><tbody>{[...d.gis.refineries, ...d.gis.power_plants, ...d.gis.mines, ...d.gis.gas_facilities, ...d.gis.industrial_facilities].sort((a: any, b: any) => a.distance_km - b.distance_km).slice(0, 12).map((f: any, i: number) => <tr key={i}><td>{f.name}</td><td>{titleCase(f.category)}</td><td>{f.distance_km} km {f.direction}</td><td>{f.source}</td></tr>)}</tbody></table>
              <table className="table"><thead><tr><th>Settlement</th><th>Type</th><th>Distance</th><th>Population</th></tr></thead><tbody>{d.gis.settlements.slice(0, 12).map((s: any, i: number) => <tr key={i}><td>{s.name}</td><td>{s.type}</td><td>{s.distance_km} km {s.direction}</td><td>{s.population === null ? <Unavailable /> : fmtNum(s.population)}</td></tr>)}</tbody></table>
            </div>
          </Section>
          <Section title={`Live thermal activity (${d.live_events.length})`}>{d.live_events.length === 0 ? <div className="text-sm text-ink-500">No live event within {radius} km.</div> : <ul className="text-sm space-y-1">{d.live_events.map((e: any) => <li key={e.incident_id}><Link className="font-mono text-brand-700 hover:underline" to={`/incidents/${e.incident_id}`}>{e.incident_id}</Link> · {e.classification_label} · <RiskBadge level={e.risk_level} /> · {e.distance_km} km {e.direction} <DataStatusBadge status="LIVE" /></li>)}</ul>}</Section>
          <Section title={`Historical thermal activity, 12 months (${d.historical_events.length + d.historical_archive.length})`}>{d.historical_events.length + d.historical_archive.length === 0 ? <div className="text-sm text-ink-500">No historical event within {radius} km in the last 12 months.</div> : <ul className="text-sm space-y-1">{d.historical_events.map((e: any) => <li key={e.incident_id}><Link className="font-mono text-brand-700 hover:underline" to={`/incidents/${e.incident_id}`}>{e.incident_id}</Link> · {e.classification_label} · {e.risk_level} · {fmtDate(e.last_detected_at)} · {e.distance_km} km</li>)}{d.historical_archive.map((h: any, i: number) => <li key={i}>{h.incident_id || 'archived'} · {titleCase(h.classification)} · {fmtDate(h.last_detected_at)} · {h.distance_km} km</li>)}</ul>}</Section>
          <Section title={`FIRMS observations within radius, last 30 days (${d.recent_detections_30d.length})`}>{d.recent_detections_30d.length === 0 ? <div className="text-sm text-ink-500">No FIRMS detection within {radius} km in the last 30 days.</div> : <div className="max-h-64 overflow-auto"><table className="table"><thead><tr><th>Observed (UTC)</th><th>Status</th><th>FRP</th><th>Sat.</th><th>Dist.</th></tr></thead><tbody>{d.recent_detections_30d.slice(0, 60).map((x: any) => <tr key={x.id}><td className="text-xs">{x.acq_date} {x.acq_time}Z</td><td><DataStatusBadge status={x.data_status} /></td><td>{x.frp}</td><td>{x.satellite}</td><td>{x.distance_km} km</td></tr>)}</tbody></table></div>}</Section>
        </div>
      )}
    </div>
  );
}
