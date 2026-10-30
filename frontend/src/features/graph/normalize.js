import { MarkerType, Position } from "@xyflow/react";

import { DEFAULT_EDGE_COLOR } from "./highlighting.js";
import { applyForceLayout, getInitialCenter } from "./layout.js";

function basename(path) {
  return String(path).split(/[\\/]/).pop() || String(path);
}

function getNodeKind(raw, data) {
  const labels = raw.labels ?? data.labels ?? [];
  if (labels.includes("File")) return "File";
  if (labels.includes("Function")) return "Function";
  return data.nodeType ?? raw.nodeType ?? "Function";
}

function normalizeNodes(rawNodes) {
  return rawNodes.map((raw, index) => {
    const data = raw.data ?? {};
    const external = raw.external ?? data.external ?? false;
    const community =
      raw.community_id ??
      data.community_id ??
      raw.community ??
      data.community ??
      raw.leiden_community ??
      data.leiden_community ??
      null;
    const communityName =
      raw.community_name ??
      data.community_name ??
      (community === null || community === undefined
        ? null
        : `Cluster #${community}`);
    const communityDescription =
      raw.community_description ?? data.community_description ?? null;
    const nodeType = getNodeKind(raw, data);
    const fullLabel = String(
      data.label ??
        raw.label ??
        raw.qualified_name ??
        raw.name ??
        `Function ${index + 1}`,
    );
    return {
      ...raw,
      id: String(raw.id ?? raw.elementId ?? index),
      type: nodeType === "File" ? "fileHub" : "graphNode",
      position: { x: 0, y: 0 },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      data: {
        ...data,
        community,
        communityName,
        communityDescription,
        external,
        fullLabel,
        displayName: basename(fullLabel),
        label: fullLabel,
        nodeType,
      },
      style: { ...raw.style },
    };
  });
}

function normalizeEdges(rawEdges) {
  return rawEdges.map((edge, index) => ({
    ...edge,
    id: String(edge.id ?? `edge-${index}`),
    source: String(edge.source ?? edge.caller_id),
    target: String(edge.target ?? edge.callee_id),
    type: "straight",
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: DEFAULT_EDGE_COLOR,
      width: 18,
      height: 18,
    },
    style: {
      ...edge.style,
      stroke: DEFAULT_EDGE_COLOR,
      strokeWidth: 1.35,
      opacity: 0.35,
    },
    interactionWidth: 16,
  }));
}

export function normalizeGraph(payload) {
  const normalizedNodes = normalizeNodes(payload.nodes ?? payload.functions ?? []);
  const edges = normalizeEdges(payload.edges ?? payload.calls ?? []);
  const nodes = applyForceLayout(normalizedNodes, edges);
  return {
    nodes,
    edges,
    initialCenter: getInitialCenter(nodes),
  };
}
