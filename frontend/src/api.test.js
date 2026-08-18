import assert from "node:assert/strict";
import test from "node:test";

import {
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

test("ingestion result scopes the subsequent chat request", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("/api/ingest-repo")) {
      return jsonResponse({
        status: "ingested",
        repo_name: "psf/requests",
        files_discovered: 10,
        files_parsed: 10,
      });
    }
    return jsonResponse({ response: "Scoped answer" });
  };

  const ingestion = await ingestRepository("psf/requests", fetchImpl);
  await requestChat("What calls get?", ingestion.repo_name, { fetchImpl });

  assert.equal(calls.length, 2);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    url: "https://github.com/psf/requests",
  });
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    message: "What calls get?",
    repo_name: "psf/requests",
  });
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
