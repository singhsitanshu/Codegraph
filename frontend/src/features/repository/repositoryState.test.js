import assert from "node:assert/strict";
import test from "node:test";

import {
  NO_REPOSITORY,
  describeRepository,
  repositoryReducer,
} from "./repositoryState.js";

function reduce(...actions) {
  return actions.reduce(repositoryReducer, NO_REPOSITORY);
}

test("ingestion moves through progress to a ready repository", () => {
  const ingesting = reduce(
    { type: "ingestionStarted" },
    { type: "ingestionProgressed", progress: 40, progressText: "Parsing" },
  );
  assert.deepEqual(ingesting, {
    phase: "ingesting",
    progress: 40,
    progressText: "Parsing",
  });
  assert.equal(describeRepository(ingesting).isIngesting, true);

  const ready = repositoryReducer(ingesting, {
    type: "ingestionSucceeded",
    repoName: "psf/requests",
  });
  assert.deepEqual(describeRepository(ready), {
    isIngesting: false,
    isDeleting: false,
    isRepositoryReady: true,
    activeRepo: "psf/requests",
    repositoryError: "",
  });
});

test("a failed deletion returns to the ready repository with its error", () => {
  const ready = reduce({ type: "ingestionSucceeded", repoName: "a/b" });
  const deleting = repositoryReducer(ready, { type: "deletionStarted" });
  assert.equal(describeRepository(deleting).activeRepo, "a/b");
  assert.equal(describeRepository(deleting).isRepositoryReady, false);

  const failed = repositoryReducer(deleting, {
    type: "deletionFailed",
    error: "Neo4j is down",
  });
  assert.equal(describeRepository(failed).repositoryError, "Neo4j is down");
  assert.equal(repositoryReducer(failed, { type: "deleted" }), NO_REPOSITORY);
});

test("progress outside an ingestion is ignored", () => {
  const ready = reduce({ type: "ingestionSucceeded", repoName: "a/b" });
  assert.equal(
    repositoryReducer(ready, { type: "ingestionProgressed", progress: 5 }),
    ready,
  );
});
