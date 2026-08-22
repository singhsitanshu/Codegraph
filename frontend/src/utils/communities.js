import { getCommunityColor } from "./colors.js";

export function buildCommunityLegend(nodes) {
  const communities = new Map();
  let unassignedCount = 0;

  nodes.forEach((node) => {
    const communityId = node.data?.community;
    if (communityId === null || communityId === undefined) {
      unassignedCount += 1;
      return;
    }

    const existing = communities.get(communityId);
    const fallbackName = `Cluster #${communityId}`;
    const communityName = node.data?.communityName || fallbackName;
    const communityDescription = node.data?.communityDescription || "";
    communities.set(communityId, {
      id: communityId,
      count: (existing?.count ?? 0) + 1,
      color: getCommunityColor(communityId),
      name:
        existing?.name && existing.name !== fallbackName
          ? existing.name
          : communityName,
      description: existing?.description || communityDescription,
    });
  });

  return {
    communities: [...communities.values()].sort(
      (left, right) => Number(left.id) - Number(right.id),
    ),
    unassignedCount,
  };
}
