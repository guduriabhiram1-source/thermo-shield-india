import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import { ProtectedRoute } from './components/ProtectedRoute';
import DashboardPage from './pages/DashboardPage';
import MapPage from './pages/MapPage';
import EventsPage from './pages/EventsPage';
import HighRiskPage from './pages/HighRiskPage';
import IncidentDetailPage from './pages/IncidentDetailPage';
import AnalyticsPage from './pages/AnalyticsPage';
import StateAnalyticsPage from './pages/StateAnalyticsPage';
import ReportsPage from './pages/ReportsPage';
import ReportDetailPage from './pages/ReportDetailPage';
import VerificationPage from './pages/VerificationPage';
import ExplainabilityPage from './pages/ExplainabilityPage';
import LocationAnalysisPage from './pages/LocationAnalysisPage';
import SatellitePage from './pages/SatellitePage';
import SettingsPage from './pages/SettingsPage';
import AffectedAreasPage from './pages/AffectedAreasPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import VerifyEmailPage from './pages/VerifyEmailPage';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="map" element={<MapPage />} />
        <Route path="incidents" element={<EventsPage />} />
        <Route path="high-risk" element={<HighRiskPage />} />
        <Route path="incidents/:id" element={<IncidentDetailPage />} />
        <Route path="incidents/:id/timeline" element={<IncidentDetailPage tab="timeline" />} />
        <Route path="incidents/:id/risk" element={<IncidentDetailPage tab="risk" />} />
        <Route path="incidents/:id/exposure" element={<IncidentDetailPage tab="exposure" />} />
        <Route path="incidents/:id/images" element={<IncidentDetailPage tab="images" />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="analytics/state/:state" element={<StateAnalyticsPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="reports/:id" element={<ReportDetailPage />} />
        <Route path="verification" element={<VerificationPage />} />
        <Route path="explainability" element={<ExplainabilityPage />} />
        <Route path="location-analysis" element={<LocationAnalysisPage />} />
        <Route path="affected-areas" element={<AffectedAreasPage />} />
        <Route path="satellite" element={<SatellitePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
