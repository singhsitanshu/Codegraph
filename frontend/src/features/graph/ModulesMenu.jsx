import { useEffect, useRef, useState } from "react";

import GraphLegend from "./GraphLegend.tsx";

export default function ModulesMenu({ graph, disabled }) {
  const [modulesOpen, setModulesOpen] = useState(false);
  const modulesPopoverRef = useRef(null);
  const modulesButtonRef = useRef(null);
  const { communityLegend } = graph;

  useEffect(() => {
    if (!modulesOpen) return undefined;

    const handlePointerDown = (event) => {
      if (!modulesPopoverRef.current?.contains(event.target)) {
        setModulesOpen(false);
      }
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setModulesOpen(false);
        modulesButtonRef.current?.focus();
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [modulesOpen]);

  return (
    <div ref={modulesPopoverRef} className="relative">
      <button
        ref={modulesButtonRef}
        type="button"
        aria-expanded={modulesOpen}
        aria-haspopup="dialog"
        aria-controls="architectural-modules-popover"
        onClick={() => setModulesOpen((current) => !current)}
        disabled={disabled}
        className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-[9px] font-extrabold uppercase tracking-[0.09em] shadow-sm transition disabled:cursor-not-allowed disabled:opacity-40 ${
          modulesOpen
            ? "border-[#bfcac2] bg-[#f4f2ff] text-[#5145a6]"
            : "border-[#d7ded8] bg-white text-[#52645d] hover:border-[#bfcac2]"
        }`}
      >
        <span>Modules</span>
        {communityLegend.communities.length > 0 && (
          <span className="hidden rounded-md bg-[#e9e6ff] px-1.5 py-0.5 text-[8px] text-[#5b4fc4] xl:inline">
            {communityLegend.communities.length}
          </span>
        )}
        <svg
          aria-hidden="true"
          className={`size-3 transition-transform ${
            modulesOpen ? "rotate-180" : ""
          }`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="m6 9 6 6 6-6"
          />
        </svg>
      </button>
      {modulesOpen && (
        <div
          id="architectural-modules-popover"
          role="dialog"
          aria-label="Architectural modules"
          className="absolute right-0 top-full z-50 mt-2 w-[19rem] max-w-[calc(100vw_-_2rem)] overflow-hidden rounded-2xl border border-[#d7ded8] bg-white/95 shadow-[0_16px_40px_rgba(32,51,45,0.18)] backdrop-blur"
        >
          <GraphLegend
            legend={communityLegend}
            activeClusters={graph.activeClusters}
            onToggleCluster={graph.toggleCluster}
            onClearClusters={graph.clearClusterFilters}
          />
        </div>
      )}
    </div>
  );
}
