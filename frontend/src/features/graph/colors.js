const UNASSIGNED_COMMUNITY_COLOR = "#64748b";

export function getCommunityColor(communityId) {
  if (communityId === null || communityId === undefined) {
    return UNASSIGNED_COMMUNITY_COLOR;
  }

  const numericId = Number(communityId);
  if (!Number.isFinite(numericId)) {
    return UNASSIGNED_COMMUNITY_COLOR;
  }

  const hue = ((numericId * 137.5) % 360 + 360) % 360;
  return `hsl(${Number(hue.toFixed(1))}, 70%, 55%)`;
}
