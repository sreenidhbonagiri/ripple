import type { PressureComparison } from "../investigation";
import { CONTEXT, DISCLAIMER, findObservation } from "../investigation";
import type { Sensor, SnapshotObservation } from "../types";

type PanelAsync = "idle" | "loading" | "ready" | "error";

interface Props {
  cursor: string | null;
  observations: SnapshotObservation[];
  snapshotStatus: PanelAsync;
  snapshotMatched: boolean;
  snapshotError: string | null;
  selectedPressure: Sensor | null;
  pressureComparison: PressureComparison | null;
  seriesStatus: PanelAsync;
  seriesMatched: boolean;
  seriesError: string | null;
}

function fmt(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

function ChannelCard({
  title,
  unit,
  hint,
  observation,
  loading,
}: {
  title: string;
  unit: string;
  hint?: string;
  observation: SnapshotObservation | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <article className="channel-card status-loading">
        <h3>{title}</h3>
        {hint && <p className="channel-note">{hint}</p>}
        <p className="channel-note">Loading…</p>
      </article>
    );
  }
  const status = observation?.status ?? "missing";
  return (
    <article className={`channel-card status-${status}`}>
      <h3>{title}</h3>
      {hint && <p className="channel-note">{hint}</p>}
      <p className="channel-value">
        {observation?.value === null || observation?.value === undefined
          ? "—"
          : fmt(observation.value)}
        <span className="channel-unit">{unit}</span>
      </p>
      <p className="channel-meta">
        <span className={`pill pill-${status}`}>{status}</span>
        {observation?.observation_ts
          ? ` · ${String(observation.observation_ts).replace("T", " ").slice(0, 19)}`
          : " · no observation ≤ cursor"}
      </p>
    </article>
  );
}

export default function InvestigationPanels({
  cursor,
  observations,
  snapshotStatus,
  snapshotMatched,
  snapshotError,
  selectedPressure,
  pressureComparison,
  seriesStatus,
  seriesMatched,
  seriesError,
}: Props) {
  const channelsLoading = Boolean(cursor) && !snapshotMatched && snapshotStatus === "loading";
  const channelsError = Boolean(cursor) && snapshotStatus === "error" && !snapshotMatched;

  const p227 = findObservation(observations, CONTEXT.externalInflows[0].sensorId);
  const p235 = findObservation(observations, CONTEXT.externalInflows[1].sensorId);
  const pump = findObservation(observations, CONTEXT.internalTransfer.sensorId);
  const tank = findObservation(observations, CONTEXT.tankLevel.sensorId);
  const selectedObs = selectedPressure
    ? findObservation(observations, selectedPressure.id)
    : null;

  const comparisonLoading =
    Boolean(selectedPressure) && !seriesMatched && seriesStatus === "loading";

  return (
    <section className="investigation" aria-label="Coordinated investigation evidence">
      <div className="investigation-header">
        <p className="replay-label">Historical benchmark replay</p>
        <p className="investigation-disclaimer">{DISCLAIMER}</p>
      </div>

      {channelsError && (
        <p className="channel-note chart-error" role="alert">
          Snapshot error{snapshotError ? `: ${snapshotError}` : ""}
        </p>
      )}

      <div className="channel-grid">
        <article
          className={`channel-card status-${
            channelsLoading ? "loading" : (selectedObs?.status ?? "missing")
          }`}
        >
          <h3>
            {selectedPressure
              ? `Selected pressure ${selectedPressure.id}`
              : "Selected pressure"}
          </h3>
          <p className="channel-note">Observed head / pressure (m)</p>
          {!selectedPressure && (
            <p className="channel-note">Select a pressure sensor on the map.</p>
          )}
          {selectedPressure && channelsLoading && (
            <p className="channel-note">Loading snapshot…</p>
          )}
          {selectedPressure && !channelsLoading && snapshotMatched && (
            <>
              <p className="channel-value">
                {fmt(selectedObs?.value)}
                <span className="channel-unit">m</span>
              </p>
              <p className="channel-meta">
                <span className={`pill pill-${selectedObs?.status ?? "missing"}`}>
                  {selectedObs?.status ?? "missing"}
                </span>
                {selectedObs?.observation_ts
                  ? ` · ${String(selectedObs.observation_ts).replace("T", " ").slice(0, 19)}`
                  : " · no observation ≤ cursor"}
              </p>
              <div className="pressure-delta">
                <h4>Change vs 30 minutes earlier (m)</h4>
                {comparisonLoading && (
                  <p className="channel-note">Loading comparison…</p>
                )}
                {!comparisonLoading && seriesStatus === "error" && (
                  <p className="channel-note chart-error">
                    Comparison error{seriesError ? `: ${seriesError}` : ""}
                  </p>
                )}
                {!comparisonLoading && seriesMatched && pressureComparison && (
                  <>
                    {pressureComparison.available ? (
                      <p className="channel-value delta">
                        {pressureComparison.deltaM! >= 0 ? "+" : ""}
                        {fmt(pressureComparison.deltaM)}
                        <span className="channel-unit">m</span>
                      </p>
                    ) : (
                      <p className="channel-note">
                        Comparison unavailable — {pressureComparison.unavailableReason}
                      </p>
                    )}
                    <p className="channel-meta">
                      prior {pressureComparison.priorStatus}
                      {pressureComparison.priorTs ? ` @ ${pressureComparison.priorTs}` : ""}
                      {" · "}
                      current {pressureComparison.currentStatus}
                      {pressureComparison.currentTs
                        ? ` @ ${pressureComparison.currentTs}`
                        : ""}
                    </p>
                    <p className="channel-note">
                      Observation only — not labeled as a leak.
                    </p>
                  </>
                )}
              </div>
            </>
          )}
        </article>

        <ChannelCard
          title={CONTEXT.externalInflows[0].label}
          unit={CONTEXT.externalInflows[0].unit}
          hint={CONTEXT.externalInflows[0].hint}
          observation={snapshotMatched ? p227 : null}
          loading={channelsLoading}
        />
        <ChannelCard
          title={CONTEXT.externalInflows[1].label}
          unit={CONTEXT.externalInflows[1].unit}
          hint={CONTEXT.externalInflows[1].hint}
          observation={snapshotMatched ? p235 : null}
          loading={channelsLoading}
        />
        <ChannelCard
          title={CONTEXT.internalTransfer.label}
          unit={CONTEXT.internalTransfer.unit}
          hint={CONTEXT.internalTransfer.hint}
          observation={snapshotMatched ? pump : null}
          loading={channelsLoading}
        />
        <ChannelCard
          title={CONTEXT.tankLevel.label}
          unit={CONTEXT.tankLevel.unit}
          hint={CONTEXT.tankLevel.hint}
          observation={snapshotMatched ? tank : null}
          loading={channelsLoading}
        />
      </div>

      {cursor && snapshotMatched && (
        <p className="investigation-cursor">
          Panels synchronized to cursor {cursor}
        </p>
      )}
      {cursor && channelsLoading && (
        <p className="investigation-cursor">Loading panels for cursor {cursor}…</p>
      )}
    </section>
  );
}
