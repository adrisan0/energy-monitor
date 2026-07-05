export interface LatestResponse {
  timestamp: string;
  solar_w: number | null;
  grid_import_w: number | null;
  grid_export_w: number | null;
  house_consumption_w: number | null;
  solar_self_consumption_w: number | null;
  solar_self_consumption_percent: number | null;
  data_quality: string;
  meter_online: boolean;
  seconds_since_last_reading: number;
}

export interface Measurement {
  id: number;
  timestamp_utc: string;
  timestamp_local: string;
  solar_w: number | null;
  grid_import_w: number | null;
  grid_export_w: number | null;
  house_consumption_w: number | null;
  solar_self_consumption_w: number | null;
  solar_self_consumption_percent: number | null;
  data_quality: string;
  error_message: string | null;
  poll_duration_ms: number | null;
}

export interface Aggregate {
  id: number;
  period: string;
  period_start_utc: string;
  period_end_utc: string;
  period_start_local: string;
  period_end_local: string;
  solar_kwh: number;
  grid_import_kwh: number;
  grid_export_kwh: number;
  house_consumption_kwh: number;
  solar_self_consumption_kwh: number;
  self_sufficiency_percent: number | null;
  surplus_export_percent: number | null;
  max_power_w: number | null;
  min_power_w: number | null;
  estimated_cost_eur: number;
  compensation_eur: number;
  fixed_cost_eur: number;
  taxes_eur: number;
  net_cost_eur: number;
  sample_count: number;
  incomplete_intervals: number;
  is_complete: boolean;
}

export interface MeasurementsResponse {
  resolution: string;
  data: Measurement[] | Aggregate[];
}

export interface RawPayload {
  id: number;
  timestamp_utc: string;
  timestamp_local: string;
  raw_payload_redacted: string;
  raw_variables: Record<string, unknown>;
  payload_hash: string;
  repeated_payload: boolean;
  data_quality: string;
  error_message: string | null;
  poll_duration_ms: number | null;
}

export interface EnergySummary {
  start: string;
  end: string;
  solar_kwh: number;
  grid_import_kwh: number;
  grid_export_kwh: number;
  house_consumption_kwh: number;
  solar_self_consumption_kwh: number;
  self_sufficiency_percent: number | null;
  surplus_export_percent: number | null;
  estimated_cost_eur: number;
  compensation_eur: number;
  fixed_cost_eur: number;
  taxes_eur: number;
  net_cost_eur: number;
  incomplete_intervals: number;
  note: string;
}

export interface EnergyComparison {
  current: EnergySummary;
  previous: EnergySummary;
  delta_net_cost_eur: number;
  delta_house_consumption_kwh: number;
}

export interface Tariff {
  id: number;
  mode: "flat" | "time_of_use" | "future_pvpc";
  flat_price_eur_per_kwh: string;
  peak_price_eur_per_kwh: string;
  shoulder_price_eur_per_kwh: string;
  valley_price_eur_per_kwh: string;
  surplus_compensation_eur_per_kwh: string;
  monthly_fixed_cost_eur: string;
  meter_rental_monthly_eur: string;
  electricity_tax_percent: string;
  vat_percent: string;
  billing_start_date: string | null;
  notes: string | null;
}

export interface Annotation {
  id: number;
  appliance_name: string;
  home_area: string | null;
  appliance_type: string | null;
  starts_at: string;
  ends_at: string | null;
  approx_power_w: string | null;
  comment: string | null;
  source: string;
  confidence: string;
}

export interface EventResponse {
  system: Array<{
    id: number;
    timestamp_utc: string;
    event_type: string;
    severity: string;
    message: string;
    metadata_json: Record<string, unknown>;
  }>;
  analysis: Array<{
    timestamp: string;
    event_type: string;
    severity: string;
    label: string;
    confidence: string;
    value_w: number | null;
    note: string;
  }>;
}

export interface SystemStatus {
  backend: string;
  database: string;
  meter_online: boolean;
  simulation_mode: boolean;
  latest_sample_at: string | null;
  latest_data_quality: string | null;
  feature_flags: Record<string, boolean>;
  backups_path: string;
}

export interface Device {
  id: number;
  name: string;
  manufacturer: string | null;
  model: string | null;
  type: string;
  zone: string | null;
  ip_address: string | null;
  status: string;
  measurement_capable: boolean;
  max_power_w: number | null;
  active: boolean;
  control_mode: string;
  config: Record<string, unknown>;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DeviceState {
  online: boolean;
  is_on: boolean | null;
  power_w: number | null;
  raw: Record<string, unknown> | null;
}

export interface DeviceUpdate {
  name?: string | null;
  zone?: string | null;
  ip_address?: string | null;
  status?: string | null;
  max_power_w?: number | null;
  active?: boolean;
  control_mode?: string | null;
  config?: Record<string, unknown>;
}

export interface DeviceColorUpdate {
  rgb: [number, number, number];
  brightness: number | null;
}

export interface DeviceModeUpdate {
  mode: "manual" | "automatic";
}

export interface MessageResponse {
  message: string;
}
