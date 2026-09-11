import { useState } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, sampleEvent, setSession } from './helpers';
import { Api } from '../services/api';
import { EventFilters, EMPTY_FILTERS } from '../components/EventFilters';
import { IncidentCard } from '../components/IncidentCard';
import { MapLegend } from '../maps/IndiaMap';
import { DataStatusBadge } from '../components/Badges';
import { markerColor } from '../utils/format';
import { useTheme } from '../themes/ThemeContext';
import ReportsPage from '../pages/ReportsPage';
import IncidentDetailPage from '../pages/IncidentDetailPage';

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api');
  const api = { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn() };
  return { ...actual, api, Api: { ...actual.Api, states: vi.fn(), districts: vi.fn(), reports: vi.fn(), event: vi.fn(), generatePdf: vi.fn(), regenerateReport: vi.fn(), images: vi.fn(), verify: vi.fn(), analyze: vi.fn() } };
});

beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); setSession(); });

describe('map + filters', () => {
  it('colours markers by risk / persistence and labels live vs historical', () => {
    expect(markerColor({ risk_level: 'CRITICAL', persistence_class: 'ISOLATED', classification: 'WILDFIRE' })).toBe('#a21caf');
    expect(markerColor({ risk_level: 'LOW', persistence_class: 'PERSISTENT', classification: 'GAS_FLARE' })).toBe('#f97316');
    expect(markerColor({ risk_level: 'LOW', persistence_class: 'ISOLATED', classification: 'UNKNOWN' })).toBe('#cbd5e1');
    renderWithProviders(<><MapLegend /><DataStatusBadge status="LIVE" /><DataStatusBadge status="HISTORICAL" /></>);
    expect(screen.getByText(/Critical/)).toBeInTheDocument();
    expect(screen.getByText('🟢 LIVE DATA')).toBeInTheDocument();
    expect(screen.getByText('🔵 HISTORICAL DATA')).toBeInTheDocument();
  });

  it('loads district options dynamically for the selected state', async () => {
    (Api.states as any).mockResolvedValue([{ name: 'Andhra Pradesh', code: 'AP', centroid: [15.9, 79.7], bbox: [], density: 304 }, { name: 'Gujarat', code: 'GJ', centroid: [22, 71], bbox: [], density: 308 }]);
    (Api.districts as any).mockResolvedValue({ districts: [{ name: 'Guntur', state: 'Andhra Pradesh', lat: 16.3, lon: 80.4 }, { name: 'Krishna', state: 'Andhra Pradesh', lat: 16.2, lon: 81.1 }], districts_in_events_not_in_osm_list: [] });
    const onChange = vi.fn();
    function Harness() { const [v, setV] = useState(EMPTY_FILTERS); return <EventFilters value={v} onChange={(n) => { onChange(n); setV(n); }} />; }
    renderWithProviders(<Harness />);
    const state = await screen.findByLabelText('State filter');
    await waitFor(() => expect(within(state).getAllByRole('option').length).toBe(3));
    expect(screen.getByLabelText('District filter')).toBeDisabled();
    await userEvent.selectOptions(state, 'Andhra Pradesh');
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ state: 'Andhra Pradesh', district: '' }));
    await waitFor(() => expect(Api.districts).toHaveBeenCalledWith('Andhra Pradesh'));
    const district = screen.getByLabelText('District filter');
    await waitFor(() => expect(within(district).getByRole('option', { name: 'Guntur' })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText('Data status filter'), 'LIVE');
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ data_status: 'LIVE' }));
  });
});

describe('incident card + detail', () => {
  it('renders the incident card with provenance-safe values and PDF actions', async () => {
    (Api.generatePdf as any).mockResolvedValue({ message: 'Report generated successfully', report: {} });
    renderWithProviders(<IncidentCard e={{ ...sampleEvent, exposed_population: null, has_report: false }} />);
    expect(screen.getByText('TSI-IND-2026-000001')).toBeInTheDocument();
    expect(screen.getByText('🟢 LIVE DATA')).toBeInTheDocument();
    expect(screen.getByText('Unavailable')).toBeInTheDocument(); // population exposure not fabricated
    expect(screen.queryByText('Download PDF')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /generate pdf/i }));
    await waitFor(() => expect(Api.generatePdf).toHaveBeenCalledWith('TSI-IND-2026-000001'));
    expect(await screen.findByText('Download PDF')).toBeInTheDocument();
  });

  it('renders the incident detail header with first observed activity and AI / human status', async () => {
    (Api.event as any).mockResolvedValue({ ...sampleEvent, bbox: null, spatial_spread_km: 0.4, locality_distance_km: 0, geocode_provider: 'nominatim', population_density: 300, mean_frp: 40, total_frp: 240, frp_trend: 2, mean_brightness: 330, mean_confidence: 0.7,
      persistence: { summary: 'Short-lived activity', active_days: 2, span_days: 2, night_day_ratio: 0.5, frp_pattern: 'stable', recurrence_frequency_per_week: 2 }, gis_context: null, weather: { available: false, reason: 'not requested' }, exposure: null, evolution: null,
      explanation: { question: 'Why did the AI classify this event?', rows: [], top_positive: [], top_negative: [], summary: 'Near refinery was the strongest factor.', method: 'rules', shap_available: false, ml_model_available: false, method_note: 'ML model unavailable - insufficient validated training data.', classification: 'REFINERY_ACTIVITY', label: 'Refinery Thermal Activity', confidence: 0.42, probabilities: { REFINERY_ACTIVITY: 0.42, GAS_FLARE: 0.2 }, alternatives: [], contribution_ranked: [], feature_importance: {}, model_version: 'rules-v2.0', model_name: 'rules', insufficient_evidence: false, uncertainty: 'Elevated', evidence: [], feature_labels: {} },
      risk_breakdown: null, risk_change: null, precautions: null, satellite: null, timeline: [], features: {}, provenance: { classification: 'MODEL INFERENCE — rules' }, probable_cause_detail: null, classification_record: null, detections: [], risk_history: [], affected_areas: [], images: [], reports: [{ id: 1, status: 'generated' }], verifications: [], alerts: [], class_labels: { REFINERY_ACTIVITY: 'Refinery Thermal Activity', GAS_FLARE: 'Gas Flare' } });
    renderWithProviders(<IncidentDetailPage />, { route: '/incidents/TSI-IND-2026-000001', path: '/incidents/:id' });
    expect(await screen.findByRole('heading', { name: 'TSI-IND-2026-000001' })).toBeInTheDocument();
    expect(screen.getByText(/Thermal activity started/)).toBeInTheDocument();
    expect(screen.getByText(/Predicted: Refinery Thermal Activity/)).toBeInTheDocument();
    expect(screen.getAllByText(/ML model unavailable/).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /download pdf/i })).toBeEnabled();
  });
});

describe('theme + reports', () => {
  it('toggles light / dark and persists to localStorage', async () => {
    function Toggle() { const { theme, toggle } = useTheme(); return <button onClick={toggle}>theme:{theme}</button>; }
    renderWithProviders(<Toggle />);
    const btn = screen.getByRole('button');
    const before = btn.textContent;
    await userEvent.click(btn);
    expect(btn.textContent).not.toBe(before);
    expect(localStorage.getItem('tsi-theme')).toBe(btn.textContent!.replace('theme:', ''));
    expect(document.documentElement.classList.contains('dark')).toBe(btn.textContent === 'theme:dark');
  });

  it('lists reports and downloads a PDF through the authenticated client', async () => {
    (Api.reports as any).mockResolvedValue([{ id: 7, event_id: 1, incident_id: 'TSI-IND-2026-000001', file_name: 'ThermoShield_Incident_TSI-IND-2026-000001.pdf', file_size: 1024, pages: 13, status: 'generated', generated_by: 'a', error: '', created_at: '2026-09-11T09:00:00Z', snapshot: null, download_url: '/api/reports/7/download', view_url: '/api/reports/7/view', state: 'Gujarat', district: 'Jamnagar', locality: 'Jamnagar', classification: 'REFINERY_ACTIVITY', classification_label: 'Refinery Thermal Activity', risk_score: 66, risk_level: 'HIGH', event_date: '2026-09-11T08:00:00Z', data_status: 'LIVE' }]);
    const { api } = await import('../services/api');
    (api.get as any).mockResolvedValue({ data: new Blob(['%PDF'], { type: 'application/pdf' }) });
    renderWithProviders(<ReportsPage />, { route: '/reports', path: '/reports' });
    expect(await screen.findByText('TSI-IND-2026-000001')).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('download-7'));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/reports/7/download', { responseType: 'blob' }));
  });
});
