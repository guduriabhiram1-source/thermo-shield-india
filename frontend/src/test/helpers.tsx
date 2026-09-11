import { render } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '../themes/ThemeContext';
import { AuthProvider } from '../hooks/useAuth';
import { DateRangeProvider } from '../hooks/useDateRange';
import type { EventSummary, Session } from '../types';

export function renderWithProviders(ui: React.ReactElement, { route = '/', path = '*' }: { route?: string; path?: string } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[route]}>
      <QueryClientProvider client={qc}><ThemeProvider><AuthProvider><DateRangeProvider>
        <Routes><Route path={path} element={ui} /><Route path="/login" element={<div>LOGIN PAGE</div>} /><Route path="/verify-email" element={<div>VERIFY PAGE</div>} /><Route path="/dashboard" element={<div>DASHBOARD PAGE</div>} /></Routes>
      </DateRangeProvider></AuthProvider></ThemeProvider></QueryClientProvider>
    </MemoryRouter>,
  );
}

export const session: Session = { access_token: 'a.b.c', refresh_token: 'r', token_type: 'bearer', expires_in: 3600, user: { id: 1, email: 'analyst@example.org', full_name: 'Analyst', role: 'ANALYST', organisation: '', is_verified: true, is_active: true } };

export function setSession(s: Session | null = session) {
  if (s) localStorage.setItem('tsi-session', JSON.stringify(s)); else localStorage.removeItem('tsi-session');
}

export const sampleEvent: EventSummary = {
  id: 1, incident_id: 'TSI-IND-2026-000001', latitude: 22.35, longitude: 70.05, state: 'Gujarat', district: 'Jamnagar', locality: 'Jamnagar', land_cover: 'industrial',
  classification: 'REFINERY_ACTIVITY', classification_label: 'Refinery Thermal Activity', classification_method: 'rules', confidence: 0.42, probable_cause: 'Refinery process heat / flare',
  risk_score: 66, risk_level: 'HIGH', risk_momentum: 4, risk_trend: 'INCREASING', priority_score: 55, priority_rank: 1, priority_reason: 'HIGH risk (66/100)', persistence_score: 40, persistence_class: 'TEMPORARY',
  max_frp: 88.2, latest_frp: 70, frp_growth_rate: 1.2, max_brightness: 345, detection_count: 6, live_detection_count: 6, active_days: 2, night_ratio: 0.5, first_detected_at: '2026-09-10T07:15:00Z', last_detected_at: '2026-09-11T08:00:00Z',
  duration_hours: 24.75, satellites: 'N', instruments: 'VIIRS', exposed_population: 12340, exposure_level: 'HIGH', status: 'ACTIVE', data_status: 'LIVE', ai_status: 'PREDICTED', human_status: 'PENDING', verified_classification: null,
  nearest_facility: { name: 'Jamnagar Refinery Complex', category: 'refinery', distance_km: 1.2, source: 'reference_public' }, weather_available: true, data_source: 'FIRMS', enrichment_level: 'live', updated_at: '2026-09-11T09:00:00Z', analysed_at: '2026-09-11T09:00:00Z', has_report: true,
};
