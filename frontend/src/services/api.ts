import axios from 'axios';
import type { AlertSettings, DashboardData, EventDetail, EventImage, EventSummary, Notification, Report, Session, StateBlock, TimelineItem } from '../types';

export const API_BASE = import.meta.env.VITE_API_BASE ?? '';
export const api = axios.create({ baseURL: API_BASE, timeout: 180000 });
const SESSION_KEY = 'tsi-session';

export function loadSession(): Session | null {
  try { const raw = localStorage.getItem(SESSION_KEY); return raw ? (JSON.parse(raw) as Session) : null; } catch { return null; }
}
export function saveSession(s: Session | null) {
  try { if (s) localStorage.setItem(SESSION_KEY, JSON.stringify(s)); else localStorage.removeItem(SESSION_KEY); } catch { /* ignore */ }
}

api.interceptors.request.use((cfg) => {
  const s = loadSession();
  if (s?.access_token) cfg.headers.Authorization = `Bearer ${s.access_token}`;
  return cfg;
});

let refreshing: Promise<Session | null> | null = null;
async function refreshSession(): Promise<Session | null> {
  const s = loadSession();
  if (!s?.refresh_token) return null;
  try {
    const r = await axios.post(`${API_BASE}/api/auth/refresh`, { refresh_token: s.refresh_token });
    const next = r.data as Session;
    saveSession(next);
    return next;
  } catch {
    saveSession(null);
    return null;
  }
}

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && original && !original._retried && loadSession()?.refresh_token && !String(original.url).includes('/api/auth/')) {
      original._retried = true;
      refreshing = refreshing ?? refreshSession();
      const next = await refreshing;
      refreshing = null;
      if (next) {
        original.headers.Authorization = `Bearer ${next.access_token}`;
        return api(original);
      }
      window.dispatchEvent(new Event('tsi-logout'));
    }
    return Promise.reject(error);
  },
);

export function fileUrl(path: string) {
  if (!path) return path;
  if (path.startsWith('http')) return path;
  return `${API_BASE}${path}`;
}

export interface EventFilters {
  state?: string; district?: string; classification?: string; risk_level?: string; persistence?: string; satellite?: string; verified?: string; range?: string; date_from?: string; date_to?: string;
  min_population?: number; industrial_km?: number; status?: string; data_status?: string; q?: string; sort?: string; limit?: number; offset?: number;
}

export const Api = {
  health: () => api.get('/api/health').then((r) => r.data),
  status: () => api.get('/api/system/status').then((r) => r.data),
  overview: () => api.get('/api/system/overview').then((r) => r.data),
  register: (body: { email: string; password: string; confirm_password: string; full_name?: string; organisation?: string }) => api.post('/api/auth/register', body).then((r) => r.data as { message: string; detail?: string }),
  verifyEmail: (email: string, code: string) => api.post('/api/auth/verify-email', { email, code }).then((r) => r.data as { message: string }),
  resendVerification: (email: string) => api.post('/api/auth/resend-verification', { email }).then((r) => r.data as { message: string; detail?: string }),
  login: (email: string, password: string) => api.post('/api/auth/login', { email, password }).then((r) => r.data as Session),
  logout: (refresh_token?: string) => api.post('/api/auth/logout', { refresh_token }).then((r) => r.data),
  me: () => api.get('/api/auth/me').then((r) => r.data),
  users: () => api.get('/api/users').then((r) => r.data),
  updateUser: (id: number, body: Record<string, unknown>) => api.patch(`/api/users/${id}`, body).then((r) => r.data),
  events: (f: EventFilters = {}) => api.get('/api/events', { params: f }).then((r) => r.data as { total: number; items: EventSummary[]; range: Record<string, string | null>; history_window: { from: string; to: string } }),
  eventsGeoJson: (f: Partial<EventFilters> = {}) => api.get('/api/events/geojson', { params: f }).then((r) => r.data),
  priority: (limit = 10, data_status = 'LIVE') => api.get('/api/events/priority', { params: { limit, data_status } }).then((r) => r.data.items as EventSummary[]),
  event: (id: string) => api.get(`/api/events/${id}`).then((r) => r.data as EventDetail),
  timeline: (id: string) => api.get(`/api/events/${id}/timeline`).then((r) => r.data as { items: TimelineItem[]; first_observed: string; last_observed: string }),
  images: (id: string, regenerate = false) => api.get(`/api/events/${id}/images`, { params: { regenerate } }).then((r) => r.data.items as EventImage[]),
  satellite: (id: string, search = false) => api.get(`/api/events/${id}/satellite`, { params: { search } }).then((r) => r.data.satellite),
  generatePdf: (id: string) => api.post(`/api/events/${id}/generate-pdf`).then((r) => r.data as { message: string; report: Report }),
  verify: (id: string, body: { action: string; classification?: string; probable_cause?: string; notes?: string }) => api.post(`/api/events/${id}/verify`, body).then((r) => r.data),
  analyze: (body: { incident_id?: string; latitude?: number; longitude?: number; with_images?: boolean; with_pdf?: boolean; live_enrichment?: boolean }) => api.post('/api/events/analyze', body).then((r) => r.data as EventDetail),
  reports: () => api.get('/api/reports').then((r) => r.data.items as Report[]),
  report: (id: number) => api.get(`/api/reports/${id}`).then((r) => r.data as Report),
  regenerateReport: (id: number) => api.post(`/api/reports/${id}/regenerate`).then((r) => r.data),
  dashboard: (params: Record<string, string | undefined> = {}) => api.get('/api/analytics/dashboard', { params }).then((r) => r.data as DashboardData),
  india: (params: Record<string, string | undefined> = {}) => api.get('/api/analytics/india', { params }).then((r) => r.data as { national: StateBlock; states: StateBlock[]; note: string }),
  state: (name: string, params: Record<string, string | undefined> = {}) => api.get(`/api/analytics/state/${encodeURIComponent(name)}`, { params }).then((r) => r.data),
  states: () => api.get('/api/boundaries/states').then((r) => r.data.states as { name: string; code: string; centroid: number[]; bbox: number[]; density: number | null }[]),
  statesGeoJson: () => api.get('/api/boundaries/states.geojson').then((r) => r.data),
  districts: (state?: string) => api.get('/api/boundaries/districts', { params: { state } }).then((r) => r.data as { districts: { name: string; state: string; lat: number; lon: number }[]; districts_in_events_not_in_osm_list: string[] }),
  location: (lat: number, lon: number, radius_km = 25, live = true) => api.get('/api/location/analyze', { params: { lat, lon, radius_km, live } }).then((r) => r.data),
  firmsLatest: (limit = 500) => api.get('/api/firms/latest', { params: { limit } }).then((r) => r.data),
  firmsRuns: () => api.get('/api/firms/runs').then((r) => r.data.items),
  firmsIngest: (body: { mode: string; csv_text?: string; days?: number; analyse?: boolean; window?: string }) => api.post('/api/firms/ingest', body).then((r) => r.data),
  liveIngest: () => api.post('/api/firms/live-ingest').then((r) => r.data),
  backfill: (start_date: string, end_date?: string) => api.post('/api/firms/backfill', { start_date, end_date }).then((r) => r.data),
  model: () => api.get('/api/ml/model').then((r) => r.data),
  trainingDataset: () => api.get('/api/ml/training-dataset').then((r) => r.data),
  train: (body: { note?: string; min_accuracy?: number }) => api.post('/api/ml/train', body).then((r) => r.data),
  promoteModel: (version: string) => api.post(`/api/ml/models/${version}/promote`).then((r) => r.data),
  search: (q: string) => api.get('/api/search', { params: { q } }).then((r) => r.data),
  notifications: () => api.get('/api/notifications').then((r) => r.data as { items: Notification[]; live_notice: string; email: { configured: boolean; provider: string } }),
  ackNotification: (id: number) => api.post(`/api/notifications/${id}/ack`).then((r) => r.data),
  alertLogs: () => api.get('/api/alerts/logs').then((r) => r.data.items),
  alertSettings: () => api.get('/api/alerts/settings').then((r) => r.data as AlertSettings),
  updateAlertSettings: (body: Partial<AlertSettings>) => api.put('/api/alerts/settings', body).then((r) => r.data as AlertSettings),
  testAlert: (recipient: string) => api.post('/api/alerts/test', { recipient }).then((r) => r.data),
  verificationQueue: () => api.get('/api/system/verification-queue').then((r) => r.data as { pending: EventSummary[]; completed: EventSummary[] }),
  audit: () => api.get('/api/system/audit').then((r) => r.data.items),
  reanalyseAll: (live = false) => api.post('/api/system/reanalyse-all', null, { params: { live } }).then((r) => r.data),
  maintenance: () => api.post('/api/system/maintenance').then((r) => r.data),
  generateVisuals: () => api.post('/api/system/generate-visuals').then((r) => r.data),
};

export function errorMessage(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const d = e.response?.data as { detail?: unknown } | undefined;
    if (d?.detail) return typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail);
    if (!e.response) return 'Backend unreachable — is the API running on port 8200?';
    return e.message;
  }
  return String(e);
}
