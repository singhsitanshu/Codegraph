// The repository the chat and graph are scoped to moves through one phase at
// a time, so a deletion cannot overlap an ingestion and progress or errors
// cannot outlive the phase they describe:
//   { phase: "idle" }
//   { phase: "ingesting", progress, progressText }
//   { phase: "failed", error }                  ingestion failed
//   { phase: "ready", repoName, error }         error: last failed deletion
//   { phase: "deleting", repoName }
export const NO_REPOSITORY = { phase: "idle" };

export function repositoryReducer(state, action) {
  switch (action.type) {
    case "ingestionStarted":
      return {
        phase: "ingesting",
        progress: 0,
        progressText: "Starting ingestion...",
      };
    case "ingestionProgressed":
      if (state.phase !== "ingesting") return state;
      return {
        ...state,
        progress: action.progress,
        progressText: action.progressText,
      };
    case "ingestionSucceeded":
      return { phase: "ready", repoName: action.repoName, error: "" };
    case "ingestionFailed":
      return { phase: "failed", error: action.error };
    case "deletionStarted":
      if (state.phase !== "ready") return state;
      return { phase: "deleting", repoName: state.repoName };
    case "deletionFailed":
      if (state.phase !== "deleting") return state;
      return { phase: "ready", repoName: state.repoName, error: action.error };
    case "deleted":
      return NO_REPOSITORY;
    default:
      throw new Error(`Unknown repository action: ${action.type}`);
  }
}

export function describeRepository(repository) {
  const isIngesting = repository.phase === "ingesting";
  const isDeleting = repository.phase === "deleting";
  const isRepositoryReady = repository.phase === "ready";
  return {
    isIngesting,
    isDeleting,
    isRepositoryReady,
    activeRepo: isRepositoryReady || isDeleting ? repository.repoName : null,
    repositoryError:
      repository.phase === "ready" || repository.phase === "failed"
        ? repository.error
        : "",
  };
}
