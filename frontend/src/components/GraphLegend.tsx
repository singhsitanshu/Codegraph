import { getCommunityColor } from "../utils/colors.js";

type CommunityLegendEntry = {
  id: number | string;
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
}: {
  legend: CommunityLegendData;
}) {
  return (
    <aside
      aria-label="Architectural cluster legend"
      className="absolute bottom-[126px] left-4 z-20 w-72 overflow-hidden rounded-2xl border border-[#d7ded8] bg-white/95 shadow-[0_12px_34px_rgba(32,51,45,0.14)] backdrop-blur"
    >
      <div className="border-b border-[#e3e8e4] px-3.5 py-3">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-[#52645d]">
          Architectural modules
        </p>
        <p className="mt-1 text-[9px] text-[#87948f]">
          LLM-labeled Leiden communities
        </p>
      </div>
      <div className="max-h-56 overflow-y-auto px-3.5 py-2.5">
        {legend.communities.map((community) => (
          <div
            key={community.id}
            className="flex items-start justify-between gap-3 py-2 text-[10px]"
            title={community.description || community.name}
          >
            <span className="flex min-w-0 items-start gap-2 font-bold text-[#43554f]">
              <span
                className="mt-1 size-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: community.color }}
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
          </div>
        ))}
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
