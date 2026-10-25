export interface NodeCoordinates {
  x: number;
  y: number;
}

export interface NetworkNode {
  id: string;
  type: "Junction" | "Reservoir" | "Tank";
  coordinates: NodeCoordinates | null;
  elevation: number | null;
  base_demand: number | null;
  demand_pattern: string | null;
  initial_quality: number | null;
  base_head: number | null;
  diameter: number | null;
  min_level: number | null;
  max_level: number | null;
  initial_level: number | null;
  min_vol: number | null;
  overflow: boolean | null;
  attributes: Record<string, unknown>;
}

export interface NetworkLink {
  id: string;
  type: "Pipe" | "Pump" | "Valve";
  start_node: string;
  end_node: string;
  length: number | null;
  diameter: number | null;
  roughness: number | null;
  minor_loss: number | null;
  status: string | null;
  check_valve: boolean | null;
  pump_type: string | null;
  valve_type: string | null;
  setting: number | null;
  attributes: Record<string, unknown>;
}

export interface NetworkCounts {
  nodes: number;
  links: number;
  junctions: number;
  reservoirs: number;
  tanks: number;
  pipes: number;
  pumps: number;
  valves: number;
}

export interface NetworkResponse {
  name: string;
  source: string;
  coordinate_system: string;
  product_boundary: string;
  counts: NetworkCounts;
  nodes: NetworkNode[];
  links: NetworkLink[];
}

export interface HealthResponse {
  status: string;
  service: string;
  product: string;
  note: string;
}

export type Selection =
  | { kind: "node"; data: NetworkNode }
  | { kind: "link"; data: NetworkLink }
  | { kind: "sensor"; data: Sensor }
  | null;

export interface Sensor {
  id: string;
  measurement_type: "pressure" | "flow" | "tank_level";
  unit: string;
  network_element_id: string;
  network_element_kind: "node" | "link";
}

export interface SensorsResponse {
  count: number;
  sensors: Sensor[];
  freshness_rule: string;
}

export interface ReadingPoint {
  ts: string;
  value: number;
}

export interface SensorReadingsResponse {
  sensor_id: string;
  unit: string;
  measurement_type: string;
  start: string;
  end: string;
  count: number;
  readings: ReadingPoint[];
}

export interface ReplayWindowResponse {
  /** Actual database coverage */
  data_start: string | null;
  data_end: string | null;
  sensor_count: number;
  /** Timescale approximate_row_count — coverage subtitle only */
  reading_count: number;
  /** True when reading_count comes from approximate_row_count */
  reading_count_estimated: boolean;
  /** Presenter playback preset (Jan 12 14:00–17:00) */
  presenter_start: string;
  presenter_end: string;
  /** Aliases for presenter window (playback) */
  start: string | null;
  end: string | null;
  step_seconds: number;
  label: string;
  freshness_rule: string;
}

export interface HourlyHistoryBucket {
  hour_start: string;
  mean_m: number;
  min_m: number;
  max_m: number;
  count: number;
  bucket_count: number;
  complete: boolean;
  missing_buckets: number;
  status: "complete" | "incomplete";
}

export interface HourlyHistoryResponse {
  sensor_id: string;
  unit: string;
  cursor: string;
  requested_days: number;
  history_start: string;
  coverage_start: string | null;
  coverage_end: string | null;
  coverage_days: number | null;
  hour_count: number;
  hours: HourlyHistoryBucket[];
  aggregation: Record<string, unknown>;
  title: string;
  limit_note: string;
}

export type FreshnessStatus = "current" | "stale" | "missing";

export interface SnapshotObservation {
  sensor_id: string;
  measurement_type: string;
  unit: string;
  network_element_id: string;
  network_element_kind: string;
  value: number | null;
  observation_ts: string | null;
  age_seconds: number | null;
  status: FreshnessStatus;
}

export interface ReplaySnapshotResponse {
  cursor: string;
  label: string;
  freshness_rule: string;
  observations: SnapshotObservation[];
}

export interface TigerWorkload {
  id: string;
  label: string;
  supports_investigation: string;
  outputs_match: boolean;
  raw_rows?: number;
  cagg_rows?: number;
  db_median_raw_s: number | null;
  db_median_cagg_s: number | null;
  db_p95_raw_s?: number | null;
  db_p95_cagg_s?: number | null;
  db_median_speedup?: number | null;
  speedup_note?: string;
  timing_scope?: string;
  timing_label?: string;
}

export interface MethodMContributor {
  sensor_id: string;
  abs_z_calibrated: number;
  delta_m3h: number;
  sigma_scale_m3h: number;
  qv_m3h: number;
  ref_mean_m3h: number;
}

export interface MethodMWarningResponse {
  method: string;
  experimental: boolean;
  disclaimer: string;
  resolution: string;
  resolution_note: string;
  cursor: string;
  score_hour: string | null;
  threshold: number;
  recover_threshold: number;
  version_hashes: Record<string, string>;
  coverage?: { start: string; end: string; note?: string };
  status: string;
  warning_active: boolean;
  score: number | null;
  contributors: MethodMContributor[];
  argmax_sensor_id: string | null;
  data_age_hours: number | null;
  notification: {
    notify_ts?: string;
    score_at_notify?: number | null;
    recovered_at_cursor_hour?: boolean;
  } | null;
  investigation_usable_without_warning: boolean;
  predicted_leak_pipes: null;
  episode_peak_score: number | null;
  episode_end_ts: string | null;
  peak_score_observed_to_cursor?: number | null;
  notes: string[];
  /** Serving backend: file artifact or Tiger tables. */
  store?: "file" | "tiger" | string;
  /** Present when store=tiger — frozen method_m_runs.run_id. */
  run_id?: string;
}

export interface MethodMTimelinePoint {
  ts: string;
  score: number | null;
  argmax_sensor_id: string | null;
}

export interface MethodMTimelineResponse {
  method: string;
  experimental: boolean;
  store: string;
  run_id: string;
  source: string;
  notification_source: string;
  label: string;
  replay_label: string;
  disclaimer: string;
  score_interpretation: string;
  resolution: string;
  resolution_note: string;
  cursor: string;
  window_start: string;
  window_end: string;
  timeline_hours: number;
  threshold: number;
  recover_threshold: number;
  version_hashes: Record<string, string>;
  coverage: { start: string; end: string; note?: string | null };
  status: string;
  points: MethodMTimelinePoint[];
  notifications: { notify_ts: string }[];
  missingness: {
    expected_stamps_in_window: number;
    expected_stamps_in_method_coverage: number;
    returned_stamps: number;
    null_scores: number;
    coverage_complete: boolean;
  };
  provenance: {
    serving_hours_sha256?: string | null;
    serving_notifications_sha256?: string | null;
    run_id: string;
    store: string;
  };
  notes: string[];
  predicted_leak_pipes: null;
}

export interface TigerEvidenceResponse {
  mode: string;
  reran_expensive_benchmark: boolean;
  rerun_note: string;
  product_boundary: string;
  live_stored: {
    sensors: number;
    readings_total: number;
    readings_in_presenter_window: number;
    readings_15m_rows: number;
    coverage_start: string | null;
    coverage_end: string | null;
    presenter_window: { start: string; end: string };
    method_m_evidence?: {
      tables_present: boolean;
      runs?: Array<{
        run_id: string;
        n_score_stamps: number;
        n_contributor_rows: number;
        n_notifications: number;
        serving_hours_sha256: string;
      }>;
      relation_bytes_approx?: number;
      relation_pretty?: string;
      note?: string;
    } | null;
  };
  storage: {
    database_bytes: number;
    database_pretty: string;
    readings_hypertable_bytes: number | null;
    readings_15m_bytes: number | null;
    limit_bytes: number | null;
    limit_pretty: string | null;
    working_ceiling_bytes: number | null;
    working_ceiling_pretty: string | null;
    headroom_note: string;
  };
  saved_benchmark: {
    available: boolean;
    run_date_utc: string | null;
    run_mtime_utc?: string | null;
    artifact_path: string | null;
    repeats: number | null;
    method?: string;
    dataset_scope?: Record<string, unknown>;
    compression_enabled_at_benchmark?: boolean;
    workloads: TigerWorkload[];
    latency_distinction: string;
    no_app_wide_speedup_claim: boolean;
  };
}
