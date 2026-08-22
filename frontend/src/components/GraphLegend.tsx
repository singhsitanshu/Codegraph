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

  return (
    <aside
      aria-label="Architectural cluster legend"
      className="absolute bottom-[126px] left-4 z-20 w-72 overflow-hidden rounded-2xl border border-[#d7ded8] bg-white/95 shadow-[0_12px_34px_rgba(32,51,45,0.14)] backdrop-blur"
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
      <div className="max-h-56 overflow-y-auto px-3.5 py-2.5">
        {legend.communities.map((community) => {
          const isSelected = activeClusters.has(community.id);
          const isDeemphasized = isFilterActive && !isSelected;

          return (
            <button
              key={community.id}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onToggleCluster(community.id)}
              className={`flex w-full items-start justify-between gap-3 rounded-xl border px-2.5 py-2 text-left text-[10px] transition-[background-color,border-color,box-shadow,opacity] duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5b4fc4]/45 ${
                isSelected
                  ? "border-[#8f83e8] bg-[#f0edff] shadow-[0_4px_12px_rgba(91,79,196,0.12)]"
                  : "border-transparent hover:border-[#dce3de] hover:bg-[#f5f7f5]"
              }`}
              style={{ opacity: isDeemphasized ? 0.4 : 1 }}
              title={community.description || community.name}
            >
              <span className="flex min-w-0 items-start gap-2 font-bold text-[#43554f]">
                <span
                  className={`mt-1 size-2.5 shrink-0 rounded-full ${
                    isSelected ? "ring-2 ring-white ring-offset-1" : ""
                  }`}
                  style={{
                    backgroundColor: community.color,
                    boxShadow: isSelected
                      ? `0 0 0 1px ${community.color}`
                      : "none",
                  }}
                />
                <span className="min-w-0">
                  <span className="block leading-4">{community.name}</span>
                  {community.description && (
                    <span className="mt-0.5 block line-clamp-2 text-[9px] font-normal leading-3 text-[#7b8984]">
                      {community.description}
                    </span>
                  )}
                </span>
              </span>
              <span className="shrink-0 pt-0.5 text-[#8a9892]">
                {community.count} {community.count === 1 ? "node" : "nodes"}
              </span>
            </button>
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
