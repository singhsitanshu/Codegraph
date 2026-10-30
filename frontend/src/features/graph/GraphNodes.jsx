import { memo } from "react";
import { Handle, Position } from "@xyflow/react";

const HANDLE_SIDES = [
  ["top", Position.Top],
  ["right", Position.Right],
  ["bottom", Position.Bottom],
  ["left", Position.Left],
];

function DirectionalHandles({ className }) {
  return HANDLE_SIDES.flatMap(([side, position]) => [
    <Handle
      key={`target-${side}`}
      id={`target-${side}`}
      type="target"
      position={position}
      className={className}
    />,
    <Handle
      key={`source-${side}`}
      id={`source-${side}`}
      type="source"
      position={position}
      className={className}
    />,
  ]);
}

const GraphNode = memo(function GraphNode({ data }) {
  const isExternal = Boolean(data.external);
  const isFocused = data.focusState === "focused";
  const isNeighbor = data.focusState === "neighbor";
  const communityColor = data.communityColor;
  const borderClass = isFocused
    ? "border-[#23a47d] ring-4 ring-[#23a47d]/20"
    : isNeighbor
      ? "border-[#74b9a1] ring-2 ring-[#74b9a1]/15"
      : isExternal
        ? "border-[#d5a24e]"
        : "border-[#8ab7a8]";
  const surfaceClass = isExternal
      ? "bg-[#fffaf0] text-[#423629] shadow-[0_8px_22px_rgba(91,67,28,0.09)]"
      : "bg-white text-[#20332d] shadow-[0_8px_22px_rgba(32,51,45,0.09)]";

  return (
    <div
      className={`relative flex h-full w-full cursor-pointer items-center gap-2.5 rounded-xl border px-3 py-2 transition-[border-color,box-shadow] duration-150 ${borderClass} ${surfaceClass}`}
      style={
        communityColor
          ? {
              background: `color-mix(in srgb, ${communityColor} 14%, white)`,
              borderColor: isFocused ? "#23a47d" : communityColor,
              boxShadow: `0 0 14px color-mix(in srgb, ${communityColor} 32%, transparent)`,
            }
          : undefined
      }
      title={data.fullLabel}
      aria-label={`${data.nodeType}: ${data.fullLabel}`}
    >
      <DirectionalHandles className="!size-2 !border-2 !border-white !bg-[#789084]" />
      <span
        className={`grid size-7 shrink-0 place-items-center rounded-lg text-[10px] font-extrabold uppercase ${
          isExternal
            ? "bg-[#f4dfb9] text-[#855f23]"
            : "bg-[#e3f3ed] text-[#276d54]"
        }`}
      >
        ƒ
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[11px] font-extrabold leading-4">{data.fullLabel}</p>
        <p
          className={`mt-0.5 truncate text-[9px] font-bold uppercase tracking-[0.13em] ${
            "text-[#809088]"
          }`}
        >
          {isExternal ? "External function" : data.nodeType}
        </p>
      </div>
    </div>
  );
});

const FileHubNode = memo(function FileHubNode({ data }) {
  const isFocused = data.focusState === "focused";
  const isNeighbor = data.focusState === "neighbor";
  const communityColor = data.communityColor;
  return (
    <div
      className={`flex h-full w-full items-center gap-3 overflow-hidden rounded-[20px] border bg-[#1e293b] px-4 text-white shadow-[0_16px_42px_rgba(15,23,42,0.22)] transition-[border-color,box-shadow] duration-150 ${
        isFocused
          ? "border-[#3dd6a4] ring-4 ring-[#23a47d]/20"
          : isNeighbor
            ? "border-[#74b9a1]"
            : "border-[#334155]"
      }`}
      style={
        communityColor
          ? {
              background: `color-mix(in srgb, ${communityColor} 24%, #1e293b)`,
              borderColor: isFocused ? "#3dd6a4" : communityColor,
              boxShadow: `0 0 16px color-mix(in srgb, ${communityColor} 34%, transparent)`,
            }
          : undefined
      }
      title={data.fullLabel}
      aria-label={`File hub: ${data.fullLabel}, ${data.degree} connections`}
    >
      <DirectionalHandles className="!size-2.5 !border-2 !border-[#1e293b] !bg-[#8ba39a]" />
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/10 text-xs font-extrabold text-[#b9f2da]">
        F
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-extrabold">{data.displayName}</p>
        <p className="mt-1 truncate text-[9px] font-bold uppercase tracking-[0.14em] text-slate-400">
          Module hub · {data.degree} links
        </p>
      </div>
    </div>
  );
});

// Keys match the node `type` assigned in graph/normalize.js.
export const nodeTypes = { fileHub: FileHubNode, graphNode: GraphNode };
