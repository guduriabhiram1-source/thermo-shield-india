import { CircleMarker, MapContainer, Marker, Polygon, Polyline, Popup, Tooltip } from 'react-leaflet';
import L from 'leaflet';
import type { EventDetail } from '../types';
import { BaseLayers } from './IndiaMap';
import { fmtNum } from '../utils/format';

const facilityIcon = (color: string) => L.divIcon({ className: '', html: `<div style="width:14px;height:14px;background:${color};border:2px solid #111;transform:rotate(45deg);"></div>`, iconSize: [14, 14], iconAnchor: [7, 7] });
const settlementIcon = L.divIcon({ className: '', html: '<div style="width:12px;height:12px;border-radius:50%;background:#16a34a;border:2px solid #052e16"></div>', iconSize: [12, 12], iconAnchor: [6, 6] });
const CAT_COLOR: Record<string, string> = { refinery: '#7c3aed', power_plant: '#0ea5e9', mine: '#a16207', gas_facility: '#db2777', industrial: '#475569', storage: '#0f766e' };
const EXPO: Record<string, string> = { LOW: '#22c55e', MODERATE: '#eab308', HIGH: '#f97316', CRITICAL: '#ef4444' };

export function IncidentMap({ e, height = 420, showExposure = true, showFacilities = true, showDetections = true, showAffected = true }: { e: EventDetail; height?: number | string; showExposure?: boolean; showFacilities?: boolean; showDetections?: boolean; showAffected?: boolean }) {
  const ex = e.exposure;
  const wind = ex?.wind;
  const arrowEnd = wind?.available && wind.downwind_deg != null ? destination(e.latitude, e.longitude, wind.downwind_deg, Math.max(3, (ex?.downwind_reach_km ?? 5) * 0.6)) : null;
  const g = e.gis_context;
  const facilities = showFacilities && g ? [...g.refineries, ...g.power_plants, ...g.mines, ...g.gas_facilities, ...g.industrial_facilities] : [];
  return (
    <MapContainer center={[e.latitude, e.longitude]} zoom={11} style={{ height, width: '100%' }} className="rounded-xl z-0">
      <BaseLayers />
      {showExposure && ex?.hazard_circle && <Polygon positions={ex.hazard_circle as [number, number][]} pathOptions={{ color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.12, weight: 1.5 }}><Tooltip sticky>Estimated hazard radius {ex.hazard_radius_km} km</Tooltip></Polygon>}
      {showExposure && ex?.downwind_sector && <Polygon positions={ex.downwind_sector as [number, number][]} pathOptions={{ color: '#f97316', fillColor: '#f97316', fillOpacity: 0.18, weight: 1.5, dashArray: '4 3' }}><Tooltip sticky>Downwind exposure sector ({ex.downwind_reach_km} km toward {wind?.downwind}) — estimate</Tooltip></Polygon>}
      {showExposure && arrowEnd && <Polyline positions={[[e.latitude, e.longitude], arrowEnd]} pathOptions={{ color: '#1d4ed8', weight: 3 }}><Tooltip permanent direction="right" className="!bg-white/90 dark:!bg-ink-900/90 !text-xs">Wind {wind!.speed_kmh} km/h from {wind!.direction_from} → {wind!.downwind}</Tooltip></Polyline>}
      {showDetections && e.detections.map((d) => (
        <CircleMarker key={d.id} center={[d.latitude, d.longitude]} radius={3 + Math.min(d.frp, 200) / 30} pathOptions={{ color: '#7f1d1d', weight: 0.6, fillColor: d.frp > 80 ? '#fbbf24' : '#ef4444', fillOpacity: 0.85 }}>
          <Tooltip>{d.acq_date} {d.acq_time}Z · FRP {fmtNum(d.frp, 1)} MW · {d.satellite}/{d.instrument} · {d.day_night === 'N' ? 'night' : 'day'} · {d.data_status}</Tooltip>
        </CircleMarker>
      ))}
      {facilities.map((f, i) => (
        <Marker key={`${f.category}-${f.id}-${i}`} position={[f.latitude, f.longitude]} icon={facilityIcon(CAT_COLOR[f.category] ?? '#475569')}>
          <Popup><div className="text-xs"><b>{f.name}</b><br />{f.category.replace('_', ' ')} · {f.operator || 'operator unavailable'}<br />{f.distance_km} km {f.direction} · {f.source} ({f.data_quality})</div></Popup>
        </Marker>
      ))}
      {showAffected && (ex?.affected_areas ?? []).map((a, i) => (
        <CircleMarker key={i} center={[a.latitude, a.longitude]} radius={7} pathOptions={{ color: '#052e16', weight: 1, fillColor: EXPO[a.exposure_level] ?? '#22c55e', fillOpacity: 0.9 }}>
          <Popup><div className="text-xs"><b>{a.name}</b> ({a.area_type})<br />{a.distance_km} km {a.direction}{a.downwind ? ' · downwind' : ''}<br />Exposure <b>{a.exposure_level}</b> · est. exposed {a.exposed_population === null ? 'unavailable' : `≈ ${fmtNum(a.exposed_population)}`}</div></Popup>
        </CircleMarker>
      ))}
      {!showAffected && (g?.settlements ?? []).map((s, i) => <Marker key={`${s.id}-${i}`} position={[s.latitude, s.longitude]} icon={settlementIcon}><Tooltip>{s.name} · {s.population === null ? 'population unavailable' : `${fmtNum(s.population)} (${s.population_source})`}</Tooltip></Marker>)}
      <CircleMarker center={[e.latitude, e.longitude]} radius={9} pathOptions={{ color: '#fff', weight: 2, fillColor: '#dc2626', fillOpacity: 1 }}><Tooltip permanent direction="top" className="!text-xs font-semibold">{e.incident_id}</Tooltip></CircleMarker>
    </MapContainer>
  );
}

function destination(lat: number, lon: number, bearing: number, km: number): [number, number] {
  const R = 6371.0088, br = (bearing * Math.PI) / 180, d = km / R, p1 = (lat * Math.PI) / 180, l1 = (lon * Math.PI) / 180;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(br));
  const l2 = l1 + Math.atan2(Math.sin(br) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return [(p2 * 180) / Math.PI, (l2 * 180) / Math.PI];
}
