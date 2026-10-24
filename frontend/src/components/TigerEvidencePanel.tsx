import { useEffect, useState } from "react";
import { fetchTigerEvidence } from "../api";
import type { TigerEvidenceResponse, TigerWorkload } from "../types";

function fmtMs(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "—";
  return `${(seconds * 1000).toFixed(2)} ms`;
}

function WorkloadRow({ wl }: { wl: TigerWorkload }) {
  const speedup =
    wl.db_median_speedup !== null && wl.db_median_speedup !== undefined
      ? `${wl.db_median_speedup.toFixed(2)}×`
      : "—";
  return (
    <tr>
      <td>
        <strong>{wl.label}</strong>
        <p className="tiger-supports">{wl.supports_investigation}</p>
      </td>
      <td>{wl.outputs_match ? "match" : "mismatch"}</td>
      <td>{fmtMs(wl.db_median_raw_s)}</td>
      <td>{fmtMs(wl.db_median_cagg_s)}</td>
      <td>{speedup}</td>
    </tr>
  );
}

export default function TigerEvidencePanel() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<TigerEvidenceResponse | null>(null);

  useEffect(() => {
    if (!open || data) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchTigerEvidence(controller.signal)
      .then((res) => {
        if (controller.signal.aborted) return;
        setData(res);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, [open, data]);

  const live = data?.live_stored;
  const storage = data?.storage;
  const bench = data?.saved_benchmark;

  return (
    <section className="tiger-panel" aria-label="Tiger Data evidence">
      <button
        type="button"
        className="tiger-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span>Tiger Data evidence</span>
        <span className="tiger-toggle-hint">
          {open ? "Hide" : "Show (loads saved benchmark — not re-run)"}
        </span>
      </button>

      {open && (
        <div className="tiger-body">
          <p className="tiger-note">
            Diagnostics stay off the critical investigation path. Benchmarks are
            not re-run on page load. Timings below are{" "}
            <strong>database execution</strong>, not application loading time.
          </p>

          {loading && <p className="channel-note">Loading Tiger evidence…</p>}
          {error && (
            <p className="state-copy" role="alert">
              {error}
            </p>
          )}

          {data && (
            <>
              <h3 className="details-section">Stored coverage (live)</h3>
              <dl className="tiger-dl">
                <div className="detail-row">
                  <dt>Sensors</dt>
                  <dd>{live?.sensors ?? "—"}</dd>
                </div>
                <div className="detail-row">
                  <dt>Readings (exact)</dt>
                  <dd>{live?.readings_total?.toLocaleString() ?? "—"}</dd>
                </div>
                <div className="detail-row">
                  <dt>Coverage</dt>
                  <dd>
                    {live?.coverage_start && live?.coverage_end
                      ? `${live.coverage_start} → ${live.coverage_end}`
                      : "—"}
                  </dd>
                </div>
                <div className="detail-row">
                  <dt>readings_15m rows</dt>
                  <dd>{live?.readings_15m_rows?.toLocaleString() ?? "—"}</dd>
                </div>
              </dl>

              <h3 className="details-section">Storage</h3>
              <dl className="tiger-dl">
                <div className="detail-row">
                  <dt>Database size</dt>
                  <dd>{storage?.database_pretty ?? "—"}</dd>
                </div>
                <div className="detail-row">
                  <dt>Configured limit</dt>
                  <dd>{storage?.limit_pretty ?? "unset"}</dd>
                </div>
                <div className="detail-row">
                  <dt>Working ceiling</dt>
                  <dd>
                    {storage?.working_ceiling_pretty ?? "—"}
                    <span className="channel-note"> (20% headroom)</span>
                  </dd>
                </div>
              </dl>

              <h3 className="details-section">January raw vs CAGG (saved)</h3>
              {!bench?.available && (
                <p className="channel-note">
                  Benchmark artifact missing. Run{" "}
                  <code>python scripts/benchmark_january_raw_cagg.py</code>.
                </p>
              )}
              {bench?.available && (
                <>
                  <p className="tiger-meta">
                    Run date {bench.run_date_utc ?? "—"}
                    {bench.repeats ? ` · ${bench.repeats}× alternating` : ""}
                    {bench.artifact_path ? ` · ${bench.artifact_path}` : ""}
                    {" · "}
                    reran on load: {data.reran_expensive_benchmark ? "yes" : "no"}
                  </p>
                  <p className="channel-note">{bench.latency_distinction}</p>
                  <div className="tiger-table-wrap">
                    <table className="tiger-table">
                      <thead>
                        <tr>
                          <th>Workload</th>
                          <th>Match</th>
                          <th>Raw DB exec</th>
                          <th>CAGG DB exec</th>
                          <th>Speedup</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(bench.workloads ?? []).map((wl) => (
                          <WorkloadRow key={wl.id} wl={wl} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
