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

export async function ingestRepository(
  repositoryInput,
  { onProgress, signal, fetchImpl = fetch } = {},
) {
  const response = await fetchImpl(`${API_BASE}/api/ingest-repo`, {
    method: "POST",
    headers: {
      Accept: "application/x-ndjson",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ url: repositoryUrlFromInput(repositoryInput) }),
    signal,
  });
  if (!response.ok) {
    throw new Error(await responseError(response, "Repository ingestion failed"));
  }
  if (!response.body) {
    throw new Error("This browser cannot stream repository ingestion progress");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let finalPayload = null;

  const processLine = (line) => {
    if (!line.trim()) return;
    let payload;
    try {
      payload = JSON.parse(line);
    } catch {
      throw new Error("Repository ingestion returned malformed progress data");
    }
    if (typeof payload.progress === "number") {
      onProgress?.(payload);
    }
    if (payload.error) {
      throw new Error(payload.error);
    }
    if (payload.progress === 100) {
      finalPayload = payload;
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";
    lines.forEach(processLine);
    if (done) break;
  }
  processLine(buffer);

  if (
    typeof finalPayload?.repo_name !== "string" ||
    !finalPayload.repo_name.trim()
  ) {
    throw new Error("Repository ingestion returned no repository name");
  }
  return finalPayload;
}

export async function fetchRepositoryGraph(repoName, fetchImpl = fetch) {
  if (!repoName?.trim()) {
    return { nodes: [], edges: [] };
  }

  const query = new URLSearchParams({ repo_name: repoName });
  const response = await fetchImpl(`${API_BASE}/api/graph?${query}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(await responseError(response, "Graph request failed"));
  }
  return response.json();
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
