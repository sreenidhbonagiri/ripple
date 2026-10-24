/** Saved investigation helpers — metadata restore; measurements stay on live APIs. */

export const DEFAULT_SOURCE_ID = "battledim-ltown-zenodo-4017659";
export const TITLE_MAX = 120;
export const NOTE_MAX = 1000;

export interface SavedInvestigation {
  id: string;
  title: string;
  note: string | null;
  sensor_id: string;
  cursor: string;
  window_start: string;
  window_end: string;
  source_id: string;
  created_at: string;
  share_path: string;
  public_note_notice: string;
  evidence_notice: string;
}

export type InvestigationCreateBody = {
  title: string;
  note?: string | null;
  sensor_id: string;
  cursor: string;
  window_start: string;
  window_end: string;
  source_id?: string;
};

export function readInvestigationIdFromUrl(
  search = typeof window !== "undefined" ? window.location.search : "",
): string | null {
  const raw = new URLSearchParams(search).get("i");
  if (!raw) return null;
  const id = raw.trim();
  if (!id || id.length > 64 || id.includes("/")) return null;
  return id;
}

export function shareUrlForId(id: string, origin = window.location.origin): string {
  const url = new URL(origin);
  url.searchParams.set("i", id);
  return url.toString();
}

export function replaceInvestigationQuery(id: string | null): void {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("i", id);
  else url.searchParams.delete("i");
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}
