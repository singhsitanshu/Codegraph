import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
} from "d3-force";
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

import {
  fetchRepositoryGraph,
  ingestRepository,
  requestChat,
} from "./api.js";

const FUNCTION_NODE_WIDTH = 150;
const FUNCTION_NODE_HEIGHT = 52;
const FILE_NODE_MIN_WIDTH = 190;
const FILE_NODE_MIN_HEIGHT = 72;
const INITIAL_ZOOM = 1;
const MANY_BODY_STRENGTH = -45;
const LINK_DISTANCE = 100;
const DEFAULT_EDGE_COLOR = "#789084";
const FOCUSED_EDGE_COLOR = "#178b6b";

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

const HANDLE_SIDES = [
  ["top", Position.Top],
  ["right", Position.Right],
  ["bottom", Position.Bottom],
  ["left", Position.Left],
];

function DirectionalHandles({ className }) {
  return HANDLE_SIDES.flatMap(([side, position]) => [
    <Handle
      key={`target-${side}`}
      id={`target-${side}`}
      type="target"
      position={position}
      className={className}
    />,
    <Handle
      key={`source-${side}`}
      id={`source-${side}`}
      type="source"
      position={position}
      className={className}
    />,
  ]);
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
      className={`relative flex h-full w-full items-center gap-2.5 rounded-xl border px-3 py-2 transition-[border-color,box-shadow] duration-150 ${borderClass} ${surfaceClass}`}
      title={data.fullLabel}
      aria-label={`${data.nodeType}: ${data.fullLabel}`}
    >
      <DirectionalHandles className="!size-2 !border-2 !border-white !bg-[#789084]" />
      <span
        className={`grid size-7 shrink-0 place-items-center rounded-lg text-[10px] font-extrabold uppercase ${
          isExternal
            ? "bg-[#f4dfb9] text-[#855f23]"
            : "bg-[#e3f3ed] text-[#276d54]"
        }`}
      >
        ƒ
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[11px] font-extrabold leading-4">{data.fullLabel}</p>
        <p
          className={`mt-0.5 truncate text-[9px] font-bold uppercase tracking-[0.13em] ${
            "text-[#809088]"
          }`}
        >
          {isExternal ? "External function" : data.nodeType}
        </p>
      </div>
    </div>
  );
});

const FileHubNode = memo(function FileHubNode({ data }) {
  const isFocused = data.focusState === "focused";
  const isNeighbor = data.focusState === "neighbor";
  return (
    <div
      className={`flex h-full w-full items-center gap-3 overflow-hidden rounded-[20px] border bg-[#1e293b] px-4 text-white shadow-[0_16px_42px_rgba(15,23,42,0.22)] transition-[border-color,box-shadow] duration-150 ${
        isFocused
          ? "border-[#3dd6a4] ring-4 ring-[#23a47d]/20"
          : isNeighbor
            ? "border-[#74b9a1]"
            : "border-[#334155]"
      }`}
      title={data.fullLabel}
      aria-label={`File hub: ${data.fullLabel}, ${data.degree} connections`}
    >
      <DirectionalHandles className="!size-2.5 !border-2 !border-[#1e293b] !bg-[#8ba39a]" />
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/10 text-xs font-extrabold text-[#b9f2da]">
        F
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-extrabold">{data.displayName}</p>
        <p className="mt-1 truncate text-[9px] font-bold uppercase tracking-[0.14em] text-slate-400">
          Module hub · {data.degree} links
        </p>
      </div>
    </div>
  );
});

const nodeTypes = { fileHub: FileHubNode, graphNode: GraphNode };

function basename(path) {
  return String(path).split(/[\\/]/).pop() || String(path);
}

function normalizeNodes(rawNodes) {
  return rawNodes.map((raw, index) => {
    const data = raw.data ?? {};
    const external = raw.external ?? data.external ?? false;
    const nodeType = getNodeKind(raw, data);
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
      type: nodeType === "File" ? "fileHub" : "graphNode",
      position: { x: 0, y: 0 },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      data: {
        ...data,
        external,
        fullLabel,
        displayName: basename(fullLabel),
        label: fullLabel,
        nodeType,
      },
      style: { ...raw.style },
    };
  });
}

function normalizeEdges(rawEdges) {
  return rawEdges.map((edge, index) => ({
    ...edge,
    id: String(edge.id ?? `edge-${index}`),
    source: String(edge.source ?? edge.caller_id),
    target: String(edge.target ?? edge.callee_id),
    type: "straight",
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
    interactionWidth: 16,
  }));
}

function getDegrees(nodes, edges) {
  const degree = new Map();
  nodes.forEach((node) => degree.set(node.id, 0));
  edges.forEach((edge) => {
    if (degree.has(edge.source)) {
      degree.set(edge.source, degree.get(edge.source) + 1);
    }
    if (degree.has(edge.target)) {
      degree.set(edge.target, degree.get(edge.target) + 1);
    }
  });
  return degree;
}

function getNodeDimensions(node, maxDegree) {
  const degreeRatio = Math.sqrt((node.data.degree ?? 0) / Math.max(1, maxDegree));
  if (node.data.nodeType === "File") {
    return {
      width: FILE_NODE_MIN_WIDTH + degreeRatio * 80,
      height: FILE_NODE_MIN_HEIGHT + degreeRatio * 20,
    };
  }
  return {
    width: FUNCTION_NODE_WIDTH + degreeRatio * 30,
    height: FUNCTION_NODE_HEIGHT + degreeRatio * 10,
  };
}

function applyForceLayout(nodes, edges) {
  if (nodes.length === 0) return [];
  const degrees = getDegrees(nodes, edges);
  const maxDegree = Math.max(1, ...degrees.values());
  const dimensions = new Map();
  const simulationNodes = nodes.map((node, index) => {
    const angle = (index / nodes.length) * Math.PI * 2;
    const radius = 180 + (index % 9) * 18;
    const dimension = getNodeDimensions(
      { ...node, data: { ...node.data, degree: degrees.get(node.id) ?? 0 } },
      maxDegree,
    );
    dimensions.set(node.id, dimension);
    return {
      id: node.id,
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
      radius: Math.max(dimension.width, dimension.height) / 2,
    };
  });
  const nodeIds = new Set(simulationNodes.map((node) => node.id));
  const simulationLinks = edges
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .map((edge) => ({ source: edge.source, target: edge.target }));

  const simulation = forceSimulation(simulationNodes)
    .force(
      "link",
      forceLink(simulationLinks)
        .id((node) => node.id)
        .distance(LINK_DISTANCE)
        .strength(0.55),
    )
    .force("charge", forceManyBody().strength(MANY_BODY_STRENGTH))
    .force("center", forceCenter(0, 0).strength(0.9))
    .force(
      "collision",
      forceCollide()
        .radius((node) => node.radius + 12)
        .strength(0.9)
        .iterations(2),
    )
    .velocityDecay(0.42)
    .stop();

  for (let tick = 0; tick < 300; tick += 1) simulation.tick();
  simulation.stop();

  const positionById = new Map(
    simulationNodes.map((node) => [node.id, { x: node.x, y: node.y }]),
  );
  return nodes.map((node) => {
    const degree = degrees.get(node.id) ?? 0;
    const dimension = dimensions.get(node.id);
    const center = positionById.get(node.id);
    return {
      ...node,
      position: {
        x: center.x - dimension.width / 2,
        y: center.y - dimension.height / 2,
      },
      data: { ...node.data, degree },
      style: {
        ...node.style,
        width: dimension.width,
        height: dimension.height,
      },
    };
  });
}

function getInitialCenter(nodes) {
  const candidates = nodes.filter((node) => !node.data.external);
  const target = candidates.sort(
    (left, right) => (right.data.degree ?? 0) - (left.data.degree ?? 0),
  )[0];
  if (!target) return { x: 0, y: 0 };
  return {
    x: target.position.x + Number(target.style.width) / 2,
    y: target.position.y + Number(target.style.height) / 2,
  };
}

function routeEdgesToNearestHandles(edges, nodes) {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));

  return edges.map((edge) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (!source || !target) return edge;

    const sourceWidth = Number(source.style?.width) || FUNCTION_NODE_WIDTH;
    const sourceHeight = Number(source.style?.height) || FUNCTION_NODE_HEIGHT;
    const targetWidth = Number(target.style?.width) || FUNCTION_NODE_WIDTH;
    const targetHeight = Number(target.style?.height) || FUNCTION_NODE_HEIGHT;
    const sourceCenter = {
      x: source.position.x + sourceWidth / 2,
      y: source.position.y + sourceHeight / 2,
    };
    const targetCenter = {
      x: target.position.x + targetWidth / 2,
      y: target.position.y + targetHeight / 2,
    };
    const deltaX = targetCenter.x - sourceCenter.x;
    const deltaY = targetCenter.y - sourceCenter.y;
    const horizontalDistance =
      Math.abs(deltaX) / Math.max(1, (sourceWidth + targetWidth) / 2);
    const verticalDistance =
      Math.abs(deltaY) / Math.max(1, (sourceHeight + targetHeight) / 2);

    let sourceSide;
    let targetSide;
    if (horizontalDistance >= verticalDistance) {
      sourceSide = deltaX >= 0 ? "right" : "left";
      targetSide = deltaX >= 0 ? "left" : "right";
    } else {
      sourceSide = deltaY >= 0 ? "bottom" : "top";
      targetSide = deltaY >= 0 ? "top" : "bottom";
    }

    return {
      ...edge,
      sourceHandle: `source-${sourceSide}`,
      targetHandle: `target-${targetSide}`,
    };
  });
}

function normalizeGraph(payload) {
  const normalizedNodes = normalizeNodes(payload.nodes ?? payload.functions ?? []);
  const edges = normalizeEdges(payload.edges ?? payload.calls ?? []);
  const nodes = applyForceLayout(normalizedNodes, edges);
  return {
    nodes,
    edges,
    initialCenter: getInitialCenter(nodes),
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
  const [graphStatus, setGraphStatus] = useState("idle");
  const [graphError, setGraphError] = useState("");
  const [messages, setMessages] = useState(starterMessages);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [chatError, setChatError] = useState("");
  const [repositoryInput, setRepositoryInput] = useState("");
  const [activeRepo, setActiveRepo] = useState(null);
  const [ingestionStatus, setIngestionStatus] = useState("idle");
  const [ingestionError, setIngestionError] = useState("");
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

  const graphCounts = useMemo(
    () => ({
      files: nodes.filter((node) => node.data.nodeType === "File").length,
      functions: nodes.filter((node) => node.data.nodeType === "Function").length,
    }),
    [nodes],
  );
  const routedEdges = useMemo(
    () => routeEdgesToNearestHandles(edges, nodes),
    [edges, nodes],
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

    return routedEdges.map((edge) => {
      const isConnected = Boolean(focusedNodeId) && connectedEdgeIds.has(edge.id);
      return {
        ...edge,
        animated: isConnected,
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
  }, [focusedConnections, focusedNodeId, routedEdges]);

  const loadGraph = useCallback(async (repoName) => {
    if (!repoName) {
      setNodes([]);
      setEdges([]);
      setInitialCenter(null);
      setFocusedNodeId(null);
      setGraphError("");
      setGraphStatus("idle");
      return;
    }

    setGraphStatus("loading");
    setGraphError("");
    try {
      const graph = normalizeGraph(await fetchRepositoryGraph(repoName));
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

  const submitRepository = async (event) => {
    event.preventDefault();
    const repository = repositoryInput.trim();
    if (!repository || ingestionStatus === "ingesting") return;

    abortRef.current?.abort();
    setIngestionStatus("ingesting");
    setIngestionError("");
    setChatError("");
    setActiveRepo(null);
    setNodes([]);
    setEdges([]);
    setInitialCenter(null);
    setGraphError("");
    setGraphStatus("idle");

    try {
      const result = await ingestRepository(repository);
      setActiveRepo(result.repo_name);
      setIngestionStatus("ready");
      setMessages([
        starterMessages[0],
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `${result.repo_name} is indexed and ready for questions.`,
        },
      ]);
      await loadGraph(result.repo_name);
    } catch (error) {
      setIngestionStatus("error");
      setIngestionError(
        error instanceof Error ? error.message : "Repository ingestion failed",
      );
    }
  };

  const sendMessage = async (event) => {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt || streaming) return;
    if (!activeRepo || ingestionStatus !== "ready") {
      setChatError("Ingest a repository before asking code-graph questions");
      return;
    }

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
      const response = await requestChat(prompt, activeRepo, {
        signal: controller.signal,
      });
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
        if (!accumulated) accumulated = `Agent request failed: ${message}`;
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
              <i
                className={`size-1.5 rounded-full ${
                  ingestionStatus === "ready" ? "bg-[#65a56c]" : "bg-[#c6a34d]"
                }`}
              />
              {ingestionStatus === "ingesting"
                ? "Indexing"
                : activeRepo || "Select repository"}
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
              <form
                onSubmit={submitRepository}
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
                    disabled={ingestionStatus === "ingesting"}
                    onChange={(event) => setRepositoryInput(event.target.value)}
                    placeholder="https://github.com/psf/requests or psf/requests"
                    className="min-w-0 flex-1 rounded-xl border border-[#d7e0da] bg-white px-3 py-2 text-xs text-[#263a33] outline-none transition focus:border-[#92aa9f] disabled:opacity-60"
                  />
                  <button
                    type="submit"
                    disabled={!repositoryInput.trim() || ingestionStatus === "ingesting"}
                    className="rounded-xl bg-[#174f3d] px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.1em] text-white transition hover:bg-[#0f3e2f] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {ingestionStatus === "ingesting" ? "Indexing…" : "Ingest"}
                  </button>
                </div>
                {(ingestionError || activeRepo) && (
                  <p
                    className={`mt-2 text-[10px] ${
                      ingestionError ? "text-[#b45348]" : "text-[#39705e]"
                    }`}
                  >
                    {ingestionError || `Active repository: ${activeRepo}`}
                  </p>
                )}
              </form>
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
                disabled={!activeRepo || ingestionStatus !== "ready"}
                className="max-h-32 min-h-12 w-full resize-none bg-transparent px-3 py-2 text-[13px] leading-5 text-[#263a33] outline-none placeholder:text-[#9ba7a2]"
                placeholder={
                  activeRepo
                    ? "Ask about a function or dependency…"
                    : "Ingest a repository to start asking questions"
                }
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
                  {chatError ||
                    (activeRepo
                      ? "Enter to send · Shift + Enter for a new line"
                      : "Repository context is required")}
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
                    disabled={!input.trim() || !activeRepo}
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
              onClick={() => loadGraph(activeRepo)}
              disabled={!activeRepo || graphStatus === "loading"}
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
                  <button
                    onClick={() => loadGraph(activeRepo)}
                    className="mt-4 text-xs font-bold text-[#276d54] underline underline-offset-4"
                  >
                    Try again
                  </button>
                </div>
              </div>
            ) : graphStatus === "loading" ? (
              <div className="grid h-full place-items-center p-8 text-center">
                <div>
                  <Icon name="refresh" className="mx-auto size-5 animate-spin text-[#52645d]" />
                  <p className="mt-3 text-xs font-bold text-[#677a72]">
                    Loading {activeRepo}…
                  </p>
                </div>
              </div>
            ) : nodes.length === 0 ? (
              <div className="grid h-full place-items-center p-8 text-center">
                <div className="max-w-xs">
                  <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-white text-[#789084] shadow-sm">
                    <Icon name="graph" className="size-5" />
                  </div>
                  <p className="mt-4 text-sm font-bold text-[#52645d]">
                    Enter a GitHub URL above and click Ingest to visualize a
                    repository graph.
                  </p>
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
                onNodeMouseEnter={(_, node) => setFocusedNodeId(node.id)}
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
