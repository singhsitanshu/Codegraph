import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCommunityLegend,
  toggleClusterSelection,
} from "./utils/communities.js";

test("cluster selection toggles multiple communities without mutating state", () => {
  const initial = new Set([1]);
  const withSecondCluster = toggleClusterSelection(initial, 2);
  const withoutFirstCluster = toggleClusterSelection(withSecondCluster, 1);

  assert.deepEqual([...initial], [1]);
  assert.deepEqual([...withSecondCluster], [1, 2]);
  assert.deepEqual([...withoutFirstCluster], [2]);
});

test("community legend uses stored labels, descriptions, and counts", () => {
  const legend = buildCommunityLegend([
    {
      data: {
        community: 2,
        communityName: "HTTP Session Management",
        communityDescription: "Coordinates HTTP sessions and requests.",
      },
    },
    {
      data: {
        community: 2,
        communityName: "HTTP Session Management",
        communityDescription: "Coordinates HTTP sessions and requests.",
      },
    },
    { data: { community: 4 } },
    { data: { community: null } },
  ]);

  assert.equal(legend.communities[0].name, "HTTP Session Management");
  assert.equal(
    legend.communities[0].description,
    "Coordinates HTTP sessions and requests.",
  );
  assert.equal(legend.communities[0].count, 2);
  assert.equal(legend.communities[1].name, "Cluster #4");
  assert.equal(legend.unassignedCount, 1);
});

test("community legend lists the largest modules first", () => {
  const nodes = [
    ...Array.from({ length: 1 }, () => ({ data: { community: 1 } })),
    ...Array.from({ length: 3 }, () => ({ data: { community: 7 } })),
    ...Array.from({ length: 2 }, () => ({ data: { community: 3 } })),
    ...Array.from({ length: 2 }, () => ({ data: { community: 2 } })),
  ];

  const legend = buildCommunityLegend(nodes);

  assert.deepEqual(
    legend.communities.map((community) => [community.id, community.count]),
    [
      [7, 3],
      [2, 2],
      [3, 2],
      [1, 1],
    ],
  );
});
