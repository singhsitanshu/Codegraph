import { getCommunityColor } from "../utils/colors.js";

export const DEFAULT_EDGE_COLOR = "#789084";
const FOCUSED_EDGE_COLOR = "#178b6b";

export function buildAdjacencyIndex(edges) {
  const index = new Map();
  edges.forEach((edge) => {
    if (!index.has(edge.source)) {
      index.set(edge.source, { nodeIds: new Set(), edgeIds: new Set() });
    }
    if (!index.has(edge.target)) {
      index.set(edge.target, { nodeIds: new Set(), edgeIds: new Set() });
    }
    index.get(edge.source).nodeIds.add(edge.target);
    index.get(edge.source).edgeIds.add(edge.id);
    index.get(edge.target).nodeIds.add(edge.source);
    index.get(edge.target).edgeIds.add(edge.id);
  });
  return index;
}

export function highlightFocusedNodes(nodes, focusedNodeId, focusedConnections) {
  if (!focusedNodeId) return nodes;
  const neighborIds = focusedConnections?.nodeIds ?? new Set();

  return nodes.map((node) => {
    const isFocused = node.id === focusedNodeId;
    const isNeighbor = neighborIds.has(node.id);
    return {
      ...node,
      data: {
        ...node.data,
        focusState: isFocused
          ? "focused"
          : isNeighbor
            ? "neighbor"
            : "dimmed",
      },
      style: {
        ...node.style,
        opacity: isFocused || isNeighbor ? 1 : 0.1,
        transition: "opacity 150ms ease",
        zIndex: isFocused ? 20 : isNeighbor ? 10 : 0,
      },
    };
  });
}

export function highlightFocusedEdges(edges, focusedNodeId, focusedConnections) {
  const connectedEdgeIds = focusedConnections?.edgeIds ?? new Set();

  return edges.map((edge) => {
    const isConnected = Boolean(focusedNodeId) && connectedEdgeIds.has(edge.id);
    return {
      ...edge,
      animated: isConnected,
      markerEnd: {
        ...edge.markerEnd,
        color: isConnected ? FOCUSED_EDGE_COLOR : DEFAULT_EDGE_COLOR,
      },
      style: {
        ...edge.style,
        stroke: isConnected ? FOCUSED_EDGE_COLOR : DEFAULT_EDGE_COLOR,
        strokeWidth: isConnected ? 2.8 : 1,
        opacity: focusedNodeId ? (isConnected ? 1 : 0.08) : 0.35,
        transition: "opacity 150ms ease, stroke 150ms ease",
      },
      zIndex: isConnected ? 15 : 0,
    };
  });
}

export function colorNodesByCluster(nodes, activeClusters) {
  const isFilterActive = activeClusters.size > 0;
  return nodes.map((node) => {
    const communityColor = getCommunityColor(node.data?.community);
    const isSelected = activeClusters.has(node.data?.community);
    const shouldDim = isFilterActive && !isSelected;
    const currentOpacity = Number(node.style?.opacity ?? 1);
    return {
      ...node,
      data: {
        ...node.data,
        communityColor,
        clusterFilterState: shouldDim ? "dimmed" : "active",
      },
      style: {
        ...node.style,
        background: shouldDim ? "#334155" : node.style?.background,
        borderColor: shouldDim ? "#475569" : communityColor,
        boxShadow: shouldDim
          ? "none"
          : `0 0 12px color-mix(in srgb, ${communityColor} 28%, transparent)`,
        filter: shouldDim ? "grayscale(0.55)" : node.style?.filter,
        opacity: shouldDim ? Math.min(currentOpacity, 0.15) : currentOpacity,
        transition: "all 300ms ease",
      },
    };
  });
}

export function dimEdgesOutsideClusters(edges, nodes, activeClusters) {
  const nodeCommunities = new Map(
    nodes.map((node) => [node.id, node.data?.community]),
  );
  return edges.map((edge) => {
    const sourceActive = activeClusters.has(nodeCommunities.get(edge.source));
    const targetActive = activeClusters.has(nodeCommunities.get(edge.target));
    const shouldDim = !(sourceActive || targetActive);
    const currentOpacity = Number(edge.style?.opacity ?? 0.35);
    const stroke = shouldDim ? "#334155" : edge.style?.stroke;

    return {
      ...edge,
      animated: shouldDim ? false : edge.animated,
      markerEnd: {
        ...edge.markerEnd,
        color: stroke,
      },
      style: {
        ...edge.style,
        opacity: shouldDim
          ? Math.min(currentOpacity, 0.05)
          : Math.max(currentOpacity, 0.6),
        stroke,
        transition: "opacity 300ms ease, stroke 300ms ease",
      },
    };
  });
}

export function miniMapNodeColor(node, showClusters, activeClusters) {
  if (showClusters) {
    if (
      activeClusters.size > 0 &&
      !activeClusters.has(node.data?.community)
    ) {
      return "#cbd5e1";
    }
    return getCommunityColor(node.data?.community);
  }
  if (node.data?.nodeType === "File") return "#1e293b";
  if (node.data?.external) return "#d5a24e";
  return "#4f9c82";
}
