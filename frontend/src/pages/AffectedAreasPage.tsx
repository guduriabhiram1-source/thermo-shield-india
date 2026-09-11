import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Api, errorMessage } from '../services/api';
import { ErrorBox, InfoBox, Loading, Section } from '../components/Common';
import { DataStatusBadge, ExposureBadge, OriginTag, RiskBadge } from '../components/Badges';
import { DateRangeSelector } from '../components/DateRangeSelector';
import { useDateRange } from '../hooks/useDateRange';
import { fmtNum } from '../utils/format';

export default function AffectedAreasPage() {
  const { params } = useDateRange();
  const q = useQuery({ queryKey: ['events-exposure', params], queryFn: () => Api.events({ ...params, sort: 'population', limit: 100 }) });
  if (q.error) return <ErrorBox error={errorMessage(q.error)} />;
  if (!q.data) return <Loading />;
  const withPop = q.data.items.filter((e) => e.exposed_population !== null && e.exposed_population > 0);
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-extrabold tracking-tight">Potentially Exposed Areas</h1><p className="text-sm text-ink-500">Incidents ranked by estimated potentially exposed population (wind-aware exposure model). Never a confirmation that an area is affected.</p></div>
      <DateRangeSelector />
      <InfoBox tone="warn">Population figures are estimates from Census-2011 reference values and OSM population tags combined with the directional exposure model. Areas are “potentially exposed”, pending field validation. <OriginTag kind="ESTIMATE" /></InfoBox>
      <Section title={`${withPop.length} incident(s) with a population-exposure estimate · ${q.data.items.length - withPop.length} without (no populated settlement within reach, or population data unavailable)`}>
        {withPop.length === 0 ? <div className="text-sm text-ink-500">No incident in the selected range has a population-exposure estimate.</div> : (
          <div className="overflow-x-auto"><table className="table"><thead><tr><th>Incident</th><th>Data</th><th>Risk</th><th>Exposure</th><th>Est. exposed population</th><th>Location</th><th>Wind</th></tr></thead>
            <tbody>{withPop.map((e) => <tr key={e.incident_id}><td><Link className="font-mono text-brand-700 dark:text-brand-300 hover:underline" to={`/incidents/${e.incident_id}/exposure`}>{e.incident_id}</Link></td><td><DataStatusBadge status={e.data_status} /></td><td><RiskBadge level={e.risk_level} score={e.risk_score} /></td><td><ExposureBadge level={e.exposure_level} /></td><td>≈ {fmtNum(e.exposed_population)}</td><td className="text-xs">{e.locality || '—'}, {e.district || '—'}, {e.state}</td><td className="text-xs">{e.weather_available ? 'available' : 'unavailable'}</td></tr>)}</tbody></table></div>
        )}
      </Section>
    </div>
  );
}
