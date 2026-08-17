import { useCallback, useEffect, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";

const API_BASE = "http://localhost:8000";

const starterMessages = [
  {
    id: "welcome",
    role: "assistant",
    content:
      "Ask me about the call graph — for example, “What calls verify_signature?”",
  },
];

function Icon({ name, className = "size-4" }) {
  const paths = {
    arrow: <path d="m5 12 14-7-4 14-3-6-7-1Z" />,
    graph: (
      <>
        <circle cx="6" cy="6" r="2.5" />
        <circle cx="18" cy="7" r="2.5" />
        <circle cx="12" cy="18" r="2.5" />
        <path d="m8.4 6.2 7.1.6M7.4 8.1l3.3 7.5m5.7-6.5-3.1 6.6" />
      </>
    ),
    refresh: <path d="M20 6v5h-5M4 18v-5h5m9.2-3A7 7 0 0 0 6.1 6.5L4 11m16 2-2.1 4.5A7 7 0 0 1 5.8 14" />,
    stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
  };
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

function layoutNodes(rawNodes) {
  const columns = Math.max(1, Math.ceil(Math.sqrt(rawNodes.length)));
  return rawNodes.map((raw, index) => {
    const data = raw.data ?? {};
    const external = raw.external ?? data.external ?? false;
    return {
      ...raw,
      id: String(raw.id ?? raw.elementId ?? index),
      position: raw.position ?? {
        x: (index % columns) * 230,
        y: Math.floor(index / columns) * 130,
      },
      data: {
        ...data,
        label:
          data.label ??
          raw.label ??
          raw.qualified_name ??
          raw.name ??
          `Function ${index + 1}`,
      },
      style: {
        background: external ? "#fffaf0" : "#ffffff",
        border: `1px solid ${external ? "#e7b56d" : "#cbd8d1"}`,
        borderRadius: 14,
        boxShadow: "0 8px 24px rgba(34, 55, 48, 0.08)",
        color: "#20332d",
        fontFamily: "Manrope, sans-serif",
        fontSize: 12,
        fontWeight: 700,
        padding: "10px 14px",
        width: 180,
        ...raw.style,
      },
    };
  });
}

function normalizeGraph(payload) {
  const rawNodes = payload.nodes ?? payload.functions ?? [];
  const rawEdges = payload.edges ?? payload.calls ?? [];
  return {
    nodes: layoutNodes(rawNodes),
    edges: rawEdges.map((edge, index) => ({
      ...edge,
      id: String(edge.id ?? `edge-${index}`),
      source: String(edge.source ?? edge.caller_id),
      target: String(edge.target ?? edge.callee_id),
      type: edge.type ?? "smoothstep",
      markerEnd: edge.markerEnd ?? {
        type: MarkerType.ArrowClosed,
        color: "#7d958a",
        width: 16,
        height: 16,
      },
      style: { stroke: "#7d958a", strokeWidth: 1.4, ...edge.style },
    })),
  };
}

function extractSseText(data) {
  if (!data || data === "[DONE]") return "";
  try {
    const parsed = JSON.parse(data);
    const content =
      parsed.token ??
      parsed.text ??
      parsed.content ??
      parsed.delta?.text ??
      parsed.delta?.content ??
      parsed.message?.content ??
      "";
    if (Array.isArray(content)) {
      return content.map((block) => block.text ?? "").join("");
    }
    return typeof content === "string" ? content : "";
  } catch {
    return data;
  }
}

async function responseError(response, fallback) {
  try {
    const payload = await response.json();
    return payload.detail ?? payload.error ?? `${fallback} (${response.status})`;
  } catch {
    return `${fallback} (${response.status})`;
  }
}

function extractSseError(data) {
  try {
    const payload = JSON.parse(data);
    return payload.error ?? data;
  } catch {
    return data;
  }
}

function ChatMessage({ message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="mt-1 grid size-7 shrink-0 place-items-center rounded-full bg-[#174f3d] text-[#e4ff9b]">
          <Icon name="graph" className="size-3.5" />
        </div>
      )}
      <div
        className={`max-w-[82%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-[13px] leading-6 ${
          isUser
            ? "rounded-br-md bg-[#20332d] text-white"
            : "rounded-bl-md border border-[#dce4de] bg-white text-[#3d4c47] shadow-[0_5px_18px_rgba(32,51,45,0.05)]"
        }`}
      >
        {message.content || (
          <span className="inline-flex gap-1 py-2" aria-label="Generating response">
            <i className="typing-dot" />
            <i className="typing-dot [animation-delay:150ms]" />
            <i className="typing-dot [animation-delay:300ms]" />
          </span>
        )}
      </div>
    </div>
  );
}

function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [graphStatus, setGraphStatus] = useState("loading");
  const [graphError, setGraphError] = useState("");
  const [messages, setMessages] = useState(starterMessages);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [chatError, setChatError] = useState("");
  const abortRef = useRef(null);
  const messagesEndRef = useRef(null);

  const loadGraph = useCallback(async () => {
    setGraphStatus("loading");
    setGraphError("");
    try {
      const response = await fetch(`${API_BASE}/api/graph`);
      if (!response.ok) {
        throw new Error(await responseError(response, "Graph request failed"));
      }
      const graph = normalizeGraph(await response.json());
      setNodes(graph.nodes);
      setEdges(graph.edges);
      setGraphStatus("ready");
    } catch (error) {
      setGraphError(error instanceof Error ? error.message : "Could not load graph");
      setGraphStatus("error");
    }
  }, [setEdges, setNodes]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const stopStreaming = () => abortRef.current?.abort();

  const sendMessage = async (event) => {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt || streaming) return;

    const userMessage = { id: crypto.randomUUID(), role: "user", content: prompt };
    const assistantId = crypto.randomUUID();
    setMessages((current) => [
      ...current,
      userMessage,
      { id: assistantId, role: "assistant", content: "" },
    ]);
    setInput("");
    setChatError("");
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;
    let accumulated = "";

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: {
          Accept: "application/json, text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message: prompt }),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(await responseError(response, "Chat request failed"));
      }
      const contentType = response.headers.get("content-type") ?? "";
      if (contentType.includes("application/json")) {
        const payload = await response.json();
        accumulated = payload.response ?? "";
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId
              ? { ...message, content: accumulated }
              : message,
          ),
        );
      } else {
        if (!response.body) throw new Error("This browser cannot stream the response");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
          const events = buffer.split(/\r?\n\r?\n/);
          buffer = events.pop() ?? "";

          for (const block of events) {
            const lines = block.split(/\r?\n/);
            const eventType = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
            const data = lines
              .filter((line) => line.startsWith("data:"))
              .map((line) => line.slice(5).trimStart())
              .join("\n");
            if (eventType === "error") {
              throw new Error(extractSseError(data) || "Streaming failed");
            }
            accumulated += extractSseText(data);
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? { ...message, content: accumulated }
                  : message,
              ),
            );
          }
          if (done) break;
        }
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        if (!accumulated) accumulated = "Response stopped.";
      } else {
        const message = error instanceof Error ? error.message : "Chat request failed";
        setChatError(message);
        if (!accumulated) accumulated = "I couldn’t reach the agent. Please try again.";
      }
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId ? { ...message, content: accumulated } : message,
        ),
      );
    } finally {
      abortRef.current = null;
      setStreaming(false);
    }
  };

  return (
    <main className="h-dvh overflow-hidden bg-[#f5f6f1] text-[#20332d]">
      <div className="grid h-full grid-cols-1 lg:grid-cols-2">
        <section className="flex min-h-0 flex-col border-b border-[#d9e0da] bg-[#f8f9f5] lg:border-r lg:border-b-0">
          <header className="flex h-[76px] shrink-0 items-center justify-between border-b border-[#dfe5df] px-6 md:px-8">
            <div className="flex items-center gap-3">
              <div className="grid size-9 place-items-center rounded-xl bg-[#174f3d] text-[#e4ff9b] shadow-[0_7px_18px_rgba(23,79,61,0.2)]">
                <Icon name="graph" className="size-[18px]" />
              </div>
              <div>
                <h1 className="text-[15px] font-extrabold tracking-[-0.02em]">Codegraph</h1>
                <p className="mt-0.5 text-[10px] font-bold uppercase tracking-[0.16em] text-[#8b9a94]">
                  Repository intelligence
                </p>
              </div>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full border border-[#d8e2db] bg-white px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-[#5d7069]">
              <i className="size-1.5 rounded-full bg-[#65a56c] shadow-[0_0_0_3px_rgba(101,165,108,0.12)]" />
              Agent ready
            </span>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-7 md:px-8">
            <div className="mx-auto flex max-w-2xl flex-col gap-5">
              <div className="mb-1">
                <p className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-[#98a59f]">
                  Call graph assistant
                </p>
                <h2 className="mt-2 text-[25px] font-semibold tracking-[-0.04em] text-[#263a33]">
                  Explore how your code connects.
                </h2>
              </div>
              {messages.map((message) => (
                <ChatMessage key={message.id} message={message} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>

          <div className="shrink-0 px-5 pb-5 md:px-8 md:pb-7">
            <form
              onSubmit={sendMessage}
              className="mx-auto max-w-2xl rounded-[20px] border border-[#d7e0da] bg-white p-2 shadow-[0_14px_40px_rgba(32,51,45,0.09)] focus-within:border-[#92aa9f]"
            >
              <textarea
                aria-label="Message"
                className="max-h-32 min-h-12 w-full resize-none bg-transparent px-3 py-2 text-[13px] leading-5 text-[#263a33] outline-none placeholder:text-[#9ba7a2]"
                placeholder="Ask about a function or dependency…"
                rows="2"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <div className="flex items-center justify-between px-2 pb-1">
                <span className={`text-[10px] ${chatError ? "text-[#b45348]" : "text-[#9aa6a1]"}`}>
                  {chatError || "Enter to send · Shift + Enter for a new line"}
                </span>
                {streaming ? (
                  <button
                    type="button"
                    onClick={stopStreaming}
                    className="grid size-8 place-items-center rounded-xl bg-[#edf1ee] text-[#43554f] transition hover:bg-[#e1e8e3]"
                    aria-label="Stop response"
                  >
                    <Icon name="stop" className="size-4" />
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!input.trim()}
                    className="grid size-8 place-items-center rounded-xl bg-[#174f3d] text-white transition hover:bg-[#0f3e2f] disabled:cursor-not-allowed disabled:opacity-35"
                    aria-label="Send message"
                  >
                    <Icon name="arrow" className="size-4" />
                  </button>
                )}
              </div>
            </form>
          </div>
        </section>

        <section className="relative hidden min-h-0 overflow-hidden bg-[#eef1eb] lg:block">
          <div className="absolute inset-x-0 top-0 z-10 flex h-[76px] items-center justify-between border-b border-[#d9e0da]/90 bg-[#f3f5f0]/90 px-7 backdrop-blur">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-extrabold tracking-[-0.01em]">Function map</h2>
                <span className="rounded-md bg-[#e0e7e1] px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.12em] text-[#677a72]">
                  Live
                </span>
              </div>
              <p className="mt-1 text-[10px] font-medium text-[#83918b]">
                {nodes.length} functions · {edges.length} call relationships
              </p>
            </div>
            <button
              type="button"
              onClick={loadGraph}
              disabled={graphStatus === "loading"}
              className="inline-flex items-center gap-2 rounded-xl border border-[#d7ded8] bg-white px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.11em] text-[#52645d] shadow-sm transition hover:border-[#bfcac2] disabled:opacity-50"
            >
              <Icon name="refresh" className={`size-3.5 ${graphStatus === "loading" ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>

          <div className="absolute inset-0 pt-[76px]">
            {graphStatus === "error" ? (
              <div className="grid h-full place-items-center p-8 text-center">
                <div>
                  <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-white text-[#9b5a4e] shadow-sm">
                    <Icon name="graph" className="size-5" />
                  </div>
                  <p className="mt-4 text-sm font-bold">Graph unavailable</p>
                  <p className="mt-1 text-xs text-[#7d8b85]">{graphError}</p>
                  <button onClick={loadGraph} className="mt-4 text-xs font-bold text-[#276d54] underline underline-offset-4">
                    Try again
                  </button>
                </div>
              </div>
            ) : (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                fitView
                fitViewOptions={{ padding: 0.25 }}
                minZoom={0.25}
                maxZoom={1.8}
                proOptions={{ hideAttribution: true }}
              >
                <Background color="#cbd4cd" gap={24} size={1} variant={BackgroundVariant.Dots} />
                <Controls showInteractive={false} position="bottom-right" />
                <MiniMap
                  pannable
                  zoomable
                  position="bottom-left"
                  nodeColor={(node) => node.data?.external ? "#e7b56d" : "#3b765f"}
                  maskColor="rgba(238, 241, 235, 0.75)"
                />
              </ReactFlow>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

export default App;
