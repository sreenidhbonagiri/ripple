import { useEffect, useState } from "react";
import { fetchTigerEvidence } from "../api";
import type { TigerEvidenceResponse, TigerWorkload } from "../types";

function fmtMs(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "—";
  return `${(seconds * 1000).toFixed(2)} ms`;
}

function TimingBars({ wl }: { wl: TigerWorkload }) {
  const raw = wl.db_median_raw_s;
  const cagg = wl.db_median_cagg_s;
  if (
    raw === null ||
    raw === undefined ||
    cagg === null ||
    cagg === undefined ||
    Number.isNaN(raw) ||
    Number.isNaN(cagg)
  ) {
    return <span className="channel-note">—</span>;
  }
  const max = Math.max(raw, cagg, 1e-9);
  const rawPct = Math.max(4, (raw / max) * 100);
  const caggPct = Math.max(4, (cagg / max) * 100);
  return (
    <div className="tiger-bars" aria-label={`Database timings for ${wl.label}`}>
      <div className="tiger-bar-row">
        <span className="tiger-bar-label">Raw</span>
        <div className="tiger-bar-track">
          <div className="tiger-bar-fill tiger-bar-raw" style={{ width: `${rawPct}%` }} />
        </div>
        <span className="tiger-bar-ms">{fmtMs(raw)}</span>
      </div>
      <div className="tiger-bar-row">
        <span className="tiger-bar-label" title="Continuous aggregate (CAGG)">
          Summary
        </span>
        <div className="tiger-bar-track">
          <div className="tiger-bar-fill tiger-bar-cagg" style={{ width: `${caggPct}%` }} />
        </div>
        <span className="tiger-bar-ms">{fmtMs(cagg)}</span>
      </div>
    </div>
  );
}

function WorkloadCard({ wl }: { wl: TigerWorkload }) {
  const speedup =
    wl.db_median_speedup !== null && wl.db_median_speedup !== undefined
      ? `${wl.db_median_speedup.toFixed(2)}×`
      : "—";
  return (
    <article className="tiger-workload-card">
      <header className="tiger-workload-head">
        <strong>{wl.label}</strong>
        <span className="tiger-workload-meta">
          {wl.outputs_match ? "outputs match" : "mismatch"} · DB speedup {speedup}
        </span>
      </header>
      <p className="tiger-supports">{wl.supports_investigation}</p>
      <TimingBars wl={wl} />
      <p className="channel-note">
        Exact DB exec: raw {fmtMs(wl.db_median_raw_s)} · precomputed summary{" "}
        {fmtMs(wl.db_median_cagg_s)} (database execution — not whole-app load
        time)
      </p>
    </article>
  );
}

export default function TigerEvidencePanel() {
  const [open, setOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
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
            <strong>How Tiger supports investigation:</strong> raw sensor history
            feeds continuous aggregates for historical context; relational metadata
            stores saved / shareable investigations. Diagnostics stay off the critical
            path. Benchmarks are <strong>not</strong> re-run on page load. Timings are{" "}
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

              {live?.method_m_evidence?.tables_present &&
                (live.method_m_evidence.runs?.length ?? 0) > 0 && (
                  <>
                    <h3 className="details-section">
                      Method M evidence (persisted)
                    </h3>
                    <p className="channel-note">
                      {live.method_m_evidence.note ??
                        "Frozen Method M detector outputs in Tiger (no labels, no raw SCADA duplication)."}
                    </p>
                    {(live.method_m_evidence.runs ?? []).map((run) => (
                      <dl className="tiger-dl" key={run.run_id}>
                        <div className="detail-row">
                          <dt>Run</dt>
                          <dd>
                            <code>{run.run_id}</code>
                          </dd>
                        </div>
                        <div className="detail-row">
                          <dt>Score stamps</dt>
                          <dd>{run.n_score_stamps.toLocaleString()}</dd>
                        </div>
                        <div className="detail-row">
                          <dt>Contributor rows</dt>
                          <dd>{run.n_contributor_rows.toLocaleString()}</dd>
                        </div>
                        <div className="detail-row">
                          <dt>Notifications</dt>
                          <dd>{run.n_notifications.toLocaleString()}</dd>
                        </div>
                        <div className="detail-row">
                          <dt>serving_hours sha256</dt>
                          <dd>
                            <code>{run.serving_hours_sha256.slice(0, 16)}…</code>
                          </dd>
                        </div>
                      </dl>
                    ))}
                    {live.method_m_evidence.relation_pretty ? (
                      <p className="channel-note">
                        Method M relation size ≈{" "}
                        {live.method_m_evidence.relation_pretty}
                      </p>
                    ) : null}
                  </>
                )}

              <h3 className="details-section">
                January raw vs precomputed summaries (saved)
              </h3>
              <p className="tiger-inline-note">
                Historical context powered by precomputed summaries.
              </p>
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
                    {" · "}
                    reran on load: {data.reran_expensive_benchmark ? "yes" : "no"}
                  </p>
                  <p className="channel-note">{bench.latency_distinction}</p>
                  <div className="tiger-workload-list">
                    {(bench.workloads ?? []).map((wl) => (
                      <WorkloadCard key={wl.id} wl={wl} />
                    ))}
                  </div>
                </>
              )}

              <details
                className="tiger-details"
                open={detailsOpen}
                onToggle={(e) => setDetailsOpen((e.target as HTMLDetailsElement).open)}
              >
                <summary>Methodology, storage, and hashes</summary>
                <p className="channel-note">
                  Precomputed historical summaries are continuous aggregates
                  (CAGGs) over raw Tiger readings. Method M scores and
                  contributor rows are persisted separately from raw SCADA.
                  Benchmarks below are exact saved database timings — not
                  re-run on page load.
                </p>
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
                {bench?.available && (
                  <>
                    <p className="channel-note">
                      Artifact {bench.artifact_path ?? "—"}. No compression claim.
                      Values are read from the saved artifact only.
                    </p>
                    <div className="tiger-table-wrap">
                      <table className="tiger-table">
                        <thead>
                          <tr>
                            <th>Workload</th>
                            <th>Match</th>
                            <th>Raw DB exec</th>
                            <th title="Continuous aggregate (CAGG)">
                              Precomputed summary DB exec
                            </th>
                            <th>Speedup</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(bench.workloads ?? []).map((wl) => (
                            <tr key={`tbl-${wl.id}`}>
                              <td>{wl.label}</td>
                              <td>{wl.outputs_match ? "match" : "mismatch"}</td>
                              <td>{fmtMs(wl.db_median_raw_s)}</td>
                              <td>{fmtMs(wl.db_median_cagg_s)}</td>
                              <td>
                                {wl.db_median_speedup != null
                                  ? `${wl.db_median_speedup.toFixed(2)}×`
                                  : "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </details>
            </>
          )}
        </div>
      )}
    </section>
  );
}
