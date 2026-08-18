import assert from "node:assert/strict";
import test from "node:test";

import {
  fetchRepositoryGraph,
  ingestRepository,
  repositoryUrlFromInput,
  requestChat,
} from "./api.js";

function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => payload,
  };
}

test("repository input accepts owner/name shorthand", () => {
  assert.equal(
    repositoryUrlFromInput("psf/requests"),
    "https://github.com/psf/requests",
  );
});

test("ingestion result scopes graph and subsequent chat requests", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("/api/ingest-repo")) {
      return jsonResponse({
        status: "success",
        repo_name: "psf/requests",
      });
    }
    if (url.includes("/api/graph?")) {
      return jsonResponse({ nodes: [], edges: [] });
    }
    return jsonResponse({ response: "Scoped answer" });
  };

  const ingestion = await ingestRepository("psf/requests", fetchImpl);
  await fetchRepositoryGraph(ingestion.repo_name, fetchImpl);
  await requestChat("What calls get?", ingestion.repo_name, { fetchImpl });

  assert.equal(calls.length, 3);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    url: "https://github.com/psf/requests",
  });
  assert.equal(
    calls[1].url,
    "http://localhost:8000/api/graph?repo_name=psf%2Frequests",
  );
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    message: "What calls get?",
    repo_name: "psf/requests",
  });
});

test("an unscoped graph stays blank without making a request", async () => {
  let called = false;
  const graph = await fetchRepositoryGraph(null, async () => {
    called = true;
  });

  assert.deepEqual(graph, { nodes: [], edges: [] });
  assert.equal(called, false);
});

test("chat is blocked locally without an ingested repository", async () => {
  let called = false;
  await assert.rejects(
    requestChat("What calls get?", "", {
      fetchImpl: async () => {
        called = true;
      },
    }),
    /Ingest a repository/,
  );
  assert.equal(called, false);
});
