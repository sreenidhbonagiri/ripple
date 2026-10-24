import { lazy, Suspense } from "react";
import type { ReadingPoint } from "../investigation";
import type {
  NetworkCounts,
  Selection,
  SnapshotObservation,
} from "../types";

const SensorChart = lazy(() => import("./SensorChart"));
const PressureHistoryPanel = lazy(() => import("./PressureHistoryPanel"));

type PanelAsync = "idle" | "loading" | "ready" | "error";

interface Props {
  selection: Selection;
  counts: NetworkCounts | null;
  networkName: string | null;
  source: string | null;
  coordinateSystem: string | null;
  observation: SnapshotObservation | null;
  observationStatus: PanelAsync;
  observationError: string | null;
  cursor: string | null;
  series: ReadingPoint[];
  seriesStatus: PanelAsync;
  seriesError: string | null;
}

function Row({
  label,
  value,
}: {
  label: string;
  value: string | number | boolean | null | undefined;
}) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="detail-row">
      <dt>{label}</dt>
      <dd>{String(value)}</dd>
    </div>
  );
}

export default function DetailsPanel({
  selection,
  counts,
  networkName,
  source,
  coordinateSystem,
  observation,
  observationStatus,
  observationError,
  cursor,
  series,
  seriesStatus,
  seriesError,
}: Props) {
  return (
    <aside className="details-panel">
      <header className="details-header">
        <p className="eyebrow">Historical benchmark replay</p>
        <h2>
          {selection
            ? selection.kind === "node"
              ? "Node"
              : selection.kind === "link"
                ? "Link"
                : "Sensor"
            : "Network"}
        </h2>
      </header>

      {!selection && (
        <div className="details-body">
          <Row label="Model" value={networkName} />
          <Row label="Source file" value={source} />
          <Row label="Coordinates" value={coordinateSystem} />
          {counts && (
            <>
              <h3 className="details-section">Counts (from parsed model)</h3>
              <Row label="Nodes" value={counts.nodes} />
              <Row label="Junctions" value={counts.junctions} />
              <Row label="Reservoirs" value={counts.reservoirs} />
              <Row label="Tanks" value={counts.tanks} />
              <Row label="Links" value={counts.links} />
              <Row label="Pipes" value={counts.pipes} />
              <Row label="Pumps" value={counts.pumps} />
              <Row label="Valves" value={counts.valves} />
            </>
          )}
          <p className="hint">
            Select a pressure sensor to inspect coordinated supply, pump
            transfer, and tank context. Measurements do not confirm a leak.
          </p>
        </div>
      )}

      {selection?.kind === "node" && (
        <div className="details-body">
          <Row label="ID" value={selection.data.id} />
          <Row label="Type" value={selection.data.type} />
          <Row label="X" value={selection.data.coordinates?.x} />
          <Row label="Y" value={selection.data.coordinates?.y} />
          <Row label="Elevation" value={selection.data.elevation} />
          <Row label="Base demand" value={selection.data.base_demand} />
        </div>
      )}

      {selection?.kind === "link" && (
        <div className="details-body">
          <Row label="ID" value={selection.data.id} />
          <Row label="Type" value={selection.data.type} />
          <Row label="Start node" value={selection.data.start_node} />
          <Row label="End node" value={selection.data.end_node} />
          <Row label="Length" value={selection.data.length} />
          <Row label="Diameter" value={selection.data.diameter} />
        </div>
      )}

      {selection?.kind === "sensor" && (
        <div className="details-body">
          <Row label="Sensor" value={selection.data.id} />
          <Row label="Type" value={selection.data.measurement_type} />
          <Row label="Unit" value={selection.data.unit} />
          <Row label="Network element" value={selection.data.network_element_id} />
          <h3 className="details-section">At cursor</h3>
          {observationStatus === "loading" && (
            <p className="channel-note">Loading observation…</p>
          )}
          {observationStatus === "error" && (
            <p className="channel-note chart-error">
              Snapshot error{observationError ? `: ${observationError}` : ""}
            </p>
          )}
          {observationStatus === "ready" && observation && (
            <>
              <Row label="Status" value={observation.status} />
              <Row label="Value" value={observation.value} />
              <Row label="Observed" value={observation.observation_ts} />
              <Row label="Age (s)" value={observation.age_seconds} />
            </>
          )}
          {observationStatus === "ready" && !observation && (
            <p className="channel-note">No observation ≤ cursor for this sensor.</p>
          )}
          <h3 className="details-section">Detailed replay chart (5-minute)</h3>
          <Suspense fallback={<p className="channel-note">Loading chart…</p>}>
            <SensorChart
              sensor={selection.data}
              series={series}
              loading={seriesStatus === "loading"}
              error={seriesStatus === "error" ? seriesError : null}
            />
            {selection.data.measurement_type === "pressure" && cursor && (
              <PressureHistoryPanel sensor={selection.data} cursor={cursor} />
            )}
          </Suspense>
        </div>
      )}
    </aside>
  );
}
