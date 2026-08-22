import assert from "node:assert/strict";
import test from "node:test";

import { getCommunityColor } from "./utils/colors.js";


test("unassigned communities use neutral slate", () => {
  assert.equal(getCommunityColor(null), "#64748b");
  assert.equal(getCommunityColor(undefined), "#64748b");
});

test("community colors are deterministic and distributed by golden angle", () => {
  assert.equal(getCommunityColor(1), "hsl(137.5, 70%, 55%)");
  assert.equal(getCommunityColor(1), getCommunityColor(1));
  assert.notEqual(getCommunityColor(1), getCommunityColor(2));
});
