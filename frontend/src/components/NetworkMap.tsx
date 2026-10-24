import { useEffect, useRef } from "react";
import type { Core, ElementDefinition } from "cytoscape";
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
): ElementDefinition[] {
  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const nodeIds = new Set(nodeById.keys());
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
      classes: [`ntype-${node.type}`, sensor ? "has-sensor" : ""].filter(Boolean).join(" "),
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
      classes: [`ltype-${link.type}`, sensor ? "has-sensor" : ""].filter(Boolean).join(" "),
    });
  }

  for (const sensor of sensors) {
    let position: { x: number; y: number } | undefined;

    if (sensor.network_element_kind === "node") {
      const host = nodeById.get(sensor.network_element_id);
      if (host?.coordinates) {
        position = { x: host.coordinates.x + 8, y: -host.coordinates.y - 8 };
      }
    } else {
      const link = links.find((l) => l.id === sensor.network_element_id);
      if (link) {
        const a = nodeById.get(link.start_node)?.coordinates;
        const b = nodeById.get(link.end_node)?.coordinates;
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
        freshness: "missing" as FreshnessStatus,
      },
      position,
      selectable: true,
      grabbable: false,
      classes: "ntype-Sensor freshness-missing",
    });
  }

  return elements;
}

function yieldToPaint(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  });
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
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    let cy: Core | null = null;

    const run = async () => {
      // Let React paint map-meta / presenter chrome before heavy map work.
      await yieldToPaint();
      if (cancelled) return;

      const { default: cytoscape } = await import("cytoscape");
      if (cancelled || !containerRef.current) return;

      performance.mark("ripple-cy-import-done");
      cy = cytoscape({
        container: containerRef.current,
        elements: toElements(nodes, links, sensors),
        layout: { name: "preset", fit: true, padding: 40 },
        textureOnViewport: true,
        hideEdgesOnViewport: true,
        pixelRatio: 1,
        wheelSensitivity: 0.35,
        minZoom: 0.05,
        maxZoom: 8,
        style: [
          {
            selector: "node",
            style: {
              label: "",
              "background-color": NODE_COLORS.Junction,
              width: 10,
              height: 10,
              "border-width": 1,
              "border-color": "#0a1a1e",
            },
          },
          {
            selector: "node.ntype-Reservoir",
            style: {
              shape: "diamond",
              width: 16,
              height: 16,
              "background-color": NODE_COLORS.Reservoir,
            },
          },
          {
            selector: "node.ntype-Tank",
            style: {
              shape: "round-rectangle",
              width: 14,
              height: 14,
              "background-color": NODE_COLORS.Tank,
            },
          },
          {
            selector: "node.ntype-Sensor",
            style: {
              shape: "triangle",
              width: 12,
              height: 12,
              label: "data(label)",
              "font-size": 8,
              "font-family": "DM Sans, sans-serif",
              color: "#1a2a30",
              "text-outline-width": 1,
              "text-outline-color": "#f2f6f4",
              "z-index": 20,
              "background-color": STATUS_COLOR.missing,
            },
          },
          {
            selector: "node.ntype-Sensor.freshness-current",
            style: { "background-color": STATUS_COLOR.current },
          },
          {
            selector: "node.ntype-Sensor.freshness-stale",
            style: { "background-color": STATUS_COLOR.stale },
          },
          {
            selector: "node.ntype-Sensor.freshness-missing",
            style: { "background-color": STATUS_COLOR.missing },
          },
          {
            selector: "node.has-sensor",
            style: { "border-width": 2, "border-color": "#c45c26" },
          },
          {
            selector: "edge",
            style: {
              width: 1.5,
              "line-color": LINK_COLORS.Pipe,
              "curve-style": "haystack",
              "haystack-radius": 0,
              opacity: 0.85,
            },
          },
          {
            selector: "edge.ltype-Pump",
            style: {
              width: 2.5,
              "line-style": "dashed",
              "line-color": LINK_COLORS.Pump,
            },
          },
          {
            selector: "edge.ltype-Valve",
            style: { width: 2.5, "line-color": LINK_COLORS.Valve },
          },
          {
            selector: "edge.has-sensor",
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
          onSelectRef.current({
            kind: "sensor",
            data: evt.target.data("sensorRaw") as Sensor,
          });
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

      if (cancelled) {
        cy.destroy();
        return;
      }
      cyRef.current = cy;
      performance.mark("ripple-cy-ready");
    };

    void run();

    return () => {
      cancelled = true;
      cy?.destroy();
      cyRef.current = null;
    };
  }, [nodes, links, sensors]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const obsBySensor = new Map(observations.map((o) => [o.sensor_id, o]));
    cy.batch(() => {
      cy.nodes(".ntype-Sensor").forEach((ele) => {
        const sensor = ele.data("sensorRaw") as Sensor;
        const status = obsBySensor.get(sensor.id)?.status ?? "missing";
        ele.data("freshness", status);
        ele.removeClass("freshness-current freshness-stale freshness-missing");
        ele.addClass(`freshness-${status}`);
      });
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
