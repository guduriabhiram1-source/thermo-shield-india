export type RiskLevel = 'LOW' | 'MODERATE' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type ExposureLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL' | 'UNAVAILABLE';
export type DataStatus = 'LIVE' | 'HISTORICAL';
export type Role = 'ADMIN' | 'ANALYST' | 'VIEWER';

export interface User { id: number; email: string; full_name: string; role: Role; organisation: string; is_verified: boolean; is_active: boolean; created_at?: string; last_login_at?: string | null }
export interface Session { access_token: string; refresh_token: string; token_type: string; expires_in: number; user: User }

export interface EventSummary {
  id: number; incident_id: string; latitude: number; longitude: number; state: string; district: string; locality: string; land_cover: string;
  classification: string; classification_label: string; classification_method: string; confidence: number; probable_cause: string;
  risk_score: number; risk_level: RiskLevel; risk_momentum: number; risk_trend: 'INCREASING' | 'DECREASING' | 'STABLE';
  priority_score: number; priority_rank: number; priority_reason: string; persistence_score: number; persistence_class: string;
  max_frp: number; latest_frp: number; frp_growth_rate: number; max_brightness: number; detection_count: number; live_detection_count: number; active_days: number; night_ratio: number;
  first_detected_at: string; last_detected_at: string; duration_hours: number; satellites: string; instruments: string; exposed_population: number | null; exposure_level: ExposureLevel;
  status: string; data_status: DataStatus; ai_status: string; human_status: string; verified_classification: string | null;
  nearest_facility: { name: string; category: string; distance_km: number; source?: string } | null; weather_available: boolean; data_source: string; enrichment_level: string;
  updated_at: string; analysed_at: string | null; has_report: boolean; distance_km?: number; direction?: string;
}

export interface Detection {
  id: number; latitude: number; longitude: number; observation_timestamp: string; acq_date: string; acq_time: string; satellite: string; instrument: string; confidence: string; confidence_score: number;
  brightness: number; brightness_2: number; frp: number; day_night: string; source: string; data_status: DataStatus; ingestion_timestamp: string; provenance: string; distance_km?: number;
}
export interface AffectedArea {
  name: string; area_type: string; district: string; state: string; latitude: number; longitude: number; distance_km: number; bearing: number; direction: string; downwind: boolean;
  exposure_score: number; exposure_level: ExposureLevel; population: number | null; population_source?: string | null; exposed_population: number | null; basis: string; source: string;
}
export interface Facility { id: number; osm_id?: string; name: string; operator: string; category: string; subtype: string; latitude: number; longitude: number; state: string; district: string; distance_km: number; bearing: number; direction: string; source: string; data_quality: string; capacity_mmtpa?: number; capacity_mw?: number; fuel?: string; resource?: string }
export interface Settlement { id: number; name: string; type: string; state: string; district: string; population: number | null; population_source?: string | null; latitude: number; longitude: number; radius_km: number; distance_km: number; bearing: number; direction: string; source: string }
export interface LandCover { available: boolean; class: string; label: string; basis: string[]; mix: Record<string, number>; provenance: string; is_estimate: boolean; note: string; provider: string }
export interface GisContext {
  search_radius_km: number; provider: string; osm_live_status: string; osm_retrieved_at?: string; refineries: Facility[]; power_plants: Facility[]; mines: Facility[]; gas_facilities: Facility[]; industrial_facilities: Facility[];
  nearest: Record<string, Facility | null>; nearest_road: { name: string; ref: string; type: string; distance_km: number; source: string } | null; nearest_railway: { name: string; ref: string; type: string; distance_km: number; source: string } | null;
  settlements: Settlement[]; nearest_residential: Settlement | null; critical_infrastructure: { name: string; kind: string; distance_km: number; direction: string; latitude: number; longitude: number }[];
  land_cover: LandCover; nearest_industrial_any: Facility | null; nearest_storage: Facility | null; distances: Record<string, number | null>; summary: string[]; geocode?: Record<string, unknown>; density?: { density_per_km2: number | null; basis: string; available: boolean };
}
export interface Weather { available: boolean; reason?: string; weather_source: string | null; kind?: string; wind_speed_kmh: number | null; wind_direction_deg: number | null; wind_direction_compass: string | null; wind_gust_kmh: number | null; temperature_c: number | null; humidity_pct: number | null; precipitation_mm: number | null; weather_timestamp: string | null; retrieved_at: string | null; note?: string }
export interface Exposure {
  wind: { available: boolean; speed_kmh: number | null; direction_from_deg: number | null; direction_from: string | null; downwind_deg: number | null; downwind: string | null; weather_source: string | null; weather_timestamp: string | null; note: string | null };
  hazard_radius_km: number; downwind_reach_km: number | null; sector_half_angle_deg: number | null; hazard_circle: number[][]; downwind_sector: number[][] | null; exposure_level: ExposureLevel; max_exposure_score: number; affected_areas: AffectedArea[];
  population: { available: boolean; exposed_estimate: number | null; downwind_estimate: number | null; within_hazard_radius: number | null; by_settlement: { name: string; population: number; type: string }[]; by_district: Record<string, number>; settlements_without_population_data: string[]; is_estimate: boolean; note: string };
  model_note: string; is_estimate: boolean; provenance: string;
}
export interface EvolutionPoint { day: string; detections: number; max_frp: number; sum_frp: number; max_brightness: number; spread_km: number; night_detections: number; live_detections: number; risk_score: number | null }
export interface Evolution { series: EvolutionPoint[]; days: number; frp_slope_per_day: number; frp_growth_rate: number; recent_change_ratio: number; spread_growth_rate: number; trend: string; statement: string; peak_day: string | null; peak_frp: number; frequency_per_day: number }
export interface ContribRow { feature: string; label: string; value: number; description: string; contribution: number; direction: string }
export interface Explanation {
  question: string; rows: ContribRow[]; top_positive: { description: string; contribution: number }[]; top_negative: { description: string; contribution: number }[]; summary: string; method: string; shap_available: boolean; ml_model_available: boolean; method_note: string;
  classification: string; label: string; confidence: number; probabilities: Record<string, number>; alternatives: { classification: string; probability: number }[]; contribution_ranked: ContribRow[]; feature_importance: Record<string, number>;
  model_version: string; model_name: string; insufficient_evidence: boolean; uncertainty: string; evidence: { text: string; provenance: string }[]; feature_labels: Record<string, string>;
}
export interface RiskComponent { value: number; weight: number; points: number; label: string }
export interface RiskChange { previous: number | null; current: number; momentum: number; trend: string; reasons: { component: string; label: string; delta_points: number; text: string }[]; statement: string; previous_at?: string | null }
export interface RiskHistory { id: number; computed_at: string; score: number; level: RiskLevel; previous_score: number | null; momentum: number; trend: string; components: Record<string, RiskComponent>; change_reasons: RiskChange['reasons']; data_status: DataStatus }
export interface Precautions { classification: string; risk_level: RiskLevel; general: string[]; risk_specific: string[]; population: string[]; limitations: string[]; disclaimer: string }
export interface TimelineItem { time: string; day: string; type: string; icon: string; title: string; detail: string; provenance: string }
export interface EventImage { id: number; type: string; title: string; description: string; url: string; source: string; available: boolean; external: boolean; meta: Record<string, unknown> | null; captured_at?: string | null; created_at: string }
export interface Report { id: number; event_id: number; incident_id: string; file_name: string; file_size: number; pages: number; status: string; generated_by: string; error: string; created_at: string; snapshot: Record<string, unknown> | null; download_url: string; view_url: string; state?: string; district?: string; locality?: string; classification?: string; classification_label?: string; risk_score?: number; risk_level?: RiskLevel; event_date?: string; data_status?: DataStatus }
export interface Verification { id: number; analyst: string; analyst_id: number | null; action: string; original_prediction: string; original_confidence: number; verified_classification: string | null; probable_cause: string; notes: string; created_at: string }
export interface AlertLog { id: number; incident_id: string; alert_type: string; risk_level: string; risk_score: number; data_status: DataStatus; data_timestamp: string | null; recipient: string; status: string; reason: string; subject: string; sent_at: string | null; created_at: string }
export interface Scene { id: string; datetime: string; cloud_cover: number; platform: string; thumbnail: string | null; visual: string | null; source: string }
export interface Satellite {
  thermal_detection: { status: string; note: string }; optical_reference: { status: string; before: { date: string; url: string; provider: string }; after: { date: string; url: string; provider: string }; note: string };
  sentinel2: { status: string; before: Scene[]; after: Scene[]; note: string; provider: string | null; searched_at?: string }; post_event_evidence: { status: string; note: string; scene?: Scene }; disclaimer: string; generated_at: string;
}
export interface ProbableCause { title: string; options: string[]; confidence: number; evidence: { text: string; provenance: string }[]; wording: string; verification: string; provenance: string }
export interface EventDetail extends EventSummary {
  bbox: { min_lat: number; min_lon: number; max_lat: number; max_lon: number } | null; spatial_spread_km: number; locality_distance_km: number | null; geocode_provider: string; population_density: number | null;
  mean_frp: number; total_frp: number; frp_trend: number; mean_brightness: number; mean_confidence: number; persistence: Record<string, any> | null; gis_context: GisContext | null; weather: Weather | null; exposure: Exposure | null;
  evolution: Evolution | null; explanation: Explanation | null; risk_breakdown: Record<string, RiskComponent | string[] | string> | null; risk_change: RiskChange | null; precautions: Precautions | null; satellite: Satellite | null; timeline: TimelineItem[] | null;
  features: Record<string, number> | null; provenance: Record<string, any> | null; probable_cause_detail: ProbableCause | null;
  classification_record: { model: string; version: string; uncertainty: string; insufficient_evidence: boolean; ml_model_available: boolean; evidence: { text: string; provenance: string }[]; created_at: string } | null;
  detections: Detection[]; risk_history: RiskHistory[]; affected_areas: AffectedArea[]; images: EventImage[]; reports: Report[]; verifications: Verification[]; alerts: AlertLog[]; class_labels: Record<string, string>;
}
export interface Notification { id: number; event_id: number | null; incident_id: string; severity: string; data_status: DataStatus; title: string; message: string; payload: Record<string, any>; acknowledged: boolean; created_at: string }
export interface Freshness { source: string; provider: string; status: string; detail: string; source_timestamp: string | null; retrieved_at: string | null }
export interface DashboardData {
  generated_at: string; range: { from: string | null; to: string | null; data_status: string | null; label: string }; history_window: { from: string; to: string; label: string };
  live: { latest_observation: string | null; latest_observation_ist: string | null; live_window_hours: number; is_stale: boolean }; freshness: Freshness[]; cards: Record<string, number | null>;
  events_by_state: { state: string; count: number }[]; classification_distribution: { classification: string; label: string; count: number }[]; risk_distribution: { level: RiskLevel; count: number }[];
  events_over_time: { day: string; new_events: number; detections: number; frp: number }[]; top_industrial_areas: { name: string; events: number }[]; population_exposure_by_state: { state: string; population: number }[];
  top_priority_live: EventSummary[]; top_priority_historical: EventSummary[]; recent_alerts: EventSummary[];
}
export interface StateBlock { state?: string; district?: string; code?: string; centroid?: number[]; density?: number | null; observations?: string; known_osm_district?: boolean; total_events: number; live_events: number; historical_events: number; active_events: number; industrial_events: number; wildfires: number; agricultural: number; persistent_sources: number; high_risk: number; critical: number; verified: number; unverified: number; estimated_exposure: number | null; exposure_events_with_estimate: number; max_risk: number; avg_risk: number; total_frp: number; total_detections: number }
export interface AlertSettings { live_alerts_enabled: boolean; high_enabled: boolean; critical_enabled: boolean; recipients: string; cooldown_hours: number; min_confidence: number; updated_by: string; updated_at: string; email: { configured: boolean; provider: string; smtp_host?: string | null; sender?: string | null; dev_log_only?: boolean }; effective: string }
