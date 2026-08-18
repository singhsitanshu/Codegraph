export const API_BASE = "http://localhost:8000";

function formatErrorDetail(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg ?? item?.message ?? String(item))
      .join("; ");
  }
  return detail?.message ?? null;
}

export async function responseError(response, fallback) {
  try {
    const payload = await response.json();
    return (
      formatErrorDetail(payload.detail) ??
      formatErrorDetail(payload.error) ??
      `${fallback} (${response.status})`
    );
  } catch {
    return `${fallback} (${response.status})`;
  }
}

export function repositoryUrlFromInput(repositoryInput) {
  const normalized = repositoryInput.trim();
  if (/^https?:\/\//i.test(normalized)) return normalized;
  return `https://github.com/${normalized.replace(/^\/+|\/+$/g, "")}`;
}

export async function ingestRepository(repositoryInput, fetchImpl = fetch) {
  const response = await fetchImpl(`${API_BASE}/api/ingest-repo`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ url: repositoryUrlFromInput(repositoryInput) }),
  });
  if (!response.ok) {
    throw new Error(await responseError(response, "Repository ingestion failed"));
  }

  const payload = await response.json();
  if (typeof payload.repo_name !== "string" || !payload.repo_name.trim()) {
    throw new Error("Repository ingestion returned no repository name");
  }
  return payload;
}

export async function requestChat(
  message,
  repoName,
  { signal, fetchImpl = fetch } = {},
) {
  if (!repoName?.trim()) {
    throw new Error("Ingest a repository before starting a chat");
  }

  const response = await fetchImpl(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: {
      Accept: "application/json, text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message, repo_name: repoName }),
    signal,
  });
  if (!response.ok) {
    throw new Error(await responseError(response, "Chat request failed"));
  }
  return response;
}
