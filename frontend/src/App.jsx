import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";

const API_BASE = "http://localhost:8000";
const NODE_WIDTH = 210;
const NODE_HEIGHT = 64;
const FILE_HEADER_HEIGHT = 72;
const FILE_PADDING = 18;
const CHILD_COLUMN_GAP = 18;
const CHILD_ROW_GAP = 16;
const COLLAPSED_FILE_WIDTH = 300;
const COLLAPSED_FILE_HEIGHT = 72;
const MODULE_COLUMN_GAP = 80;
const MODULE_ROW_GAP = 120;
const LAYOUT_MARGIN = 50;
const INITIAL_ZOOM = 0.85;
const DEFAULT_EDGE_COLOR = "#789084";
const FOCUSED_EDGE_COLOR = "#178b6b";
const PRIMARY_FILES = new Set(["api.py", "sessions.py", "models.py", "adapters.py"]);

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

function getNodeKind(raw, data) {
  const labels = raw.labels ?? data.labels ?? [];
  if (labels.includes("File")) return "File";
  if (labels.includes("Function")) return "Function";
  return data.nodeType ?? raw.nodeType ?? "Function";
}

const GraphNode = memo(function GraphNode({ data }) {
  const isExternal = Boolean(data.external);
  const isFocused = data.focusState === "focused";
  const isNeighbor = data.focusState === "neighbor";
  const borderClass = isFocused
    ? "border-[#23a47d] ring-4 ring-[#23a47d]/20"
    : isNeighbor
      ? "border-[#74b9a1] ring-2 ring-[#74b9a1]/15"
      : isExternal
        ? "border-[#d5a24e]"
        : "border-[#8ab7a8]";
  const surfaceClass = isExternal
      ? "bg-[#fffaf0] text-[#423629] shadow-[0_8px_22px_rgba(91,67,28,0.09)]"
      : "bg-white text-[#20332d] shadow-[0_8px_22px_rgba(32,51,45,0.09)]";

  return (
    <div
      className={`relative flex h-16 w-[210px] items-center gap-3 rounded-2xl border px-4 py-3 transition-[border-color,box-shadow] duration-150 ${borderClass} ${surfaceClass}`}
      title={data.fullLabel}
      aria-label={`${data.nodeType}: ${data.fullLabel}`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!size-2 !border-2 !border-white !bg-[#789084]"
      />
      <span
        className={`grid size-8 shrink-0 place-items-center rounded-lg text-[10px] font-extrabold uppercase ${
          isExternal
            ? "bg-[#f4dfb9] text-[#855f23]"
            : "bg-[#e3f3ed] text-[#276d54]"
        }`}
      >
        ƒ
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-extrabold leading-5">{data.fullLabel}</p>
        <p
          className={`mt-0.5 truncate text-[9px] font-bold uppercase tracking-[0.13em] ${
            "text-[#809088]"
          }`}
        >
          {isExternal ? "External function" : data.nodeType}
        </p>
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!size-2 !border-2 !border-white !bg-[#789084]"
      />
    </div>
  );
});

const FileGroupNode = memo(function FileGroupNode({ data }) {
  const isFocused = data.focusState === "focused";
  const isNeighbor = data.focusState === "neighbor";
  return (
    <div
      className={`h-full w-full overflow-hidden rounded-[22px] border bg-[#1e293b] text-white shadow-[0_16px_42px_rgba(15,23,42,0.2)] transition-[border-color,box-shadow] duration-150 ${
        isFocused
          ? "border-[#3dd6a4] ring-4 ring-[#23a47d]/20"
          : isNeighbor
            ? "border-[#74b9a1]"
            : "border-[#334155]"
      }`}
      title={data.fullLabel}
      aria-label={`File: ${data.fullLabel}. Click to ${data.collapsed ? "expand" : "collapse"}.`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!size-2.5 !border-2 !border-[#1e293b] !bg-[#8ba39a]"
      />
      <div className="flex h-[72px] items-center gap-3 border-b border-white/10 px-5">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-white/10 text-xs font-extrabold text-[#b9f2da]">
          F
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-extrabold">{data.displayName}</p>
          <p className="mt-1 text-[9px] font-bold uppercase tracking-[0.14em] text-slate-400">
            {data.childCount} {data.childCount === 1 ? "function" : "functions"}
          </p>
        </div>
        <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-white/8 text-base text-slate-300">
          {data.collapsed ? "+" : "−"}
        </span>
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!size-2.5 !border-2 !border-[#1e293b] !bg-[#8ba39a]"
      />
    </div>
  );
});

const nodeTypes = { fileGroup: FileGroupNode, graphNode: GraphNode };

function basename(path) {
  return String(path).split(/[\\/]/).pop() || String(path);
}

function normalizeNodes(rawNodes) {
  return rawNodes.map((raw, index) => {
    const data = raw.data ?? {};
    const external = raw.external ?? data.external ?? false;
    const fullLabel = String(
      data.label ??
        raw.label ??
        raw.qualified_name ??
        raw.name ??
        `Function ${index + 1}`,
    );
    return {
      ...raw,
      id: String(raw.id ?? raw.elementId ?? index),
      type: getNodeKind(raw, data) === "File" ? "fileGroup" : "graphNode",
      position: { x: 0, y: 0 },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      data: {
        ...data,
        external,
        fullLabel,
        displayName: basename(fullLabel),
        label: fullLabel,
        nodeType: getNodeKind(raw, data),
      },
      style: {
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        ...raw.style,
      },
    };
  });
}

function normalizeEdges(rawEdges) {
  return rawEdges.map((edge, index) => ({
    ...edge,
    id: String(edge.id ?? `edge-${index}`),
    source: String(edge.source ?? edge.caller_id),
    target: String(edge.target ?? edge.callee_id),
    type: "smoothstep",
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: DEFAULT_EDGE_COLOR,
      width: 18,
      height: 18,
    },
    style: {
      ...edge.style,
      stroke: DEFAULT_EDGE_COLOR,
      strokeWidth: 1.35,
      opacity: 0.35,
    },
  }));
}

function buildCompoundNodes(nodes, edges) {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const fileNodes = nodes.filter((node) => node.data.nodeType === "File");
  const functionNodes = nodes.filter((node) => node.data.nodeType === "Function");
  const fileByPath = new Map();
  fileNodes.forEach((file) => {
    const path = file.data.path ?? file.data.fullLabel;
    fileByPath.set(String(path), file.id);
  });

  const parentFromDefines = new Map();
  edges.forEach((edge) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (source?.data.nodeType === "File" && target?.data.nodeType === "Function") {
      parentFromDefines.set(target.id, source.id);
    }
  });

  const orphanFunctions = functionNodes.filter((node) => {
    const filePath = node.data.file;
    return !parentFromDefines.has(node.id) && !fileByPath.has(String(filePath ?? ""));
  });
  let externalGroup = null;
  if (orphanFunctions.length > 0) {
    let externalId = "module:external-dependencies";
    while (nodeById.has(externalId)) externalId = `${externalId}:fallback`;
    externalGroup = {
      id: externalId,
      type: "fileGroup",
      position: { x: 0, y: 0 },
      data: {
        nodeType: "File",
        synthetic: true,
        fullLabel: "External dependencies",
        displayName: "External dependencies",
        label: "External dependencies",
        collapsed: true,
      },
      style: {},
    };
    fileNodes.push(externalGroup);
  }

  const parents = fileNodes.map((file) => {
    const primary = PRIMARY_FILES.has(basename(file.data.path ?? file.data.fullLabel));
    return {
      ...file,
      type: "fileGroup",
      data: {
        ...file.data,
        collapsed: file.data.synthetic ? true : !primary,
      },
    };
  });
  const children = functionNodes.map((node) => {
    const parentId =
      parentFromDefines.get(node.id) ??
      fileByPath.get(String(node.data.file ?? "")) ??
      externalGroup?.id;
    return {
      ...node,
      parentId,
      extent: "parent",
      expandParent: false,
      draggable: false,
    };
  });
  return [...parents, ...children];
}

function layoutFileModules(nodes) {
  const parents = nodes.filter((node) => node.data.nodeType === "File");
  const childrenByParent = new Map(parents.map((node) => [node.id, []]));
  nodes.forEach((node) => {
    if (node.parentId && childrenByParent.has(node.parentId)) {
      childrenByParent.get(node.parentId).push(node);
    }
  });
  childrenByParent.forEach((children) => {
    children.sort((left, right) =>
      left.data.fullLabel.localeCompare(right.data.fullLabel),
    );
  });

  const parentLayouts = parents
    .map((parent) => {
      const children = childrenByParent.get(parent.id) ?? [];
      const collapsed = Boolean(parent.data.collapsed);
      const columns = collapsed
        ? 1
        : Math.min(3, Math.max(1, Math.ceil(Math.sqrt(children.length))));
      const rows = Math.max(1, Math.ceil(children.length / columns));
      const width = collapsed
        ? COLLAPSED_FILE_WIDTH
        : FILE_PADDING * 2 + columns * NODE_WIDTH + (columns - 1) * CHILD_COLUMN_GAP;
      const height = collapsed
        ? COLLAPSED_FILE_HEIGHT
        : FILE_HEADER_HEIGHT + FILE_PADDING * 2 + rows * NODE_HEIGHT + (rows - 1) * CHILD_ROW_GAP;
      return { parent, children, collapsed, columns, width, height };
    })
    .sort((left, right) => {
      const leftPrimary = PRIMARY_FILES.has(left.parent.data.displayName);
      const rightPrimary = PRIMARY_FILES.has(right.parent.data.displayName);
      if (leftPrimary !== rightPrimary) return leftPrimary ? -1 : 1;
      return left.parent.data.fullLabel.localeCompare(right.parent.data.fullLabel);
    });

  const moduleColumns = Math.max(1, Math.ceil(Math.sqrt(parentLayouts.length)));
  const positioned = new Map();
  let y = LAYOUT_MARGIN;
  for (let rowStart = 0; rowStart < parentLayouts.length; rowStart += moduleColumns) {
    const row = parentLayouts.slice(rowStart, rowStart + moduleColumns);
    let x = LAYOUT_MARGIN;
    let rowHeight = 0;
    row.forEach(({ parent, children, collapsed, columns, width, height }) => {
      positioned.set(parent.id, {
        ...parent,
        position: { x, y },
        data: { ...parent.data, childCount: children.length },
        style: { width, height },
      });
      children.forEach((child, index) => {
        positioned.set(child.id, {
          ...child,
          hidden: collapsed,
          position: {
            x: FILE_PADDING + (index % columns) * (NODE_WIDTH + CHILD_COLUMN_GAP),
            y:
              FILE_HEADER_HEIGHT +
              FILE_PADDING +
              Math.floor(index / columns) * (NODE_HEIGHT + CHILD_ROW_GAP),
          },
          style: { ...child.style, width: NODE_WIDTH, height: NODE_HEIGHT },
        });
      });
      x += width + MODULE_COLUMN_GAP;
      rowHeight = Math.max(rowHeight, height);
    });
    y += rowHeight + MODULE_ROW_GAP;
  }
  return [
    ...parentLayouts.map(({ parent }) => positioned.get(parent.id)),
    ...nodes
      .filter((node) => node.parentId)
      .map((node) => positioned.get(node.id))
      .filter(Boolean),
  ];
}

function getInitialCenter(nodes, edges) {
  const parentByNode = new Map(
    nodes.map((node) => [node.id, node.parentId ?? node.id]),
  );
  const degree = new Map();
  edges.forEach((edge) => {
    const sourceParent = parentByNode.get(edge.source);
    const targetParent = parentByNode.get(edge.target);
    if (!sourceParent || !targetParent || sourceParent === targetParent) return;
    degree.set(sourceParent, (degree.get(sourceParent) ?? 0) + 1);
    degree.set(targetParent, (degree.get(targetParent) ?? 0) + 1);
  });
  const files = nodes.filter(
    (node) => node.data.nodeType === "File" && !node.data.synthetic,
  );
  const entryPoints = files.filter((node) =>
    new Set(["api.py", "sessions.py"]).has(node.data.displayName),
  );
  const candidates = entryPoints.length > 0 ? entryPoints : files;
  const target = candidates.sort(
    (left, right) => (degree.get(right.id) ?? 0) - (degree.get(left.id) ?? 0),
  )[0];
  if (!target) return { x: 0, y: 0 };
  return {
    x: target.position.x + Number(target.style.width) / 2,
    y: target.position.y + Number(target.style.height) / 2,
  };
}

function normalizeGraph(payload) {
  const normalizedNodes = normalizeNodes(payload.nodes ?? payload.functions ?? []);
  const edges = normalizeEdges(payload.edges ?? payload.calls ?? []);
  const nodes = layoutFileModules(buildCompoundNodes(normalizedNodes, edges));
  return {
    nodes,
    edges,
    initialCenter: getInitialCenter(nodes, edges),
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
  const [focusedNodeId, setFocusedNodeId] = useState(null);
  const [initialCenter, setInitialCenter] = useState(null);
  const [flowReady, setFlowReady] = useState(false);
  const [graphStatus, setGraphStatus] = useState("loading");
  const [graphError, setGraphError] = useState("");
  const [messages, setMessages] = useState(starterMessages);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [chatError, setChatError] = useState("");
  const abortRef = useRef(null);
  const messagesEndRef = useRef(null);
  const flowInstanceRef = useRef(null);

  const adjacencyIndex = useMemo(() => {
    const index = new Map();
    edges.forEach((edge) => {
      if (!index.has(edge.source)) {
        index.set(edge.source, { nodeIds: new Set(), edgeIds: new Set() });
      }
      if (!index.has(edge.target)) {
        index.set(edge.target, { nodeIds: new Set(), edgeIds: new Set() });
      }
      index.get(edge.source).nodeIds.add(edge.target);
      index.get(edge.source).edgeIds.add(edge.id);
      index.get(edge.target).nodeIds.add(edge.source);
      index.get(edge.target).edgeIds.add(edge.id);
    });
    return index;
  }, [edges]);

  const focusedConnections = focusedNodeId
    ? adjacencyIndex.get(focusedNodeId)
    : null;

  const hiddenNodeIds = useMemo(
    () => new Set(nodes.filter((node) => node.hidden).map((node) => node.id)),
    [nodes],
  );
  const graphCounts = useMemo(
    () => ({
      files: nodes.filter((node) => node.data.nodeType === "File").length,
      functions: nodes.filter((node) => node.data.nodeType === "Function").length,
    }),
    [nodes],
  );

  const visibleNodes = useMemo(() => {
    if (!focusedNodeId) return nodes;
    const neighborIds = focusedConnections?.nodeIds ?? new Set();

    return nodes.map((node) => {
      const isFocused = node.id === focusedNodeId;
      const isNeighbor = neighborIds.has(node.id);
      return {
        ...node,
        data: {
          ...node.data,
          focusState: isFocused
            ? "focused"
            : isNeighbor
              ? "neighbor"
              : "dimmed",
        },
        style: {
          ...node.style,
          opacity: isFocused || isNeighbor ? 1 : 0.1,
          transition: "opacity 150ms ease",
          zIndex: isFocused ? 20 : isNeighbor ? 10 : 0,
        },
      };
    });
  }, [focusedConnections, focusedNodeId, nodes]);

  const visibleEdges = useMemo(() => {
    const connectedEdgeIds = focusedConnections?.edgeIds ?? new Set();

    return edges.map((edge) => {
      const hidden = hiddenNodeIds.has(edge.source) || hiddenNodeIds.has(edge.target);
      const isConnected = Boolean(focusedNodeId) && connectedEdgeIds.has(edge.id);
      return {
        ...edge,
        hidden,
        animated: isConnected && !hidden,
        markerEnd: {
          ...edge.markerEnd,
          color: isConnected ? FOCUSED_EDGE_COLOR : DEFAULT_EDGE_COLOR,
        },
        style: {
          ...edge.style,
          stroke: isConnected ? FOCUSED_EDGE_COLOR : DEFAULT_EDGE_COLOR,
          strokeWidth: isConnected ? 2.8 : 1,
          opacity: focusedNodeId ? (isConnected ? 1 : 0.08) : 0.35,
          transition: "opacity 150ms ease, stroke 150ms ease",
        },
        zIndex: isConnected ? 15 : 0,
      };
    });
  }, [edges, focusedConnections, focusedNodeId, hiddenNodeIds]);

  const toggleFileNode = useCallback(
    (_, selectedNode) => {
      if (selectedNode.data.nodeType !== "File") return;
      setFocusedNodeId(null);
      setNodes((currentNodes) =>
        layoutFileModules(
          currentNodes.map((node) =>
            node.id === selectedNode.id
              ? {
                  ...node,
                  data: { ...node.data, collapsed: !node.data.collapsed },
                }
              : node,
          ),
        ),
      );
    },
    [setNodes],
  );

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
      setInitialCenter(graph.initialCenter);
      setFocusedNodeId(null);
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
    if (
      graphStatus !== "ready" ||
      !flowReady ||
      !initialCenter ||
      !flowInstanceRef.current
    ) {
      return undefined;
    }
    const frame = requestAnimationFrame(() => {
      flowInstanceRef.current?.setCenter(initialCenter.x, initialCenter.y, {
        zoom: INITIAL_ZOOM,
        duration: 350,
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [flowReady, graphStatus, initialCenter]);

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
                {graphCounts.files} files · {graphCounts.functions} functions · {edges.length} relationships
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
                nodes={visibleNodes}
                edges={visibleEdges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onInit={(instance) => {
                  flowInstanceRef.current = instance;
                  setFlowReady(true);
                }}
                onNodeClick={toggleFileNode}
                onNodeMouseEnter={(_, node) => {
                  if (node.data.nodeType === "Function") setFocusedNodeId(node.id);
                }}
                onNodeMouseLeave={() => setFocusedNodeId(null)}
                defaultViewport={{ x: 0, y: 0, zoom: INITIAL_ZOOM }}
                minZoom={0.15}
                maxZoom={1.8}
                onlyRenderVisibleElements
                proOptions={{ hideAttribution: true }}
              >
                <Background color="#cbd4cd" gap={24} size={1} variant={BackgroundVariant.Dots} />
                <Controls showInteractive={false} position="bottom-right" />
                <MiniMap
                  pannable
                  zoomable
                  position="bottom-left"
                  nodeColor={(node) => {
                    if (node.data?.nodeType === "File") return "#1e293b";
                    if (node.data?.external) return "#d5a24e";
                    return "#4f9c82";
                  }}
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
