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

function ndjsonResponse(chunks, status = 200) {
  const encoder = new TextEncoder();
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/x-ndjson" },
    body: new ReadableStream({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
        controller.close();
      },
    }),
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
  const progressUpdates = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("/api/ingest-repo")) {
      return ndjsonResponse([
        '{"status":"Downloading repository...","progress":10}\n',
        '{"status":"Parsing files (1/',
        '1)...","progress":80}\n{"status":"Repository ingestion complete.",',
        '"progress":100,"repo_name":"psf/requests"}\n',
      ]);
    }
    if (url.includes("/api/graph?")) {
      return jsonResponse({ nodes: [], edges: [] });
    }
    return jsonResponse({ response: "Scoped answer" });
  };

  const ingestion = await ingestRepository("psf/requests", {
    fetchImpl,
    onProgress: (update) => progressUpdates.push(update.progress),
  });
  await fetchRepositoryGraph(ingestion.repo_name, fetchImpl);
  await requestChat("What calls get?", ingestion.repo_name, { fetchImpl });

  assert.equal(calls.length, 3);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    url: "https://github.com/psf/requests",
  });
  assert.deepEqual(progressUpdates, [10, 80, 100]);
  assert.equal(
    calls[1].url,
    "http://localhost:8000/api/graph?repo_name=psf%2Frequests",
  );
  assert.deepEqual(JSON.parse(calls[2].options.body), {
    message: "What calls get?",
    repo_name: "psf/requests",
  });
});

test("ingestion surfaces a streamed terminal error", async () => {
  const fetchImpl = async () =>
    ndjsonResponse([
      '{"status":"Downloading repository...","progress":10}\n',
      '{"status":"Repository ingestion failed.","progress":10,',
      '"error":"GitHub repository was not found"}\n',
    ]);

  await assert.rejects(
    ingestRepository("missing/repository", { fetchImpl }),
    /GitHub repository was not found/,
  );
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
