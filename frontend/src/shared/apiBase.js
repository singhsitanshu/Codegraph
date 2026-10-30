export const DEFAULT_API_BASE = "http://localhost:8000";

// The backend origin comes from VITE_API_BASE. The dashboard calls it directly,
// and the dev server proxies same-origin /api requests (the unload cleanup) to
// it, so both read this one value. The backend's CORS_ORIGINS must allow the
// dashboard's origin.
export function resolveApiBase(env) {
  const configured = env?.VITE_API_BASE?.trim();
  return (configured || DEFAULT_API_BASE).replace(/\/+$/, "");
}
