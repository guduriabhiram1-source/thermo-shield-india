import { useEffect, useMemo } from 'react';
import { CircleMarker, GeoJSON, LayersControl, MapContainer, Popup, TileLayer, useMap, useMapEvents } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';
import { Link } from 'react-router-dom';
import type { EventSummary } from '../types';
import { markerColor, fmtNum } from '../utils/format';
import { useTheme } from '../themes/ThemeContext';
import { DataStatusBadge } from '../components/Badges';

export const INDIA_CENTER: [number, number] = [22.5, 80.5];

export function BaseLayers() {
  const { isDark } = useTheme();
  return (
    <LayersControl position="topright">
      <LayersControl.BaseLayer checked={!isDark} name="OpenStreetMap">
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
      </LayersControl.BaseLayer>
      <LayersControl.BaseLayer checked={isDark} name="Dark (CARTO)">
        <TileLayer attribution='&copy; OpenStreetMap contributors &copy; <a href="https://carto.com/">CARTO</a>' url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
      </LayersControl.BaseLayer>
      <LayersControl.BaseLayer name="Satellite imagery (Esri World Imagery)">
        <TileLayer attribution="Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community" url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" />
      </LayersControl.BaseLayer>
      <LayersControl.BaseLayer name="Terrain (OpenTopoMap)">
        <TileLayer attribution='&copy; OpenStreetMap contributors, SRTM | &copy; <a href="https://opentopomap.org">OpenTopoMap</a>' url="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png" />
      </LayersControl.BaseLayer>
    </LayersControl>
  );
}

export function FlyTo({ center, zoom }: { center: [number, number] | null; zoom?: number }) {
  const map = useMap();
  useEffect(() => { if (center) map.flyTo(center, zoom ?? 11, { duration: 0.8 }); }, [center?.[0], center?.[1]]);
  return null;
}

export function ClickCapture({ onClick }: { onClick?: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => onClick?.(e.latlng.lat, e.latlng.lng) });
  return null;
}

export function EventPopup({ e }: { e: EventSummary }) {
  return (
    <div className="text-xs space-y-1 min-w-[220px]">
      <div className="font-mono font-bold text-brand-700 dark:text-brand-300">{e.incident_id}</div>
      <DataStatusBadge status={e.data_status} />
      <div className="font-semibold">{e.classification_label} · {Math.round(e.confidence * 100)}% <span className="font-normal text-ink-500">[{e.classification_method === 'lightgbm' ? 'ML' : 'rules'}]</span></div>
      <div>Risk <b>{Math.round(e.risk_score)}/100 {e.risk_level}</b> · persistence {e.persistence_class}</div>
      <div>{e.locality || 'Locality unavailable'}, {e.district || 'District unavailable'}, {e.state}</div>
      <div>Peak FRP {fmtNum(e.max_frp, 1)} MW · exposure {e.exposed_population === null ? 'unavailable' : `≈ ${fmtNum(e.exposed_population)} (est.)`}</div>
      <Link className="text-brand-600 font-semibold hover:underline" to={`/incidents/${e.incident_id}`}>Open incident →</Link>
    </div>
  );
}

export function IndiaMap({ events, focus, onMapClick, height = '100%', cluster = true, boundaries, children }: { events: EventSummary[]; focus?: EventSummary | null; onMapClick?: (lat: number, lon: number) => void; height?: string; cluster?: boolean; boundaries?: any; children?: React.ReactNode }) {
  const markers = useMemo(() => events.map((e) => (
    <CircleMarker key={e.incident_id} center={[e.latitude, e.longitude]} radius={e.risk_level === 'CRITICAL' ? 10 : e.risk_level === 'HIGH' ? 8 : 6}
      pathOptions={{ color: e.data_status === 'LIVE' ? '#111827' : '#64748b', weight: e.data_status === 'LIVE' ? 1.5 : 1, dashArray: e.data_status === 'LIVE' ? undefined : '2 2', fillColor: markerColor(e), fillOpacity: e.data_status === 'LIVE' ? 0.95 : 0.7 }}>
      <Popup><EventPopup e={e} /></Popup>
    </CircleMarker>
  )), [events]);
  const iconFn = (c: any) => L.divIcon({ html: `<div><span>${c.getChildCount()}</span></div>`, className: 'marker-cluster marker-cluster-small', iconSize: L.point(36, 36) });
  return (
    <MapContainer center={INDIA_CENTER} zoom={5} minZoom={4} maxBounds={[[-5, 50], [45, 110]]} style={{ height, width: '100%' }} className="rounded-xl z-0">
      <BaseLayers />
      {boundaries && <GeoJSON key="states" data={boundaries} style={() => ({ color: '#64748b', weight: 0.8, fillOpacity: 0.02 })} />}
      {cluster ? <MarkerClusterGroup chunkedLoading iconCreateFunction={iconFn} maxClusterRadius={45}>{markers}</MarkerClusterGroup> : markers}
      <FlyTo center={focus ? [focus.latitude, focus.longitude] : null} />
      {onMapClick && <ClickCapture onClick={onMapClick} />}
      {children}
    </MapContainer>
  );
}

export function MapLegend() {
  const items = [['#a21caf', '🟣 Critical'], ['#ef4444', '🔴 High risk'], ['#f97316', '🟠 Persistent source'], ['#eab308', '🟡 Medium / moderate'], ['#22c55e', '🟢 Low'], ['#cbd5e1', '⚪ Unknown']];
  return (
    <div className="flex flex-wrap gap-3 text-xs items-center">
      {items.map(([c, l]) => <span key={l} className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-full border border-ink-900/40" style={{ background: c }} /> {l}</span>)}
      <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-full border-2 border-ink-900" /> solid ring = LIVE</span>
      <span className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-full border border-dashed border-ink-500" /> dashed ring = HISTORICAL</span>
    </div>
  );
}
