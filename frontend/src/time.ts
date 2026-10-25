/** Naive benchmark clock helpers (no timezone conversion). */

export function normalizeNaive(ts: string): string {
  // Strip timezone suffixes if a serializer adds them; keep wall-clock text.
  const cleaned = ts.trim().replace(/Z$/, "").replace(/([+-]\d{2}:\d{2})$/, "");
  const normalized = cleaned.includes("T") ? cleaned.replace("T", " ") : cleaned;
  // Ensure seconds present
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(normalized)) {
    return `${normalized}:00`;
  }
  return normalized.slice(0, 19);
}

export function parseNaive(ts: string): Date {
  const normalized = normalizeNaive(ts).replace(" ", "T");
  return new Date(normalized);
}

export function formatNaive(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}

/** Consistent UI timestamps (drop trailing :00 seconds). */
export function formatDisplayTs(ts: string | null | undefined): string {
  if (!ts) return "—";
  const n = normalizeNaive(String(ts));
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:00$/.test(n)) return n.slice(0, 16);
  return n;
}

export function addSeconds(ts: string, seconds: number): string {
  const d = parseNaive(ts);
  d.setSeconds(d.getSeconds() + seconds);
  return formatNaive(d);
}

export function clampTs(ts: string, start: string, end: string): string {
  const t = parseNaive(ts).getTime();
  const a = parseNaive(start).getTime();
  const b = parseNaive(end).getTime();
  if (t < a) return start;
  if (t > b) return end;
  return ts;
}
