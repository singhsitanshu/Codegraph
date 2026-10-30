import { useEffect, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  MiniMap,
  ReactFlow,
} from "@xyflow/react";

import { miniMapNodeColor } from "../graph/highlighting.js";
import GraphControls from "./GraphControls.jsx";
import { nodeTypes } from "./GraphNodes.jsx";
import Icon from "./Icon.jsx";

const INITIAL_ZOOM = 1;

export default function GraphCanvas({
  graph,
  activeRepo,
  isGraphMaximized,
  onToggleGraphMaximized,
  onNodeClick,
}) {
  const [flowReady, setFlowReady] = useState(false);
  const flowInstanceRef = useRef(null);
  const { activeClusters, graphLoad, graphStatus, initialCenter, showClusters } = graph;

  useEffect(() => {
    if (
      graphStatus !== "ready" ||
      !flowReady ||
      !initialCenter ||
      !flowInstanceRef.current
    ) {
      return undefined;
    }
    const frame = requestAnimationFrame(() => {
      flowInstanceRef.current?.setCenter(initialCenter.x, initialCenter.y, {
        zoom: INITIAL_ZOOM,
        duration: 350,
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [flowReady, graphStatus, initialCenter]);

  return (
    <div className="absolute inset-0 pt-[76px]">
      {graphStatus === "error" ? (
        <div className="grid h-full place-items-center p-8 text-center">
          <div>
            <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-white text-[#9b5a4e] shadow-sm">
              <Icon name="graph" className="size-5" />
            </div>
            <p className="mt-4 text-sm font-bold">Graph unavailable</p>
            <p className="mt-1 text-xs text-[#7d8b85]">{graphLoad.error}</p>
            <button
              onClick={() => graph.loadGraph(activeRepo)}
              className="mt-4 text-xs font-bold text-[#276d54] underline underline-offset-4"
            >
              Try again
            </button>
          </div>
        </div>
      ) : graphStatus === "loading" ? (
        <div className="grid h-full place-items-center p-8 text-center">
          <div>
            <Icon name="refresh" className="mx-auto size-5 animate-spin text-[#52645d]" />
            <p className="mt-3 text-xs font-bold text-[#677a72]">
              Loading {activeRepo}…
            </p>
          </div>
        </div>
      ) : graph.nodes.length === 0 ? (
        <div className="grid h-full place-items-center p-8 text-center">
          <div className="max-w-xs">
            <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-white text-[#789084] shadow-sm">
              <Icon name="graph" className="size-5" />
            </div>
            <p className="mt-4 text-sm font-bold text-[#52645d]">
              Enter a GitHub URL above and click Ingest to visualize a
              repository graph.
            </p>
          </div>
        </div>
      ) : (
        <ReactFlow
          nodes={graph.styledNodes}
          edges={graph.styledEdges}
          nodeTypes={nodeTypes}
          onNodesChange={graph.onNodesChange}
          onEdgesChange={graph.onEdgesChange}
          onInit={(instance) => {
            flowInstanceRef.current = instance;
            setFlowReady(true);
          }}
          onNodeMouseEnter={(_, node) => graph.focusNode(node.id)}
          onNodeMouseLeave={() => graph.focusNode(null)}
          onNodeClick={onNodeClick}
          defaultViewport={{ x: 0, y: 0, zoom: INITIAL_ZOOM }}
          minZoom={0.15}
          maxZoom={1.8}
          onlyRenderVisibleElements
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#cbd4cd" gap={24} size={1} variant={BackgroundVariant.Dots} />
          <GraphControls
            isGraphMaximized={isGraphMaximized}
            onToggleGraphMaximized={onToggleGraphMaximized}
          />
          <MiniMap
            pannable
            zoomable
            position="bottom-left"
            nodeColor={(node) =>
              miniMapNodeColor(node, showClusters, activeClusters)
            }
            maskColor="rgba(238, 241, 235, 0.75)"
          />
        </ReactFlow>
      )}
    </div>
  );
}
