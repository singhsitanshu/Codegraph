import { useCallback, useMemo, useState } from "react";
import { useEdgesState, useNodesState } from "@xyflow/react";

import { fetchRepositoryGraph } from "../../shared/api.js";
import {
  buildAdjacencyIndex,
  colorNodesByCluster,
  dimEdgesOutsideClusters,
  highlightFocusedEdges,
  highlightFocusedNodes,
} from "./highlighting.js";
import { routeEdgesToNearestHandles } from "./layout.js";
import { normalizeGraph } from "./normalize.js";
import {
  buildCommunityLegend,
  toggleClusterSelection,
} from "./communities.js";

// Owns the loaded repository graph and how it is presented: hover focus,
// architectural cluster colouring and the cluster filter.
export default function useCodeGraph() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [focusedNodeId, setFocusedNodeId] = useState(null);
  const [initialCenter, setInitialCenter] = useState(null);
  // { status: "idle" | "loading" | "ready" } or { status: "error", error }
  const [graphLoad, setGraphLoad] = useState({ status: "idle" });
  const [showClusters, setShowClusters] = useState(false);
  const [activeClusters, setActiveClusters] = useState(() => new Set());

  const adjacencyIndex = useMemo(() => buildAdjacencyIndex(edges), [edges]);

  const focusedConnections = focusedNodeId
    ? adjacencyIndex.get(focusedNodeId)
    : null;

  const graphCounts = useMemo(
    () => ({
      files: nodes.filter((node) => node.data.nodeType === "File").length,
      functions: nodes.filter((node) => node.data.nodeType === "Function").length,
    }),
    [nodes],
  );
  const routedEdges = useMemo(
    () => routeEdgesToNearestHandles(edges, nodes),
    [edges, nodes],
  );

  const visibleNodes = useMemo(
    () => highlightFocusedNodes(nodes, focusedNodeId, focusedConnections),
    [focusedConnections, focusedNodeId, nodes],
  );

  const styledNodes = useMemo(() => {
    if (!showClusters) return visibleNodes;
    return colorNodesByCluster(visibleNodes, activeClusters);
  }, [activeClusters, showClusters, visibleNodes]);

  const communityLegend = useMemo(
    () => buildCommunityLegend(nodes),
    [nodes],
  );

  const visibleEdges = useMemo(
    () => highlightFocusedEdges(routedEdges, focusedNodeId, focusedConnections),
    [focusedConnections, focusedNodeId, routedEdges],
  );

  const styledEdges = useMemo(() => {
    if (!showClusters || activeClusters.size === 0) return visibleEdges;
    return dimEdgesOutsideClusters(visibleEdges, nodes, activeClusters);
  }, [activeClusters, nodes, showClusters, visibleEdges]);

  const toggleCluster = useCallback((communityId) => {
    setShowClusters(true);
    setActiveClusters((current) =>
      toggleClusterSelection(current, communityId),
    );
  }, []);

  const clearClusterFilters = useCallback(() => {
    setActiveClusters(new Set());
  }, []);

  const toggleShowClusters = () => setShowClusters((current) => !current);

  const loadGraph = useCallback(async (repoName) => {
    if (!repoName) {
      setNodes([]);
      setEdges([]);
      setInitialCenter(null);
      setFocusedNodeId(null);
      setActiveClusters(new Set());
      setGraphLoad({ status: "idle" });
      return;
    }

    setGraphLoad({ status: "loading" });
    try {
      const graph = normalizeGraph(await fetchRepositoryGraph(repoName));
      setNodes(graph.nodes);
      setEdges(graph.edges);
      setInitialCenter(graph.initialCenter);
      setFocusedNodeId(null);
      setGraphLoad({ status: "ready" });
    } catch (error) {
      setGraphLoad({
        status: "error",
        error: error instanceof Error ? error.message : "Could not load graph",
      });
    }
  }, [setEdges, setNodes]);

  // Empties the graph and its presentation when the repository goes away or a
  // new one starts ingesting.
  const clearGraph = () => {
    setNodes([]);
    setEdges([]);
    setInitialCenter(null);
    setFocusedNodeId(null);
    setGraphLoad({ status: "idle" });
    setShowClusters(false);
    setActiveClusters(new Set());
  };

  return {
    nodes,
    edges,
    styledNodes,
    styledEdges,
    onNodesChange,
    onEdgesChange,
    focusNode: setFocusedNodeId,
    initialCenter,
    graphLoad,
    graphStatus: graphLoad.status,
    graphCounts,
    communityLegend,
    showClusters,
    activeClusters,
    toggleCluster,
    clearClusterFilters,
    toggleShowClusters,
    loadGraph,
    clearGraph,
  };
}
