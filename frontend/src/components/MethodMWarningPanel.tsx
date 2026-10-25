import { useEffect, useState } from "react";
import { fetchMethodMWarning } from "../api";
import { formatDisplayTs } from "../time";
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

const ANOMALY_CONTRIBUTION_TITLE =
  "Calibrated absolute z-score (|z|) — how strongly this sensor’s flow mismatch diverges from its reference scale";

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
  const store = data?.store;
  const fromTiger = store === "tiger";

  return (
    <section
      id="panel-warning"
      className="method-m-panel app-panel"
      aria-label="Experimental warning"
      tabIndex={-1}
    >
      <div className="method-m-header">
        <h2 className="method-m-title">Experimental warning</h2>
        {matched && data && (
          <p className="method-m-provenance" role="note">
            {fromTiger
              ? "Warning evidence served from Tiger Data."
              : store === "file"
                ? "Warning evidence served from the frozen file artifact."
                : "Warning evidence store loading…"}
          </p>
        )}
      </div>

      {!cursor && (
        <p className="channel-note">
          Choose a replay cursor or Explore a warning to load status.
        </p>
      )}

      {showLoading && (
        <p className="channel-note" role="status">
          Loading warning…
        </p>
      )}

      {error && (
        <p className="state-copy" role="alert">
          {error}
        </p>
      )}

      {matched && data && (
        <div className="method-m-body">
          {data.warning_active ? (
            <div className="method-m-active" role="status">
              <p className="method-m-status">Experimental warning</p>
              <p className="method-m-explain">
                An unusual pattern was flagged. Review the evidence to
                investigate.
              </p>
              <p className="method-m-score">
                Anomaly score {fmtScore(data.score)}
                <span className="channel-unit">
                  {" "}
                  / threshold {fmtScore(data.threshold)}
                </span>
              </p>
              {data.notification?.notify_ts && (
                <p className="channel-note">
                  Notification {formatDisplayTs(data.notification.notify_ts)}
                </p>
              )}
            </div>
          ) : (
            <div className="method-m-idle" role="status">
              <p className="method-m-status">
                {data.status === "before_coverage" || data.status === "missing"
                  ? "No warning evidence at this cursor"
                  : "No warning at this time"}
              </p>
              {data.score !== null && data.score !== undefined && (
                <p className="method-m-score">
                  Anomaly score {fmtScore(data.score)}
                  <span className="channel-unit">
                    {" "}
                    / threshold {fmtScore(data.threshold)}
                  </span>
                </p>
              )}
            </div>
          )}

          {data.contributors.length > 0 && (
            <>
              <h3 className="details-section">
                {data.warning_active
                  ? "Contributing sensors"
                  : "Sensor deviations"}
              </h3>
              <p className="channel-note">
                Inspect a sensor to update the map and pressure chart.
              </p>
              {data.argmax_sensor_id ? (
                <p className="channel-note">
                  Strongest sensor: <strong>{data.argmax_sensor_id}</strong>
                </p>
              ) : null}
              <div className="tiger-table-wrap">
                <table className="tiger-table">
                  <thead>
                    <tr>
                      <th>Sensor</th>
                      <th title={ANOMALY_CONTRIBUTION_TITLE}>
                        Anomaly contribution
                      </th>
                      <th title="Change in flow mismatch (δ), m³/h">
                        Δ mismatch (m³/h)
                      </th>
                      <th title="Reference variability (σ_SCALE), m³/h">
                        Ref. variability (m³/h)
                      </th>
                      <th title="Model-estimated flow mismatch (qᵥ), m³/h">
                        Est. mismatch (m³/h)
                      </th>
                      <th>Inspect</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.contributors.map((c) => {
                      const selected = selectedSensorId === c.sensor_id;
                      const strongest = data.argmax_sensor_id === c.sensor_id;
                      return (
                        <tr
                          key={c.sensor_id}
                          className={
                            selected ? "method-m-contrib-selected" : undefined
                          }
                        >
                          <td>
                            {c.sensor_id}
                            {strongest ? " · strongest" : ""}
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
                              Inspect
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
            <summary>Method and evaluation</summary>
            <p className="channel-note">
              Score stamp ≤ cursor: {formatDisplayTs(data.score_hour)}.
              {data.data_age_hours !== null && data.data_age_hours !== undefined
                ? ` Data age ${data.data_age_hours.toFixed(2)} h.`
                : ""}
              {data.peak_score_observed_to_cursor !== null &&
              data.peak_score_observed_to_cursor !== undefined
                ? ` Peak to cursor ${fmtScore(data.peak_score_observed_to_cursor)}.`
                : ""}
            </p>
            <p className="channel-note">
              Five-minute Method M anomaly scores on the historical benchmark.
              <strong> Anomaly contribution</strong> is the calibrated absolute
              z-score (|z|) — how strongly a sensor’s flow mismatch diverges from
              its reference scale (σ_SCALE). Model-estimated flow mismatch (qᵥ)
              is a dual-context residual; δ is the change in that mismatch.
              Strongest sensor is argmax of calibrated |z|. Sensors are
              investigation evidence, not predicted leak pipes.
            </p>
            <p className="channel-note">
              Store:{" "}
              <strong>
                {fromTiger
                  ? "Tiger Data"
                  : store === "file"
                    ? "file artifact"
                    : (store ?? "—")}
              </strong>
              {fromTiger && data.run_id ? (
                <>
                  {" "}
                  · run <code>{data.run_id}</code>
                </>
              ) : null}
              . Threshold τ = {fmtScore(data.threshold)} (recover{" "}
              {fmtScore(data.recover_threshold)}). Resolution{" "}
              {data.resolution === "five_minute" ? "five-minute" : data.resolution}
              . Calibration sha256{" "}
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
