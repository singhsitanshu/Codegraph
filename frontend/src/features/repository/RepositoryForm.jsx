export default function RepositoryForm({ repository }) {
  const {
    activeRepo,
    isDeleting,
    isIngesting,
    repositoryError,
    repositoryInput,
    setRepositoryInput,
  } = repository;

  return (
    <form
      onSubmit={repository.submitRepository}
      className="rounded-2xl border border-[#d8e1da] bg-[#fdfefb] p-3 shadow-[0_5px_18px_rgba(32,51,45,0.04)]"
    >
      <label
        htmlFor="repository"
        className="text-[10px] font-extrabold uppercase tracking-[0.15em] text-[#71817b]"
      >
        GitHub repository
      </label>
      <div className="mt-2 flex gap-2">
        <input
          id="repository"
          type="text"
          value={repositoryInput}
          disabled={isIngesting || isDeleting}
          onChange={(event) => setRepositoryInput(event.target.value)}
          placeholder="https://github.com/psf/requests or psf/requests"
          className="min-w-0 flex-1 rounded-xl border border-[#d7e0da] bg-white px-3 py-2 text-xs text-[#263a33] outline-none transition focus:border-[#92aa9f] disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={
            !repositoryInput.trim() || isIngesting || isDeleting
          }
          className="rounded-xl bg-[#174f3d] px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.1em] text-white transition hover:bg-[#0f3e2f] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isIngesting ? "Indexing…" : "Ingest"}
        </button>
      </div>
      {isIngesting && (
        <div className="mt-3" aria-live="polite">
          <div className="flex items-center justify-between gap-3 text-[10px] font-bold text-[#52645d]">
            <span>{repository.progressText}</span>
            <span>{repository.progress}%</span>
          </div>
          <div
            className="mt-1.5 h-2 overflow-hidden rounded-full bg-[#e3e9e4]"
            role="progressbar"
            aria-label="Repository ingestion progress"
            aria-valuemin="0"
            aria-valuemax="100"
            aria-valuenow={repository.progress}
          >
            <div
              className="h-full rounded-full bg-[#2f7d61] transition-[width] duration-300 ease-out"
              style={{ width: `${repository.progress}%` }}
            />
          </div>
        </div>
      )}
      {(repositoryError || activeRepo) && (
        <div className="mt-2 flex items-center justify-between gap-3">
          <p
            className={`min-w-0 truncate text-[10px] ${
              repositoryError ? "text-[#b45348]" : "text-[#39705e]"
            }`}
          >
            {repositoryError || `Active repository: ${activeRepo}`}
          </p>
          {activeRepo && (
            <button
              type="button"
              onClick={repository.deleteActiveRepository}
              disabled={isDeleting}
              className="shrink-0 rounded-lg border border-[#e6c8c3] bg-[#fff8f6] px-2.5 py-1 text-[9px] font-extrabold uppercase tracking-[0.1em] text-[#a24f44] transition hover:bg-[#fbe9e5] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isDeleting ? "Deleting..." : "Delete"}
            </button>
          )}
        </div>
      )}
    </form>
  );
}
