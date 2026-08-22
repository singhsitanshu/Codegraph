import assert from "node:assert/strict";
import test from "node:test";

import { buildCommunityLegend } from "./utils/communities.js";

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
