import GraphCanvas from "./GraphCanvas.jsx";
import Icon from "./Icon.jsx";
import ModulesMenu from "./ModulesMenu.jsx";

export default function GraphPanel({
  graph,
  repository,
  isGraphMaximized,
  onToggleGraphMaximized,
  onNodeClick,
}) {
  const { activeRepo, isDeleting } = repository;
  const { graphCounts, graphStatus, showClusters } = graph;
  const graphControlsDisabled =
    graph.nodes.length === 0 || graphStatus === "loading";

  return (
    <section className="relative hidden min-h-0 min-w-0 overflow-hidden bg-[#eef1eb] lg:block">
      <div className="absolute inset-x-0 top-0 z-10 flex h-[76px] items-center justify-between border-b border-[#d9e0da]/90 bg-[#f3f5f0]/90 px-7 backdrop-blur">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-extrabold tracking-[-0.01em]">Function map</h2>
            <span className="rounded-md bg-[#e0e7e1] px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] text-[#677a72]">
              Live
            </span>
          </div>
          <p className="mt-1 text-[10px] font-medium text-[#83918b]">
            {graphCounts.files} files · {graphCounts.functions} functions · {graph.edges.length} relationships
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ModulesMenu graph={graph} disabled={graphControlsDisabled} />
          <button
            type="button"
            aria-pressed={showClusters}
            aria-label={
              showClusters
                ? "Hide architectural clusters"
                : "Show architectural clusters"
            }
            onClick={graph.toggleShowClusters}
            disabled={graphControlsDisabled}
            className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-[9px] font-extrabold uppercase tracking-[0.09em] shadow-sm transition disabled:cursor-not-allowed disabled:opacity-40 ${
              showClusters
                ? "border-[#5145a6] bg-[#5b4fc4] text-white"
                : "border-[#d7ded8] bg-white text-[#52645d] hover:border-[#bfcac2]"
            }`}
          >
            <span
              aria-hidden="true"
              className={`size-2.5 rounded-full ${
                showClusters ? "bg-[#d9d5ff]" : "bg-[#8f83e8]"
              }`}
            />
            <span className="hidden 2xl:inline">
              {showClusters ? "Hide Sub-Systems" : "Architectural Clusters"}
            </span>
            <span className="2xl:hidden">Clusters</span>
          </button>
          <button
            type="button"
            onClick={() => graph.loadGraph(activeRepo)}
            disabled={!activeRepo || graphStatus === "loading" || isDeleting}
            className="inline-flex items-center gap-2 rounded-xl border border-[#d7ded8] bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.11em] text-[#52645d] shadow-sm transition hover:border-[#bfcac2] disabled:opacity-50"
          >
            <Icon name="refresh" className={`size-3.5 ${graphStatus === "loading" ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      <GraphCanvas
        graph={graph}
        activeRepo={activeRepo}
        isGraphMaximized={isGraphMaximized}
        onToggleGraphMaximized={onToggleGraphMaximized}
        onNodeClick={onNodeClick}
      />
    </section>
  );
}
