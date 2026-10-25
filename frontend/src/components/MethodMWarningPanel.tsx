import { useEffect, useState } from "react";
import { fetchMethodMWarning } from "../api";
import type { MethodMWarningResponse } from "../types";

interface Props {
  cursor: string | null;
}

function fmtScore(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(3);
}

export default function MethodMWarningPanel({ cursor }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<MethodMWarningResponse | null>(null);
  const [forCursor, setForCursor] = useState<string | null>(null);

  useEffect(() => {
    if (!cursor) {
      setData(null);
      setForCursor(null);
      setError(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const requestCursor = cursor;
    setLoading(true);
    setError(null);
    fetchMethodMWarning(requestCursor, controller.signal)
      .then((res) => {
        if (controller.signal.aborted) return;
        setData(res);
        setForCursor(requestCursor);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, [cursor]);

  const matched = Boolean(cursor) && forCursor === cursor && data !== null;
  const showLoading = Boolean(cursor) && (!matched || loading) && !error;

  return (
    <section className="method-m-panel" aria-label="Experimental Method M warning">
      <div className="method-m-header">
        <p className="method-m-badge">Experimental · five-minute scoring</p>
        <h2 className="method-m-title">Experimental anomaly warning</h2>
        <p className="method-m-disclaimer" role="note">
          Experimental anomaly warning — not a confirmed leak. Not a pipe
          localization result. Scores and notifications use a native five-minute
          grid; do not treat notify times as finer than the 5-minute stamp.
        </p>
      </div>

      {!cursor && (
        <p className="channel-note">
          Set a replay cursor to load Method M evidence. Investigation stays
          usable without a warning.
        </p>
      )}

      {showLoading && (
        <p className="channel-note" role="status">
          Loading experimental warning…
        </p>
      )}

      {error && (
        <p className="state-copy" role="alert">
          {error}
        </p>
      )}

      {matched && data && (
        <div className="method-m-body">
          <p className="method-m-meta">
            Resolution: {data.resolution === "five_minute" ? "five-minute" : data.resolution}{" "}
            (latest score stamp ≤ cursor). Threshold τ ={" "}
            {fmtScore(data.threshold)}. Score stamp {data.score_hour ?? "—"}.
            {data.data_age_hours !== null && data.data_age_hours !== undefined
              ? ` Data age ${data.data_age_hours.toFixed(2)} h vs cursor.`
              : null}
          </p>

          {data.warning_active ? (
            <div className="method-m-active" role="status">
              <p className="method-m-status">Experimental warning active</p>
              <p className="method-m-score">
                Score {fmtScore(data.score)}
                <span className="channel-unit"> / τ {fmtScore(data.threshold)}</span>
              </p>
              {data.notification?.notify_ts && (
                <p className="channel-note">
                  Notification (five-minute, ≤ cursor) {data.notification.notify_ts}
                </p>
              )}
              {data.peak_score_observed_to_cursor !== null &&
                data.peak_score_observed_to_cursor !== undefined && (
                  <p className="channel-note">
                    Peak observed to cursor:{" "}
                    {fmtScore(data.peak_score_observed_to_cursor)} (final episode
                    peak/end withheld until the cursor reaches them)
                  </p>
                )}
            </div>
          ) : (
            <div className="method-m-idle" role="status">
              <p className="method-m-status">
                {data.status === "before_coverage" || data.status === "missing"
                  ? "No Method M evidence at this cursor"
                  : "No experimental warning at this cursor"}
              </p>
              {data.score !== null && data.score !== undefined && (
                <p className="method-m-score">
                  Score {fmtScore(data.score)}
                  <span className="channel-unit"> / τ {fmtScore(data.threshold)}</span>
                </p>
              )}
              <p className="channel-note">
                Investigation remains usable without a warning. No predicted
                leaking pipes are shown.
              </p>
            </div>
          )}

          {data.contributors.length > 0 && (
            <>
              <h3 className="details-section">Contributing sensors (measured dual context)</h3>
              <div className="tiger-table-wrap">
                <table className="tiger-table">
                  <thead>
                    <tr>
                      <th>Sensor</th>
                      <th>|z|/cal</th>
                      <th>δ (m³/h)</th>
                      <th>σ_SCALE</th>
                      <th>q_v</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.contributors.map((c) => (
                      <tr key={c.sensor_id}>
                        <td>
                          {c.sensor_id}
                          {data.argmax_sensor_id === c.sensor_id ? " · max" : ""}
                        </td>
                        <td>{fmtScore(c.abs_z_calibrated)}</td>
                        <td>{fmtScore(c.delta_m3h)}</td>
                        <td>{fmtScore(c.sigma_scale_m3h)}</td>
                        <td>{fmtScore(c.qv_m3h)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <p className="method-m-meta">
            Method M · experimental · calibration{" "}
            {(data.version_hashes.calibration_sha256 ?? "").slice(0, 12)}…
            {data.version_hashes.tau_sha256
              ? ` · τ ${(data.version_hashes.tau_sha256 ?? "").slice(0, 8)}…`
              : null}
          </p>
        </div>
      )}
    </section>
  );
}
