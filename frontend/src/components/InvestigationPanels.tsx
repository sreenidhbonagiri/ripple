import type { PressureComparison, ReadingPoint } from "../investigation";
import { CONTEXT, DISCLAIMER, findObservation } from "../investigation";
import type { Sensor, SnapshotObservation } from "../types";

interface Props {
  cursor: string | null;
  observations: SnapshotObservation[];
  selectedPressure: Sensor | null;
  pressureSeries: ReadingPoint[];
  pressureComparison: PressureComparison | null;
  seriesLoading: boolean;
}

function fmt(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

function ChannelCard({
  title,
  unit,
  observation,
  footnote,
}: {
  title: string;
  unit: string;
  observation: SnapshotObservation | null;
  footnote?: string;
}) {
  const status = observation?.status ?? "missing";
  return (
    <article className={`channel-card status-${status}`}>
      <h3>{title}</h3>
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
      {footnote && <p className="channel-note">{footnote}</p>}
    </article>
  );
}

export default function InvestigationPanels({
  cursor,
  observations,
  selectedPressure,
  pressureComparison,
  seriesLoading,
}: Props) {
  const p227 = findObservation(observations, CONTEXT.externalInflows[0].sensorId);
  const p235 = findObservation(observations, CONTEXT.externalInflows[1].sensorId);
  const pump = findObservation(observations, CONTEXT.internalTransfer.sensorId);
  const tank = findObservation(observations, CONTEXT.tankLevel.sensorId);
  const selectedObs = selectedPressure
    ? findObservation(observations, selectedPressure.id)
    : null;

  return (
    <section className="investigation" aria-label="Coordinated investigation evidence">
      <div className="investigation-header">
        <p className="replay-label">Historical benchmark replay</p>
        <p className="investigation-disclaimer">{DISCLAIMER}</p>
      </div>

      <div className="channel-grid">
        <article className={`channel-card status-${selectedObs?.status ?? "missing"}`}>
          <h3>
            {selectedPressure
              ? `Pressure ${selectedPressure.id}`
              : "Selected pressure"}
          </h3>
          {!selectedPressure && (
            <p className="channel-note">Select a pressure sensor on the map.</p>
          )}
          {selectedPressure && (
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
                <h4>Change vs 30 minutes earlier</h4>
                {seriesLoading && <p className="channel-note">Loading comparison…</p>}
                {!seriesLoading && pressureComparison && (
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
          unit="m³/h"
          observation={p227}
        />
        <ChannelCard
          title={CONTEXT.externalInflows[1].label}
          unit="m³/h"
          observation={p235}
        />
        <ChannelCard
          title={CONTEXT.internalTransfer.label}
          unit="m³/h"
          observation={pump}
          footnote="Internal transfer to tank — not external supply."
        />
        <ChannelCard
          title={CONTEXT.tankLevel.label}
          unit="m"
          observation={tank}
        />
      </div>

      {cursor && (
        <p className="investigation-cursor">Panels synchronized to cursor {cursor}</p>
      )}
    </section>
  );
}
