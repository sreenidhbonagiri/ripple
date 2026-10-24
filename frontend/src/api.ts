import type {
  HealthResponse,
  HourlyHistoryResponse,
  NetworkResponse,
  ReplaySnapshotResponse,
  ReplayWindowResponse,
  SensorReadingsResponse,
  SensorsResponse,
  TigerEvidenceResponse,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, { signal });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function fetchHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>("/api/health");
}

export function fetchNetwork(signal?: AbortSignal): Promise<NetworkResponse> {
  return fetchJson<NetworkResponse>("/api/network", signal);
}

export function fetchSensors(signal?: AbortSignal): Promise<SensorsResponse> {
  return fetchJson<SensorsResponse>("/api/sensors", signal);
}

export function fetchReplayWindow(signal?: AbortSignal): Promise<ReplayWindowResponse> {
  return fetchJson<ReplayWindowResponse>("/api/replay/window", signal);
}

export function fetchReplaySnapshot(
  at: string,
  signal?: AbortSignal,
): Promise<ReplaySnapshotResponse> {
  const q = new URLSearchParams({ at });
  return fetchJson<ReplaySnapshotResponse>(`/api/replay/snapshot?${q}`, signal);
}

export function fetchSensorReadings(
  sensorId: string,
  start: string,
  end: string,
  signal?: AbortSignal,
): Promise<SensorReadingsResponse> {
  const q = new URLSearchParams({ start, end });
  return fetchJson<SensorReadingsResponse>(
    `/api/sensors/${encodeURIComponent(sensorId)}/readings?${q}`,
    signal,
  );
}

export function fetchHourlyHistory(
  sensorId: string,
  at: string,
  days = 30,
  signal?: AbortSignal,
): Promise<HourlyHistoryResponse> {
  const q = new URLSearchParams({ at, days: String(days) });
  return fetchJson<HourlyHistoryResponse>(
    `/api/sensors/${encodeURIComponent(sensorId)}/hourly-history?${q}`,
    signal,
  );
}

/** Lazy Tiger evidence — do not call on critical investigation load. */
export function fetchTigerEvidence(
  signal?: AbortSignal,
): Promise<TigerEvidenceResponse> {
  return fetchJson<TigerEvidenceResponse>("/api/tiger/evidence", signal);
}
