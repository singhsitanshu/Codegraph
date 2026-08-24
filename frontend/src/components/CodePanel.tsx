import { useEffect, useMemo, useState } from "react";
import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import go from "react-syntax-highlighter/dist/esm/languages/prism/go";
import java from "react-syntax-highlighter/dist/esm/languages/prism/java";
import javascript from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import jsx from "react-syntax-highlighter/dist/esm/languages/prism/jsx";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import tsx from "react-syntax-highlighter/dist/esm/languages/prism/tsx";
import typescript from "react-syntax-highlighter/dist/esm/languages/prism/typescript";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

import { fetchNodeCode } from "../api.js";

SyntaxHighlighter.registerLanguage("python", python);
SyntaxHighlighter.registerLanguage("javascript", javascript);
SyntaxHighlighter.registerLanguage("jsx", jsx);
SyntaxHighlighter.registerLanguage("typescript", typescript);
SyntaxHighlighter.registerLanguage("tsx", tsx);
SyntaxHighlighter.registerLanguage("go", go);
SyntaxHighlighter.registerLanguage("java", java);

type CodePayload = {
  code: string;
  file_path: string;
  name: string;
};

interface CodePanelProps {
  nodeId: string | null;
  repoName: string | null;
  onClose: () => void;
}

const LANGUAGE_BY_EXTENSION: Record<string, string> = {
  py: "python",
  js: "javascript",
  jsx: "jsx",
  ts: "typescript",
  tsx: "tsx",
  go: "go",
  java: "java",
};

function languageForFile(filePath: string): string {
  const extension = filePath.split(".").pop()?.toLowerCase() ?? "";
  return LANGUAGE_BY_EXTENSION[extension] ?? "text";
}

export default function CodePanel({
  nodeId,
  repoName,
  onClose,
}: CodePanelProps) {
  const [source, setSource] = useState<CodePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!nodeId || !repoName) {
      setSource(null);
      setLoading(false);
      setError("");
      return undefined;
    }

    const controller = new AbortController();
    setSource(null);
    setLoading(true);
    setError("");
    fetchNodeCode(nodeId, repoName, { signal: controller.signal })
      .then((payload) => setSource(payload))
      .catch((requestError: unknown) => {
        if (
          requestError instanceof DOMException &&
          requestError.name === "AbortError"
        ) {
          return;
        }
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Could not load source code",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [nodeId, repoName]);

  useEffect(() => {
    if (!nodeId) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [nodeId, onClose]);

  const language = useMemo(
    () => languageForFile(source?.file_path ?? ""),
    [source?.file_path],
  );

  return (
    <aside
      aria-hidden={!nodeId}
      aria-label="Function source code"
      inert={!nodeId}
      role="dialog"
      className={`fixed right-0 top-0 z-[60] flex h-dvh w-full flex-col border-l border-slate-700 bg-[#0d1117] text-slate-100 shadow-[-18px_0_48px_rgba(15,23,42,0.28)] transition-transform duration-300 ease-out sm:w-[min(42rem,70vw)] xl:w-2/5 2xl:w-1/3 ${
        nodeId ? "translate-x-0" : "pointer-events-none translate-x-full"
      }`}
    >
      <header className="flex min-h-20 items-center justify-between gap-4 border-b border-slate-700/80 bg-slate-900/95 px-5 py-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-extrabold text-white">
            {source?.name || (loading ? "Loading function…" : "Function source")}
          </p>
          <p className="mt-1 truncate font-mono text-[11px] text-slate-400">
            {source?.file_path || repoName || ""}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="grid size-9 shrink-0 place-items-center rounded-xl border border-slate-700 bg-slate-800 text-slate-300 transition hover:border-slate-500 hover:bg-slate-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          aria-label="Close source code panel"
        >
          <svg
            aria-hidden="true"
            className="size-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path strokeLinecap="round" d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-auto">
        {loading ? (
          <div className="space-y-3 p-6" aria-live="polite">
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">
              Loading source code
            </p>
            {[72, 88, 61, 79, 45].map((width) => (
              <div
                key={width}
                className="h-3 animate-pulse rounded bg-slate-800"
                style={{ width: `${width}%` }}
              />
            ))}
          </div>
        ) : error ? (
          <div className="p-6" role="alert">
            <p className="text-sm font-bold text-rose-300">Source unavailable</p>
            <p className="mt-2 text-xs leading-5 text-slate-400">{error}</p>
          </div>
        ) : source?.code ? (
          <SyntaxHighlighter
            language={language}
            style={vscDarkPlus}
            showLineNumbers
            wrapLongLines={false}
            customStyle={{
              margin: 0,
              minHeight: "100%",
              padding: "1.25rem",
              background: "transparent",
              fontSize: "0.78rem",
              lineHeight: 1.65,
            }}
            lineNumberStyle={{
              minWidth: "2.75rem",
              color: "#52606d",
              paddingRight: "1rem",
            }}
          >
            {source.code}
          </SyntaxHighlighter>
        ) : (
          <div className="p-6">
            <p className="text-sm font-bold text-slate-300">
              No source code was stored for this function.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
