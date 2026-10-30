import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
} from "d3-force";

const FUNCTION_NODE_WIDTH = 150;
const FUNCTION_NODE_HEIGHT = 52;
const FILE_NODE_MIN_WIDTH = 190;
const FILE_NODE_MIN_HEIGHT = 72;
const MANY_BODY_STRENGTH = -45;
const LINK_DISTANCE = 100;

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

export function applyForceLayout(nodes, edges) {
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

export function getInitialCenter(nodes) {
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

export function routeEdgesToNearestHandles(edges, nodes) {
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
