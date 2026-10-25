import { useEffect, useState } from "react";
import { fetchMethodMWarning } from "../api";
import type { MethodMWarningResponse } from "../types";

interface Props {
  cursor: string | null;
  onInspectSensor?: (sensorId: string) => void;
  selectedSensorId?: string | null;
  /** Share the cursor-matched warning payload with the investigation brief. */
  onMatchedData?: (data: MethodMWarningResponse | null) => void;
}

function fmtScore(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(3);
}

export default function MethodMWarningPanel({
  cursor,
  onInspectSensor,
  selectedSensorId = null,
  onMatchedData,
}: Props) {
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
      onMatchedData?.(null);
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
        onMatchedData?.(res);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
        onMatchedData?.(null);
      });
    return () => controller.abort();
    // onMatchedData intentionally omitted — parent should pass a stable callback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
          Contributing sensors are dual-context evidence to inspect — not leak
          locations.
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
            Five-minute resolution (latest score stamp ≤ cursor). Score stamp{" "}
            {data.score_hour ?? "—"}.
            {data.data_age_hours !== null && data.data_age_hours !== undefined
              ? ` Data age ${data.data_age_hours.toFixed(2)} h vs cursor.`
              : null}
          </p>

          {data.warning_active ? (
            <div className="method-m-active" role="status">
              <p className="method-m-status">Experimental warning active</p>
              <p className="method-m-score">
                Score {fmtScore(data.score)}
                <span className="channel-unit">
                  {" "}
                  / threshold τ {fmtScore(data.threshold)}
                </span>
              </p>
              {data.notification?.notify_ts && (
                <p className="channel-note">
                  Notification time (five-minute stamp ≤ cursor):{" "}
                  {data.notification.notify_ts}
                </p>
              )}
              {data.peak_score_observed_to_cursor !== null &&
                data.peak_score_observed_to_cursor !== undefined && (
                  <p className="channel-note">
                    Peak score observed to cursor:{" "}
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
                  <span className="channel-unit">
                    {" "}
                    / threshold τ {fmtScore(data.threshold)}
                  </span>
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
              <h3 className="details-section">
                Contributing sensors (dual-context evidence)
              </h3>
              <p className="channel-note">
                Use <strong>Inspect sensor</strong> to update the map selection and
                pressure chart at the current replay cursor. This does not identify a
                leaking pipe.
              </p>
              <p className="channel-note">
                <strong>Virtual flow (qᵥ)</strong> is a model-derived mismatch used
                for scoring — not a measured water loss at that node.
              </p>
              <div className="tiger-table-wrap">
                <table className="tiger-table">
                  <thead>
                    <tr>
                      <th>Sensor</th>
                      <th title="Calibrated absolute z-score">|z| (cal)</th>
                      <th title="Dual-context residual flow">δ (m³/h)</th>
                      <th title="Scale used for calibration">σ scale (m³/h)</th>
                      <th title="Model-derived virtual flow mismatch">
                        Virtual flow qᵥ (m³/h)
                      </th>
                      <th>Inspect</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.contributors.map((c) => {
                      const selected = selectedSensorId === c.sensor_id;
                      return (
                        <tr
                          key={c.sensor_id}
                          className={selected ? "method-m-contrib-selected" : undefined}
                        >
                          <td>
                            {c.sensor_id}
                            {data.argmax_sensor_id === c.sensor_id ? " · max" : ""}
                          </td>
                          <td>{fmtScore(c.abs_z_calibrated)}</td>
                          <td>{fmtScore(c.delta_m3h)}</td>
                          <td>{fmtScore(c.sigma_scale_m3h)}</td>
                          <td>{fmtScore(c.qv_m3h)}</td>
                          <td>
                            <button
                              type="button"
                              className="btn btn-inspect"
                              aria-label={`Inspect sensor ${c.sensor_id}`}
                              aria-pressed={selected}
                              onClick={() => onInspectSensor?.(c.sensor_id)}
                              disabled={!onInspectSensor}
                            >
                              Inspect sensor
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <details className="method-m-tech">
            <summary>Technical methodology and version hashes</summary>
            <p className="channel-note">
              Serving store:{" "}
              <strong>
                {data.store === "tiger"
                  ? "Tiger (database)"
                  : data.store === "file"
                    ? "file artifact"
                    : (data.store ?? "file artifact")}
              </strong>
              {data.store === "tiger" && data.run_id ? (
                <>
                  {" "}
                  · run <code>{data.run_id}</code>
                </>
              ) : null}
              . Threshold τ = {fmtScore(data.threshold)} (recover{" "}
              {fmtScore(data.recover_threshold)}). Resolution{" "}
              {data.resolution === "five_minute" ? "five-minute" : data.resolution}.
              Calibration sha256{" "}
              <code>{data.version_hashes.calibration_sha256 ?? "—"}</code>
              {data.version_hashes.tau_sha256 ? (
                <>
                  {" "}
                  · τ sha256 <code>{data.version_hashes.tau_sha256}</code>
                </>
              ) : null}
              {data.version_hashes.serving_hours_sha256 ? (
                <>
                  {" "}
                  · serving_hours sha256{" "}
                  <code>{data.version_hashes.serving_hours_sha256}</code>
                </>
              ) : null}
            </p>
            {data.resolution_note ? (
              <p className="channel-note">{data.resolution_note}</p>
            ) : null}
          </details>
        </div>
      )}
    </section>
  );
}
