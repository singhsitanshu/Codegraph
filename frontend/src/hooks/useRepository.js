import { useEffect, useReducer, useState } from "react";

import {
  cleanupRepositoryOnUnload,
  deleteRepository,
  ingestRepository,
} from "../api.js";
import {
  NO_REPOSITORY,
  describeRepository,
  repositoryReducer,
} from "../utils/repositoryState.js";

// Owns the repository the app is scoped to: ingesting it, deleting it and the
// best-effort cleanup when the page unloads. Callers react to its lifecycle
// through onIngestionStarted, onIngested(repoName) and onDeleted.
export default function useRepository({
  abortRef,
  onIngestionStarted,
  onIngested,
  onDeleted,
}) {
  const [repositoryInput, setRepositoryInput] = useState("");
  const [repository, dispatchRepository] = useReducer(
    repositoryReducer,
    NO_REPOSITORY,
  );
  const view = describeRepository(repository);
  const { activeRepo, isDeleting, isIngesting } = view;

  useEffect(() => {
    const handleUnload = () => {
      try {
        cleanupRepositoryOnUnload(activeRepo)?.catch(() => {});
      } catch {
        // Navigation must not be blocked if the best-effort cleanup cannot start.
      }
    };

    window.addEventListener("beforeunload", handleUnload);
    return () => window.removeEventListener("beforeunload", handleUnload);
  }, [activeRepo]);

  const deleteActiveRepository = async () => {
    if (repository.phase !== "ready") return;
    const { repoName } = repository;
    const confirmed = window.confirm(
      `Delete ${repoName} and all of its graph data? This cannot be undone.`,
    );
    if (!confirmed) return;

    abortRef.current?.abort();
    dispatchRepository({ type: "deletionStarted" });
    try {
      await deleteRepository(repoName);
      dispatchRepository({ type: "deleted" });
      setRepositoryInput("");
      onDeleted();
    } catch (error) {
      dispatchRepository({
        type: "deletionFailed",
        error: error instanceof Error ? error.message : "Repository deletion failed",
      });
    }
  };

  const submitRepository = async (event) => {
    event.preventDefault();
    const requestedRepository = repositoryInput.trim();
    if (!requestedRepository || isIngesting || isDeleting) return;

    abortRef.current?.abort();
    dispatchRepository({ type: "ingestionStarted" });
    onIngestionStarted();

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await ingestRepository(requestedRepository, {
        signal: controller.signal,
        onProgress: (update) =>
          dispatchRepository({
            type: "ingestionProgressed",
            progress: update.progress,
            progressText: update.status,
          }),
      });
      dispatchRepository({
        type: "ingestionSucceeded",
        repoName: result.repo_name,
      });
      await onIngested(result.repo_name);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      dispatchRepository({
        type: "ingestionFailed",
        error: error instanceof Error ? error.message : "Repository ingestion failed",
      });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  };

  return {
    ...view,
    progress: repository.progress,
    progressText: repository.progressText,
    repositoryInput,
    setRepositoryInput,
    submitRepository,
    deleteActiveRepository,
  };
}
