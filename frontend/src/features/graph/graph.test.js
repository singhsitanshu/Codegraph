import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAdjacencyIndex,
  dimEdgesOutsideClusters,
  highlightFocusedNodes,
  miniMapNodeColor,
} from "./highlighting.js";
import { routeEdgesToNearestHandles } from "./layout.js";
import { normalizeGraph } from "./normalize.js";

const payload = {
  nodes: [
    { id: "file", labels: ["File"], name: "src/app/main.py", community_id: 3 },
    { id: 1, labels: ["Function"], qualified_name: "main.run" },
    { id: 2, name: "helper", external: true },
  ],
  edges: [
    { id: "e1", source: "file", target: "1" },
    { caller_id: 1, callee_id: 2 },
  ],
};

test("graph payloads normalize into laid-out React Flow nodes and edges", () => {
  const graph = normalizeGraph(payload);
  const [file, run, helper] = graph.nodes;

  assert.deepEqual(
    graph.nodes.map((node) => [node.id, node.type, node.data.nodeType]),
    [
      ["file", "fileHub", "File"],
      ["1", "graphNode", "Function"],
      ["2", "graphNode", "Function"],
    ],
  );
  assert.equal(file.data.displayName, "main.py");
  assert.equal(file.data.communityName, "Cluster #3");
  assert.equal(helper.data.external, true);
  assert.equal(run.data.degree, 2);
  assert.ok(file.style.width >= 190);
  assert.deepEqual(
    graph.edges.map((edge) => [edge.id, edge.source, edge.target]),
    [
      ["e1", "file", "1"],
      ["edge-1", "1", "2"],
    ],
  );
  assert.equal(normalizeGraph({}).nodes.length, 0);
});

test("edges attach to the handles facing each other", () => {
  const nodes = [
    { id: "a", position: { x: 0, y: 0 }, style: { width: 100, height: 50 } },
    { id: "b", position: { x: 400, y: 0 }, style: { width: 100, height: 50 } },
    { id: "c", position: { x: 0, y: 400 }, style: { width: 100, height: 50 } },
  ];
  const [right, down] = routeEdgesToNearestHandles(
    [
      { id: "ab", source: "a", target: "b" },
      { id: "ac", source: "a", target: "c" },
    ],
    nodes,
  );

  assert.deepEqual([right.sourceHandle, right.targetHandle], ["source-right", "target-left"]);
  assert.deepEqual([down.sourceHandle, down.targetHandle], ["source-bottom", "target-top"]);
});

test("focus highlighting keeps neighbours visible and dims the rest", () => {
  const edges = [{ id: "e1", source: "a", target: "b" }];
  const nodes = ["a", "b", "c"].map((id) => ({ id, data: {}, style: {} }));
  const index = buildAdjacencyIndex(edges);

  assert.equal(highlightFocusedNodes(nodes, null, null), nodes);
  assert.deepEqual(
    highlightFocusedNodes(nodes, "a", index.get("a")).map((node) => [
      node.data.focusState,
      node.style.opacity,
    ]),
    [
      ["focused", 1],
      ["neighbor", 1],
      ["dimmed", 0.1],
    ],
  );
});

test("cluster filters dim edges and minimap nodes outside the selection", () => {
  const nodes = [
    { id: "a", data: { community: 1 } },
    { id: "b", data: { community: 2 } },
  ];
  const [edge] = dimEdgesOutsideClusters(
    [{ id: "e", source: "b", target: "b", style: { opacity: 0.35 } }],
    nodes,
    new Set([1]),
  );

  assert.equal(edge.style.opacity, 0.05);
  assert.equal(miniMapNodeColor(nodes[1], true, new Set([1])), "#cbd5e1");
  assert.equal(miniMapNodeColor({ data: { nodeType: "File" } }, false, new Set()), "#1e293b");
});
