import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bot, CheckCircle2, Download, Eye, FileText, HelpCircle, Image as ImageIcon, RefreshCw, Satellite, Users, Wind } from 'lucide-react';
import { Api, errorMessage } from '../services/api';
import { AuthImage, ErrorBox, InfoBox, KV, Loading, Note, Section, Tabs, Unavailable } from '../components/Common';
import { ClassBadge, DataStatusBadge, ExposureBadge, OriginTag, PersistenceBadge, RiskBadge, StatusBadge } from '../components/Badges';
import { IncidentMap } from '../maps/IncidentMap';
import { EvolutionChart } from '../charts/EvolutionChart';
import { DayRiskSeries, RiskComponentsChart, RiskHistoryChart } from '../charts/RiskCharts';
import { ContributionChart, ProbabilityBars } from '../charts/ShapChart';
import { downloadPdf } from '../components/IncidentCard';
import { useAuth } from '../hooks/useAuth';
import { CLASSES, fmtCoord, fmtDate, fmtDateUtc, fmtKm, fmtNum, fmtPct, titleCase, trendArrow, trendClass } from '../utils/format';
import type { EventDetail } from '../types';

type Tab = 'overview' | 'timeline' | 'risk' | 'exposure' | 'images' | 'verify';
const TABS: { key: Tab; label: string }[] = [{ key: 'overview', label: 'Overview & AI' }, { key: 'timeline', label: 'Timeline & evolution' }, { key: 'risk', label: 'Risk momentum' }, { key: 'exposure', label: 'Wind & exposure' }, { key: 'images', label: 'Images & satellite' }, { key: 'verify', label: 'Human verification' }];

export default function IncidentDetailPage({ tab: initial = 'overview' }: { tab?: Tab }) {
  const { id = '' } = useParams();
  const nav = useNavigate();
  const [tab, setTab] = useState<Tab>(initial);
  const q = useQuery({ queryKey: ['event', id], queryFn: () => Api.event(id) });
  if (q.error) return <ErrorBox error={errorMessage(q.error)} />;
  if (!q.data) return <Loading text="Loading incident…" />;
  const e = q.data;
  const go = (t: Tab) => { setTab(t); nav(t === 'overview' ? `/incidents/${id}` : `/incidents/${id}/${t === 'verify' ? '' : t}`.replace(/\/$/, ''), { replace: true }); };
  return (
    <div className="space-y-4">
      <Header e={e} onRefresh={() => q.refetch()} />
      <Tabs tabs={TABS} value={tab} onChange={go} />
      {tab === 'overview' && <Overview e={e} />}
      {tab === 'timeline' && <TimelineTab e={e} />}
      {tab === 'risk' && <RiskTab e={e} />}
      {tab === 'exposure' && <ExposureTab e={e} />}
      {tab === 'images' && <ImagesTab e={e} />}
      {tab === 'verify' && <VerifyTab e={e} />}
    </div>
  );
}

function Header({ e, onRefresh }: { e: EventDetail; onRefresh: () => void }) {
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const gen = useMutation({ mutationFn: () => Api.generatePdf(e.incident_id), onSuccess: (r) => { setMsg(r.message); qc.invalidateQueries({ queryKey: ['event', e.incident_id] }); }, onError: (er) => setMsg(errorMessage(er)) });
  const rean = useMutation({ mutationFn: () => Api.analyze({ incident_id: e.incident_id, live_enrichment: true }), onSuccess: () => { setMsg('Re-analysed with live enrichment (Nominatim, Overpass, weather).'); onRefresh(); }, onError: (er) => setMsg(errorMessage(er)) });
  const hasReport = e.reports.some((r) => r.status === 'generated');
  return (
    <div className="card p-4 md:p-5 space-y-3">
      <div className="text-[10px] font-bold tracking-[0.25em] text-brand-600">THERMO-SHIELD INDIA · THERMAL INCIDENT REPORT</div>
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="font-mono text-2xl font-extrabold">{e.incident_id}</h1>
        <DataStatusBadge status={e.data_status} big />
        <RiskBadge level={e.risk_level} score={e.risk_score} /><ClassBadge classification={e.classification} label={e.classification_label} /><PersistenceBadge cls={e.persistence_class} score={e.persistence_score} /><StatusBadge status={e.status} />
        <span className={`text-sm font-semibold ${trendClass(e.risk_trend)}`}>{trendArrow(e.risk_trend)} ({e.risk_momentum > 0 ? '+' : ''}{Math.round(e.risk_momentum)})</span>
      </div>
      <div className="text-sm text-ink-600 dark:text-ink-300">{e.locality || 'Locality unavailable'} · {e.district || 'District unavailable'} · <b>{e.state || 'State unavailable'}</b> · {fmtCoord(e.latitude, e.longitude)} <OriginTag kind="OBSERVED" /> <span className="text-xs text-ink-400">geocode: {e.geocode_provider || 'reference'}</span></div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        <div className="rounded-lg bg-ink-50 dark:bg-ink-800/60 p-2"><div className="text-ink-500">Thermal activity started (first observed)</div><div className="font-semibold">{fmtDate(e.first_detected_at)}</div><div className="text-[10px] text-ink-400">{fmtDateUtc(e.first_detected_at)}</div></div>
        <div className="rounded-lg bg-ink-50 dark:bg-ink-800/60 p-2"><div className="text-ink-500">Last observation</div><div className="font-semibold">{fmtDate(e.last_detected_at)}</div><div className="text-[10px] text-ink-400">{e.detection_count} detections · {e.active_days} active day(s)</div></div>
        <div className="rounded-lg bg-ink-50 dark:bg-ink-800/60 p-2"><div className="text-ink-500">AI status <OriginTag kind="MODEL" /></div><div className="font-semibold">{e.ai_status === 'INSUFFICIENT_EVIDENCE' ? 'Insufficient evidence — human verification required' : `Predicted: ${e.classification_label} (${fmtPct(e.confidence, 1)})`}</div><div className="text-[10px] text-ink-400">method: {e.classification_method === 'lightgbm' ? 'LightGBM + SHAP' : 'rule-based (ML model unavailable)'}</div></div>
        <div className="rounded-lg bg-ink-50 dark:bg-ink-800/60 p-2"><div className="text-ink-500">Human status <OriginTag kind="HUMAN" /></div><div className="font-semibold">{e.human_status === 'PENDING' ? 'Pending' : `${titleCase(e.human_status)}: ${e.verified_classification ? titleCase(e.verified_classification) : 'uncertain'}`}</div></div>
      </div>
      <div className="flex flex-wrap gap-2 pt-1">
        <button className="btn-primary text-xs" onClick={() => gen.mutate()} disabled={gen.isPending}><FileText size={14} /> {gen.isPending ? 'Generating…' : 'Generate PDF'}</button>
        <button className="btn-secondary text-xs" disabled={!hasReport} onClick={() => downloadPdf(e.incident_id, true)}><Eye size={14} /> View PDF</button>
        <button className="btn-secondary text-xs" disabled={!hasReport} onClick={() => downloadPdf(e.incident_id)}><Download size={14} /> Download PDF</button>
        <button className="btn-secondary text-xs" onClick={() => rean.mutate()} disabled={rean.isPending}><RefreshCw size={14} /> {rean.isPending ? 'Re-analysing…' : 'Re-analyse (live enrichment)'}</button>
        <Link to={`/map?focus=${e.incident_id}`} className="btn-secondary text-xs">View on India map</Link>
        {msg && <span className="text-xs text-ink-600 dark:text-ink-300 self-center">{msg}</span>}
      </div>
    </div>
  );
}

function Overview({ e }: { e: EventDetail }) {
  const g = e.gis_context;
  const exp = e.explanation;
  const cause = e.probable_cause_detail;
  const prec = e.precautions;
  const lc = g?.land_cover;
  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <Section title="Incident summary" icon={<OriginTag kind="OBSERVED" />} className="xl:col-span-1">
        <KV items={[
          ['Incident ID', <span className="font-mono">{e.incident_id}</span>], ['Data status', <DataStatusBadge status={e.data_status} />], ['Classification', <>{e.classification_label} <OriginTag kind="MODEL" /></>], ['Risk', `${Math.round(e.risk_score)}/100 · ${e.risk_level}`],
          ['Confidence', fmtPct(e.confidence, 1)], ['Latitude / Longitude', fmtCoord(e.latitude, e.longitude)], ['State', e.state], ['District', e.district], ['Nearest locality', e.locality ? `${e.locality}${e.locality_distance_km ? ` (${fmtKm(e.locality_distance_km)})` : ''}` : null],
          ['First observed thermal activity', fmtDate(e.first_detected_at)], ['Last observation', fmtDate(e.last_detected_at)], ['Duration', `${e.duration_hours.toFixed(1)} h`], ['Persistence', `${e.persistence_class} · ${Math.round(e.persistence_score)}/100`],
          ['Detections', `${e.detection_count} (${e.live_detection_count} live)`], ['Peak / mean / latest FRP', `${fmtNum(e.max_frp, 1)} / ${fmtNum(e.mean_frp, 1)} / ${fmtNum(e.latest_frp, 1)} MW`], ['Peak brightness temperature', `${fmtNum(e.max_brightness, 1)} K`],
          ['Satellite / instrument', `${e.satellites || 'Unavailable'} / ${e.instruments || 'Unavailable'}`], ['Spatial spread', fmtKm(e.spatial_spread_km)], ['Land cover', lc?.available ? <>{lc.label} <span className="text-[10px] text-ink-400">[{lc.provenance}]</span></> : null],
          ['Population density', e.population_density != null ? <>{fmtNum(e.population_density)} /km² <OriginTag kind="ESTIMATE" /></> : null],
        ]} />
        {e.persistence && <Note>{e.persistence.summary} Active days {e.persistence.active_days} of {e.persistence.span_days}; night/day ratio {e.persistence.night_day_ratio}; FRP pattern {e.persistence.frp_pattern}; recurrence {e.persistence.recurrence_frequency_per_week}/week.</Note>}
      </Section>
      <div className="xl:col-span-2 space-y-4">
        <Section title="Probable source & AI explanation" icon={<Bot size={16} />} right={<OriginTag kind="MODEL" />}>
          {exp && !exp.ml_model_available && <InfoBox tone="warn"><b>ML model unavailable — insufficient validated training data.</b> {exp.method_note}</InfoBox>}
          {e.ai_status === 'INSUFFICIENT_EVIDENCE' && <div className="mt-2"><InfoBox tone="warn"><b>Insufficient evidence — Human verification required.</b> {e.classification_record?.uncertainty}</InfoBox></div>}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
            <div>
              <div className="card-title mb-1">Probability distribution</div>
              {exp ? <ProbabilityBars probs={exp.probabilities} labels={e.class_labels} /> : <Unavailable />}
              <div className="card-title mt-3 mb-1">Probable cause / thermal source</div>
              {cause ? (<div className="text-sm"><div className="font-semibold">{cause.title}</div><div className="text-xs text-ink-500 mt-0.5">Possible sources: {cause.options.join(', ')}</div><div className="text-xs mt-1 text-amber-700 dark:text-amber-300">{cause.wording}</div><div className="text-xs mt-1">Verification: {cause.verification}</div></div>) : <Unavailable />}
              <div className="card-title mt-3 mb-1">Uncertainty</div><div className="text-xs">{e.classification_record?.uncertainty ?? 'Unavailable'}</div>
            </div>
            <div>
              <div className="card-title mb-1">{exp?.question ?? 'Why did the AI classify this event?'}</div>
              {exp ? <><ContributionChart rows={exp.rows} shap={exp.shap_available} height={260} /><p className="text-sm mt-2">{exp.summary}</p><Note>{exp.method}</Note></> : <Unavailable />}
            </div>
          </div>
          <div className="card-title mt-4 mb-1">Evidence (contributing features)</div>
          <ul className="text-xs space-y-1">{(cause?.evidence ?? []).map((ev, i) => <li key={i}>• {ev.text} <span className="text-[10px] text-ink-400">[{ev.provenance}]</span></li>)}{!cause?.evidence?.length && <li><Unavailable /></li>}</ul>
        </Section>
        <Section title="GIS context — nearby facilities & infrastructure" right={<OriginTag kind="OBSERVED" />}>
          {g ? (
            <>
              <div className="text-xs text-ink-500 mb-2">Provider: {g.provider} · OSM live: {g.osm_live_status} · search radius {g.search_radius_km} km</div>
              <ul className="text-sm space-y-1">{g.summary.map((s, i) => <li key={i}>• {s}</li>)}</ul>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3 text-xs">
                <div><div className="card-title mb-1">Facilities within radius</div>
                  {[...g.refineries, ...g.power_plants, ...g.mines, ...g.gas_facilities, ...g.industrial_facilities].length === 0 ? <div className="text-ink-500">No facility found within {g.search_radius_km} km in OSM / reference data.</div> :
                    <table className="table"><thead><tr><th>Name</th><th>Type</th><th>Distance</th><th>Source</th></tr></thead><tbody>{[...g.refineries, ...g.power_plants, ...g.mines, ...g.gas_facilities, ...g.industrial_facilities].sort((a, b) => a.distance_km - b.distance_km).slice(0, 10).map((f, i) => <tr key={i}><td>{f.name}</td><td>{titleCase(f.category)}</td><td>{f.distance_km} km {f.direction}</td><td>{f.source}</td></tr>)}</tbody></table>}
                </div>
                <div><div className="card-title mb-1">Settlements & critical infrastructure</div>
                  <table className="table"><thead><tr><th>Name</th><th>Type</th><th>Distance</th><th>Population</th></tr></thead><tbody>
                    {g.settlements.slice(0, 8).map((s, i) => <tr key={i}><td>{s.name}</td><td>{s.type}</td><td>{s.distance_km} km {s.direction}</td><td>{s.population === null ? <Unavailable /> : <>{fmtNum(s.population)} <span className="text-[10px] text-ink-400">({s.population_source})</span></>}</td></tr>)}
                    {g.critical_infrastructure.map((c, i) => <tr key={`c${i}`}><td>{c.name || `${titleCase(c.kind)} (unnamed)`}</td><td>{c.kind}</td><td>{c.distance_km} km {c.direction}</td><td>—</td></tr>)}
                  </tbody></table>
                  {g.settlements.length === 0 && <div className="text-ink-500">No settlement found within radius in the gazetteer / OSM.</div>}
                </div>
              </div>
            </>
          ) : <Unavailable text="GIS context unavailable" />}
        </Section>
        <Section title="Precautions (risk-dependent decision-support guidance)">
          {prec ? (<div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <div><div className="card-title mb-1">General ({titleCase(prec.classification)})</div><ul className="space-y-1">{prec.general.map((p, i) => <li key={i}>• {p}</li>)}</ul></div>
            <div><div className="card-title mb-1">Risk level {prec.risk_level}</div><ul className="space-y-1">{prec.risk_specific.map((p, i) => <li key={i}>• {p}</li>)}{prec.population.map((p, i) => <li key={`p${i}`}>• {p}</li>)}</ul>
              <div className="card-title mt-3 mb-1">Limitations</div><ul className="space-y-1 text-xs text-ink-500">{prec.limitations.map((p, i) => <li key={i}>• {p}</li>)}</ul></div>
            <div className="md:col-span-2 text-xs text-amber-700 dark:text-amber-300">{prec.disclaimer}</div>
          </div>) : <Unavailable />}
        </Section>
        <Section title="Provenance of every block"><KV items={Object.entries(e.provenance ?? {}).filter(([k]) => k !== 'features').map(([k, v]) => [titleCase(k), String(v)])} /></Section>
      </div>
    </div>
  );
}

function TimelineTab({ e }: { e: EventDetail }) {
  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <Section title="Historical timeline (dates from real observations)" className="xl:col-span-1">
        <ol className="relative border-l border-ink-200 dark:border-ink-700 ml-2 space-y-3">
          {(e.timeline ?? []).map((t, i) => (
            <li key={i} className="ml-4"><span className="absolute -left-2.5 grid place-items-center h-5 w-5 rounded-full bg-white dark:bg-ink-900 text-xs border border-ink-300 dark:border-ink-700">{t.icon}</span>
              <div className="text-[11px] text-ink-500">{fmtDate(t.time)} <span className="text-[10px]">[{t.provenance}]</span></div><div className="text-sm font-semibold">{t.title}</div><div className="text-xs text-ink-600 dark:text-ink-300">{t.detail}</div></li>
          ))}
        </ol>
      </Section>
      <div className="xl:col-span-2 space-y-4">
        <Section title="Event evolution — FRP, brightness, spread, detection frequency" right={<OriginTag kind="CALCULATED" />}>
          {e.evolution ? <><p className="text-sm font-semibold mb-2">{e.evolution.statement}</p><EvolutionChart evo={e.evolution} /><Note>Peak FRP {fmtNum(e.evolution.peak_frp, 1)} MW on {e.evolution.peak_day ?? '—'} · FRP growth ×{e.evolution.frp_growth_rate} · spread growth ×{e.evolution.spread_growth_rate} · {e.evolution.frequency_per_day} detections/day.</Note></> : <Unavailable />}
        </Section>
        <Section title="Risk timeline (per observation day)">{e.evolution ? <DayRiskSeries series={e.evolution.series} /> : <Unavailable />}</Section>
        <Section title="Raw detections" right={<OriginTag kind="OBSERVED" />}>
          <div className="overflow-x-auto max-h-80"><table className="table"><thead><tr><th>Observation (UTC)</th><th>Ingested</th><th>Status</th><th>Satellite</th><th>FRP</th><th>Bright. (K)</th><th>Conf.</th><th>Day/Night</th><th>Lat / Lon</th></tr></thead>
            <tbody>{e.detections.map((d) => <tr key={d.id}><td className="text-xs">{fmtDateUtc(d.observation_timestamp)}</td><td className="text-xs">{fmtDateUtc(d.ingestion_timestamp)}</td><td><DataStatusBadge status={d.data_status} /></td><td>{d.satellite}/{d.instrument}</td><td>{fmtNum(d.frp, 1)}</td><td>{fmtNum(d.brightness, 1)}</td><td>{d.confidence}</td><td>{d.day_night}</td><td className="font-mono text-xs">{fmtCoord(d.latitude, d.longitude)}</td></tr>)}</tbody></table></div>
        </Section>
      </div>
    </div>
  );
}

function RiskTab({ e }: { e: EventDetail }) {
  const rc = e.risk_change;
  const missing = (e.risk_breakdown?._missing_inputs as string[] | undefined) ?? [];
  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      <Section title="Risk momentum" right={<OriginTag kind="CALCULATED" />}>
        <div className="flex items-end gap-4"><div><div className="card-title">Risk score</div><div className="text-4xl font-extrabold">{Math.round(e.risk_score)}<span className="text-lg text-ink-400">/100</span></div><RiskBadge level={e.risk_level} /></div>
          <div><div className="card-title">Previous</div><div className="text-2xl font-bold">{rc?.previous != null ? Math.round(rc.previous) : '—'}</div></div>
          <div><div className="card-title">Momentum</div><div className={`text-2xl font-bold ${trendClass(e.risk_trend)}`}>{e.risk_momentum > 0 ? '+' : ''}{Math.round(e.risk_momentum)}</div><div className={`text-xs font-semibold ${trendClass(e.risk_trend)}`}>{trendArrow(e.risk_trend)}</div></div></div>
        <p className="text-sm mt-3">{rc?.statement}</p>
        <div className="mt-3"><RiskHistoryChart history={e.risk_history} /></div>
        {missing.length > 0 && <Note>Missing inputs (component set to 0, not guessed): {missing.join('; ')}.</Note>}
      </Section>
      <Section title="Why did risk change?" icon={<HelpCircle size={16} />}>
        {rc?.reasons?.length ? (<><p className="text-sm mb-2">{rc.previous != null ? `Risk changed from ${Math.round(rc.previous)} → ${Math.round(rc.current)} because:` : 'Initial assessment — contributions by component:'}</p>
          <table className="table"><tbody>{rc.reasons.map((r, i) => <tr key={i}><td className={`font-mono font-bold ${r.delta_points > 0 ? 'text-red-600' : 'text-green-600'}`}>{r.delta_points > 0 ? '+' : ''}{r.delta_points}</td><td>{r.text}</td></tr>)}</tbody></table>
          <Note>Every contribution is computed from the actual change in a documented component between the previous and current assessment.</Note></>) : <Unavailable />}
      </Section>
      <Section title="Risk components (weighted factors)" className="xl:col-span-2">{e.risk_breakdown ? <RiskComponentsChart breakdown={e.risk_breakdown} /> : <Unavailable />}</Section>
    </div>
  );
}

function ExposureTab({ e }: { e: EventDetail }) {
  const ex = e.exposure;
  const w = e.weather;
  const pop = ex?.population;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Section title="Wind conditions" icon={<Wind size={16} />} right={<OriginTag kind={w?.available ? 'OBSERVED' : 'UNAVAILABLE'} />}>
          {w?.available ? <KV items={[['Wind speed', `${w.wind_speed_kmh} km/h`], ['Wind direction (from)', `${w.wind_direction_compass} (${w.wind_direction_deg}°)`], ['Potential downwind direction', ex?.wind.downwind ?? null], ['Gusts', w.wind_gust_kmh != null ? `${w.wind_gust_kmh} km/h` : null], ['Temperature / humidity', `${w.temperature_c ?? '—'} °C / ${w.humidity_pct ?? '—'} %`], ['Weather timestamp', fmtDate(w.weather_timestamp)], ['Weather source', w.weather_source], ['Exposure', <ExposureBadge level={ex?.exposure_level ?? 'UNAVAILABLE'} />]]} />
            : <div className="text-sm"><b>Weather data unavailable.</b> <span className="text-xs text-ink-500">{w?.reason ?? 'Not retrieved in the reference pass — use “Re-analyse (live enrichment)”.'}</span></div>}
          {w?.note && <Note>{w.note}</Note>}
        </Section>
        <Section title="Exposure model" className="xl:col-span-2" right={<OriginTag kind="ESTIMATE" />}>
          {ex ? <><KV items={[['Estimated hazard radius', `${ex.hazard_radius_km} km`], ['Downwind exposure reach', ex.downwind_reach_km != null ? `${ex.downwind_reach_km} km toward ${ex.wind.downwind}` : 'Unavailable (no wind data)'], ['Sector half-angle', ex.sector_half_angle_deg != null ? `${ex.sector_half_angle_deg}°` : null], ['Exposure level', <ExposureBadge level={ex.exposure_level} />]]} /><Note>{ex.model_note} Estimated potential exposure based on available wind and geographic data.</Note>
            {!ex.wind.available && <div className="mt-2"><InfoBox tone="warn">{ex.wind.note}</InfoBox></div>}</> : <Unavailable />}
        </Section>
      </div>
      <Section title="Wind-aware exposure map"><IncidentMap e={e} height={460} /></Section>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Section title="Potentially exposed areas" right={<OriginTag kind="ESTIMATE" />}>
          {ex?.affected_areas.length ? <div className="overflow-x-auto"><table className="table"><thead><tr><th>Area</th><th>Type</th><th>Distance</th><th>Direction</th><th>Downwind</th><th>Exposure</th><th>Est. exposed pop.</th><th>Source</th></tr></thead>
            <tbody>{ex.affected_areas.map((a, i) => <tr key={i}><td className="font-medium">{a.name}</td><td>{titleCase(a.area_type)}</td><td>{a.distance_km} km</td><td>{a.direction}</td><td>{a.downwind ? 'yes' : 'no'}</td><td><ExposureBadge level={a.exposure_level} /></td><td>{a.exposed_population === null ? <Unavailable /> : `≈ ${fmtNum(a.exposed_population)}`}</td><td className="text-xs">{a.source}</td></tr>)}</tbody></table></div>
            : <div className="text-sm text-ink-500">No potentially exposed area identified in the available datasets (gazetteer / OSM) within reach.</div>}
          <Note>Never claimed as definitely affected — potentially exposed only, pending field validation. Names come only from real GIS datasets.</Note>
        </Section>
        <Section title="Population exposure" icon={<Users size={16} />} right={<OriginTag kind="ESTIMATE" />}>
          {pop?.available ? <><div className="text-3xl font-extrabold">≈ {fmtNum(pop.exposed_estimate)}</div><div className="text-xs text-ink-500">Estimated potentially exposed population · downwind ≈ {pop.downwind_estimate != null ? fmtNum(pop.downwind_estimate) : 'unavailable'} · within hazard radius ≈ {fmtNum(pop.within_hazard_radius)}</div>
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs"><div><div className="card-title mb-1">By settlement</div><ul>{pop.by_settlement.map((s, i) => <li key={i}>{s.name} ({s.type}): ≈ {fmtNum(s.population)}</li>)}</ul></div>
              <div><div className="card-title mb-1">By administrative area</div><ul>{Object.entries(pop.by_district).map(([k, v]) => <li key={k}>{k}: ≈ {fmtNum(v)}</li>)}</ul></div></div>
            {pop.settlements_without_population_data.length > 0 && <Note>Settlements without population data (listed, not estimated): {pop.settlements_without_population_data.join(', ')}.</Note>}
            <Note>{pop.note}</Note></> : <div className="text-sm"><b>Population exposure unavailable</b> — no settlement with population data lies within the exposure reach.</div>}
        </Section>
      </div>
    </div>
  );
}

function ImagesTab({ e }: { e: EventDetail }) {
  const qc = useQueryClient();
  const [zoom, setZoom] = useState<string | null>(null);
  const imgs = useQuery({ queryKey: ['images', e.incident_id], queryFn: () => Api.images(e.incident_id) });
  const sat = useMutation({ mutationFn: () => Api.satellite(e.incident_id, true), onSuccess: () => { qc.invalidateQueries({ queryKey: ['event', e.incident_id] }); qc.invalidateQueries({ queryKey: ['images', e.incident_id] }); } });
  const s = e.satellite;
  const available = (imgs.data ?? []).filter((i) => i.available);
  const unavailable = (imgs.data ?? []).filter((i) => !i.available);
  const compare = available.filter((i) => i.type === 'optical_before' || i.type === 'optical_after');
  return (
    <div className="space-y-4">
      <Section title="Satellite evidence tiers" icon={<Satellite size={16} />} right={<button className="btn-secondary text-xs" onClick={() => sat.mutate()} disabled={sat.isPending}><RefreshCw size={13} /> {sat.isPending ? 'Searching STAC…' : 'Search Sentinel-2 scenes'}</button>}>
        {s ? <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div className="rounded-lg border border-sky-300 dark:border-sky-800 p-3"><div className="font-semibold">Thermal satellite detection <OriginTag kind="OBSERVED" /></div><div className="mt-1">{s.thermal_detection.note}</div></div>
          <div className="rounded-lg border border-ink-200 dark:border-ink-800 p-3"><div className="font-semibold">Optical satellite confirmation (Sentinel-2)</div><div className="mt-1">Status: <b>{s.sentinel2.status}</b> — {s.sentinel2.note}</div>{s.sentinel2.before.length + s.sentinel2.after.length > 0 && <ul className="mt-1">{[...s.sentinel2.before.map((x) => ({ ...x, k: 'before' })), ...s.sentinel2.after.map((x) => ({ ...x, k: 'after' }))].map((sc) => <li key={sc.id}>{sc.k}: {sc.datetime?.slice(0, 10)} · cloud {sc.cloud_cover}% · {sc.platform}</li>)}</ul>}</div>
          <div className="rounded-lg border border-ink-200 dark:border-ink-800 p-3"><div className="font-semibold">Post-event evidence</div><div className="mt-1">Status: <b>{s.post_event_evidence.status}</b> — {s.post_event_evidence.note}</div></div>
          <div className="md:col-span-3 text-amber-700 dark:text-amber-300">{s.disclaimer}</div>
        </div> : <Unavailable />}
      </Section>
      {compare.length === 2 && <Section title="Before / after optical reference (NASA GIBS true colour, 250 m)"><div className="grid grid-cols-1 md:grid-cols-2 gap-3">{compare.map((i) => <figure key={i.id}><img src={i.url} alt={i.title} className="rounded-lg w-full cursor-zoom-in" loading="lazy" onClick={() => setZoom(i.url)} /><figcaption className="text-xs text-ink-500 mt-1">{i.title} — {i.description}</figcaption></figure>)}</div></Section>}
      <Section title="Image gallery (only actually available images)" icon={<ImageIcon size={16} />}>
        {imgs.isLoading && <Loading />}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {available.map((i) => (
            <figure key={i.id} className="rounded-lg border border-ink-200 dark:border-ink-800 overflow-hidden">
              {i.external ? <img src={i.url} alt={i.title} className="w-full cursor-zoom-in bg-white" loading="lazy" onClick={() => setZoom(i.url)} /> : <AuthImage src={i.url} alt={i.title} className="w-full cursor-zoom-in bg-white" onClick={(u) => setZoom(u)} />}
              <figcaption className="p-2 text-xs"><div className="font-semibold">{i.title}</div><div className="text-ink-500">{i.description}</div><div className="text-[10px] text-ink-400 mt-0.5">source: {i.source}{i.external ? ' (external, loaded live)' : ''}</div></figcaption>
            </figure>
          ))}
        </div>
        {unavailable.length > 0 && <div className="mt-3 text-xs text-ink-500 space-y-1">{unavailable.map((i) => <div key={i.id}>⚠ {i.title}: {i.description}</div>)}</div>}
      </Section>
      {zoom && <div className="fixed inset-0 z-[1000] bg-black/85 grid place-items-center p-4 cursor-zoom-out" onClick={() => setZoom(null)}><img src={zoom} alt="Fullscreen" className="max-h-full max-w-full rounded-lg" /></div>}
    </div>
  );
}

function VerifyTab({ e }: { e: EventDetail }) {
  const { can, user } = useAuth();
  const qc = useQueryClient();
  const [action, setAction] = useState<'CONFIRM' | 'CORRECT' | 'UNCERTAIN'>('CONFIRM');
  const [cls, setCls] = useState(e.classification);
  const [notes, setNotes] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const m = useMutation({ mutationFn: () => Api.verify(e.incident_id, { action, classification: action === 'CORRECT' ? cls : undefined, notes }), onSuccess: () => { setMsg('Verification stored. The verified record is now available as a training sample.'); qc.invalidateQueries({ queryKey: ['event', e.incident_id] }); }, onError: (er) => setMsg(errorMessage(er)) });
  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      <Section title="AI vs human status">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-lg bg-violet-50 dark:bg-violet-900/20 p-3"><div className="card-title">AI status</div><div className="font-semibold mt-1">{e.ai_status === 'INSUFFICIENT_EVIDENCE' ? 'Insufficient evidence' : `Predicted: ${e.classification_label}`}</div><div className="text-xs text-ink-500">confidence {fmtPct(e.confidence, 1)} · {e.classification_method}</div></div>
          <div className="rounded-lg bg-green-50 dark:bg-green-900/20 p-3"><div className="card-title">Human status</div><div className="font-semibold mt-1">{e.human_status === 'PENDING' ? 'Pending' : `${titleCase(e.human_status)}${e.verified_classification ? `: ${titleCase(e.verified_classification)}` : ''}`}</div></div>
        </div>
        <div className="card-title mt-4 mb-1">Verification history</div>
        {e.verifications.length === 0 ? <div className="text-sm text-ink-500">No analyst verification recorded yet.</div> : <table className="table"><thead><tr><th>When</th><th>Analyst</th><th>Action</th><th>Original</th><th>Verified</th><th>Notes</th></tr></thead><tbody>{e.verifications.map((v) => <tr key={v.id}><td className="text-xs">{fmtDate(v.created_at)}</td><td className="text-xs">{v.analyst}</td><td>{v.action}</td><td>{titleCase(v.original_prediction)}</td><td>{v.verified_classification ? titleCase(v.verified_classification) : '—'}</td><td className="text-xs">{v.notes}</td></tr>)}</tbody></table>}
      </Section>
      <Section title="Analyst controls" icon={<CheckCircle2 size={16} />}>
        {!can('ANALYST') ? <InfoBox>Your role ({user?.role}) can view but not verify incidents. ANALYST or ADMIN role is required.</InfoBox> : (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-2">{(['CONFIRM', 'CORRECT', 'UNCERTAIN'] as const).map((a) => <button key={a} className={action === a ? 'btn-primary' : 'btn-secondary'} onClick={() => setAction(a)}>{a === 'CONFIRM' ? 'CONFIRM' : a === 'CORRECT' ? 'CHANGE CLASSIFICATION' : 'MARK UNCERTAIN'}</button>)}</div>
            {action === 'CORRECT' && <label className="block"><span className="label">Verified classification</span><select className="input" value={cls} onChange={(ev) => setCls(ev.target.value)}>{CLASSES.map((c) => <option key={c} value={c}>{e.class_labels[c] ?? c}</option>)}</select></label>}
            <label className="block"><span className="label">Notes (source of verification, field report, operator contact…)</span><textarea className="input" rows={4} value={notes} onChange={(ev) => setNotes(ev.target.value)} /></label>
            <button className="btn-primary" onClick={() => m.mutate()} disabled={m.isPending}>{m.isPending ? 'Saving…' : 'Save verification'}</button>
            {msg && <div className="text-xs">{msg}</div>}
            <Note>Stored with analyst id, timestamp, original prediction and verified prediction. Verified records become training samples; the production model is only retrained and promoted through an explicit ADMIN action.</Note>
          </div>
        )}
      </Section>
    </div>
  );
}
