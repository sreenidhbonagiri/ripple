import { useEffect, useRef } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import type {
  FreshnessStatus,
  NetworkLink,
  NetworkNode,
  Selection,
  Sensor,
  SnapshotObservation,
} from "../types";

interface Props {
  nodes: NetworkNode[];
  links: NetworkLink[];
  sensors: Sensor[];
  observations: SnapshotObservation[];
  onSelect: (selection: Selection) => void;
  fitToken: number;
}

const NODE_COLORS: Record<NetworkNode["type"], string> = {
  Junction: "#1a6b7a",
  Reservoir: "#0d4a3a",
  Tank: "#b35c1e",
};

const LINK_COLORS: Record<NetworkLink["type"], string> = {
  Pipe: "#5a7a86",
  Pump: "#8b3a2a",
  Valve: "#6b5a8a",
};

const STATUS_COLOR: Record<FreshnessStatus, string> = {
  current: "#2f7d4a",
  stale: "#b07a12",
  missing: "#8b3a2a",
};

function toElements(
  nodes: NetworkNode[],
  links: NetworkLink[],
  sensors: Sensor[],
  observations: SnapshotObservation[],
): ElementDefinition[] {
  const nodeIds = new Set(nodes.map((n) => n.id));
  const obsBySensor = new Map(observations.map((o) => [o.sensor_id, o]));
  const sensorByElement = new Map(sensors.map((s) => [s.network_element_id, s]));
  const elements: ElementDefinition[] = [];

  for (const node of nodes) {
    const pos = node.coordinates
      ? { x: node.coordinates.x, y: -node.coordinates.y }
      : undefined;
    const sensor = sensorByElement.get(node.id);
    elements.push({
      group: "nodes",
      data: {
        id: node.id,
        label: node.id,
        nodeType: node.type,
        raw: node,
        hasSensor: Boolean(sensor),
        sensorId: sensor?.id ?? null,
      },
      position: pos,
      selectable: true,
      grabbable: false,
    });
  }

  for (const link of links) {
    if (!nodeIds.has(link.start_node) || !nodeIds.has(link.end_node)) continue;
    const sensor = sensorByElement.get(link.id);
    elements.push({
      group: "edges",
      data: {
        id: link.id,
        source: link.start_node,
        target: link.end_node,
        label: link.id,
        linkType: link.type,
        raw: link,
        hasSensor: Boolean(sensor),
        sensorId: sensor?.id ?? null,
      },
      selectable: true,
    });
  }

  // Sensor markers as overlay nodes near mapped elements
  for (const sensor of sensors) {
    const obs = obsBySensor.get(sensor.id);
    const status: FreshnessStatus = obs?.status ?? "missing";
    let position: { x: number; y: number } | undefined;

    if (sensor.network_element_kind === "node") {
      const host = nodes.find((n) => n.id === sensor.network_element_id);
      if (host?.coordinates) {
        position = { x: host.coordinates.x + 8, y: -host.coordinates.y - 8 };
      }
    } else {
      const link = links.find((l) => l.id === sensor.network_element_id);
      if (link) {
        const a = nodes.find((n) => n.id === link.start_node)?.coordinates;
        const b = nodes.find((n) => n.id === link.end_node)?.coordinates;
        if (a && b) {
          position = { x: (a.x + b.x) / 2, y: -((a.y + b.y) / 2) };
        }
      }
    }

    elements.push({
      group: "nodes",
      data: {
        id: `sensor:${sensor.id}`,
        label: sensor.id,
        nodeType: "Sensor",
        sensorRaw: sensor,
        freshness: status,
      },
      position,
      selectable: true,
      grabbable: false,
    });
  }

  return elements;
}

export default function NetworkMap({
  nodes,
  links,
  sensors,
  observations,
  onSelect,
  fitToken,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      elements: toElements(nodes, links, sensors, observations),
      layout: { name: "preset", fit: true, padding: 40 },
      wheelSensitivity: 0.35,
      minZoom: 0.05,
      maxZoom: 8,
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "font-size": 7,
            "font-family": "DM Sans, sans-serif",
            color: "#1a2a30",
            "text-outline-width": 2,
            "text-outline-color": "#f2f6f4",
            "background-color": (ele) => {
              if (ele.data("nodeType") === "Sensor") {
                return STATUS_COLOR[ele.data("freshness") as FreshnessStatus] ?? "#8b3a2a";
              }
              return NODE_COLORS[ele.data("nodeType") as NetworkNode["type"]] ?? "#1a6b7a";
            },
            width: 10,
            height: 10,
            "border-width": 1,
            "border-color": "#0a1a1e",
          },
        },
        {
          selector: 'node[nodeType = "Reservoir"]',
          style: { shape: "diamond", width: 16, height: 16 },
        },
        {
          selector: 'node[nodeType = "Tank"]',
          style: { shape: "round-rectangle", width: 14, height: 14 },
        },
        {
          selector: 'node[nodeType = "Sensor"]',
          style: {
            shape: "triangle",
            width: 12,
            height: 12,
            "font-size": 8,
            "z-index": 20,
          },
        },
        {
          selector: "node[hasSensor]",
          style: {
            "border-width": 2,
            "border-color": "#c45c26",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": (ele) =>
              LINK_COLORS[ele.data("linkType") as NetworkLink["type"]] ?? "#5a7a86",
            "curve-style": "haystack",
            "haystack-radius": 0,
            opacity: 0.85,
          },
        },
        {
          selector: 'edge[linkType = "Pump"]',
          style: { width: 2.5, "line-style": "dashed" },
        },
        {
          selector: 'edge[linkType = "Valve"]',
          style: { width: 2.5 },
        },
        {
          selector: "edge[hasSensor]",
          style: { width: 3, "line-color": "#c45c26" },
        },
        {
          selector: ":selected",
          style: {
            "border-width": 3,
            "border-color": "#c45c26",
            "line-color": "#c45c26",
            "background-color": "#c45c26",
            "z-index": 999,
          },
        },
      ],
    });

    cy.on("tap", "node", (evt) => {
      if (evt.target.data("nodeType") === "Sensor") {
        onSelectRef.current({ kind: "sensor", data: evt.target.data("sensorRaw") as Sensor });
        return;
      }
      const sensorId = evt.target.data("sensorId") as string | null;
      if (sensorId) {
        const sensor = sensors.find((s) => s.id === sensorId);
        if (sensor) {
          onSelectRef.current({ kind: "sensor", data: sensor });
          return;
        }
      }
      onSelectRef.current({ kind: "node", data: evt.target.data("raw") as NetworkNode });
    });

    cy.on("tap", "edge", (evt) => {
      const sensorId = evt.target.data("sensorId") as string | null;
      if (sensorId) {
        const sensor = sensors.find((s) => s.id === sensorId);
        if (sensor) {
          onSelectRef.current({ kind: "sensor", data: sensor });
          return;
        }
      }
      onSelectRef.current({ kind: "link", data: evt.target.data("raw") as NetworkLink });
    });

    cy.on("tap", (evt) => {
      if (evt.target === cy) onSelectRef.current(null);
    });

    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [nodes, links, sensors]); // rebuild topology when network/sensors change

  // Update freshness colors without full rebuild
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const obsBySensor = new Map(observations.map((o) => [o.sensor_id, o]));
    cy.nodes().forEach((ele) => {
      if (ele.data("nodeType") !== "Sensor") return;
      const sensor = ele.data("sensorRaw") as Sensor;
      const status = obsBySensor.get(sensor.id)?.status ?? "missing";
      ele.data("freshness", status);
    });
  }, [observations]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || fitToken === 0) return;
    cy.fit(undefined, 40);
  }, [fitToken]);

  return (
    <div
      className="network-map"
      ref={containerRef}
      role="img"
      aria-label="L-Town water network map with sensors"
    />
  );
}
