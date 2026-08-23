import { useState, type MouseEvent } from "react";

import { getCommunityColor } from "../utils/colors.js";

type CommunityLegendEntry = {
  id: number;
  count: number;
  color: string;
  name: string;
  description: string;
};

type CommunityLegendData = {
  communities: CommunityLegendEntry[];
  unassignedCount: number;
};

export default function GraphLegend({
  legend,
  activeClusters,
  onToggleCluster,
  onClearClusters,
}: {
  legend: CommunityLegendData;
  activeClusters: ReadonlySet<number>;
  onToggleCluster: (communityId: number) => void;
  onClearClusters: () => void;
}) {
  const isFilterActive = activeClusters.size > 0;
  const [expandedInfo, setExpandedInfo] = useState<Set<number>>(
    () => new Set(),
  );

  const toggleInfo = (
    event: MouseEvent<HTMLButtonElement>,
    communityId: number,
  ) => {
    event.stopPropagation();
    setExpandedInfo((current) => {
      const next = new Set(current);
      if (next.has(communityId)) {
        next.delete(communityId);
      } else {
        next.add(communityId);
      }
      return next;
    });
  };

  return (
    <aside
      aria-label="Architectural cluster legend"
      className="w-full overflow-hidden"
    >
      <div className="flex items-start justify-between gap-3 border-b border-[#e3e8e4] px-3.5 py-3">
        <div>
          <p className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-[#52645d]">
            Architectural modules
          </p>
          <p className="mt-1 text-[9px] text-[#87948f]">
            Click modules to isolate them
          </p>
        </div>
        {isFilterActive && (
          <button
            type="button"
            onClick={onClearClusters}
            className="shrink-0 rounded-md border border-[#d6ddd8] bg-white px-2 py-1 text-[8px] font-extrabold uppercase tracking-[0.08em] text-[#596b64] transition hover:border-[#aebcb3] hover:bg-[#f1f5f2] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5b4fc4]/40"
          >
            Clear filters
          </button>
        )}
      </div>
      <div className="max-h-[min(70vh,32rem)] overflow-y-auto px-3.5 py-2.5">
        {legend.communities.map((community) => {
          const isSelected = activeClusters.has(community.id);
          const isDeemphasized = isFilterActive && !isSelected;
          const isInfoExpanded = expandedInfo.has(community.id);
          const descriptionId = `community-description-${community.id}`;

          return (
            <div
              key={community.id}
              className={`mb-1 border-b border-[#e3e8e4]/70 pb-1 transition-opacity duration-200 last:mb-0 last:border-0 last:pb-0 ${
                isDeemphasized ? "opacity-40" : "opacity-100"
              }`}
            >
              <div
                className={`flex items-stretch rounded-xl border transition-[background-color,border-color,box-shadow] duration-200 ${
                  isSelected
                    ? "border-[#8f83e8] bg-[#f0edff] shadow-[0_4px_12px_rgba(91,79,196,0.12)]"
                    : "border-transparent hover:border-[#dce3de] hover:bg-[#f5f7f5]"
                }`}
              >
                <button
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => onToggleCluster(community.id)}
                  className="flex min-w-0 flex-1 items-center justify-between gap-3 rounded-l-xl px-2.5 py-2 text-left text-[10px] focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5b4fc4]/45"
                >
                  <span className="flex min-w-0 items-center gap-2 font-bold text-[#43554f]">
                    <span
                      className={`size-2.5 shrink-0 rounded-full ${
                        isSelected ? "ring-2 ring-white ring-offset-1" : ""
                      }`}
                      style={{
                        backgroundColor: community.color,
                        boxShadow: isSelected
                          ? `0 0 0 1px ${community.color}`
                          : "none",
                      }}
                    />
                    <span className="min-w-0 leading-4">{community.name}</span>
                  </span>
                  <span className="shrink-0 text-[#8a9892]">
                    {community.count} {community.count === 1 ? "node" : "nodes"}
                  </span>
                </button>
                {community.description && (
                  <button
                    type="button"
                    aria-label={`${isInfoExpanded ? "Hide" : "Show"} description for ${community.name}`}
                    aria-expanded={isInfoExpanded}
                    aria-controls={descriptionId}
                    onClick={(event) => toggleInfo(event, community.id)}
                    className="my-1.5 mr-1.5 grid size-7 shrink-0 place-items-center rounded-lg text-[#7b8984] transition-colors hover:bg-[#e4e8e5] hover:text-[#43554f] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5b4fc4]/45"
                    title="Toggle description"
                  >
                    <svg
                      aria-hidden="true"
                      className="size-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
                      />
                    </svg>
                  </button>
                )}
              </div>
              {isInfoExpanded && community.description && (
                <div
                  id={descriptionId}
                  className="px-3 pb-2 pt-1 text-[9px] italic leading-4 text-[#7b8984]"
                >
                  {community.description}
                </div>
              )}
            </div>
          );
        })}
        {legend.unassignedCount > 0 && (
          <div className="flex items-center justify-between gap-3 py-1.5 text-[10px]">
            <span className="flex min-w-0 items-center gap-2 font-bold text-[#60716b]">
              <span
                className="size-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: getCommunityColor(null) }}
              />
              <span>Unassigned</span>
            </span>
            <span className="shrink-0 text-[#8a9892]">
              {legend.unassignedCount}{" "}
              {legend.unassignedCount === 1 ? "node" : "nodes"}
            </span>
          </div>
        )}
      </div>
    </aside>
  );
}
