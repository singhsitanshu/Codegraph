import { useCallback, useEffect, useRef, useState } from "react";

import ChatPanel from "./features/chat/ChatPanel.jsx";
import CodePanel from "./features/code/CodePanel.tsx";
import GraphPanel from "./features/graph/GraphPanel.jsx";
import useChat from "./features/chat/useChat.js";
import useCodeGraph from "./features/graph/useCodeGraph.js";
import useRepository from "./features/repository/useRepository.js";

function App() {
  // One in-flight request slot shared by ingestion and chat: starting or
  // deleting a repository aborts a streaming answer, and unmounting aborts
  // whichever request is running.
  const abortRef = useRef(null);
  const graph = useCodeGraph();
  const chat = useChat(abortRef);
  const repository = useRepository({
    abortRef,
    onIngestionStarted: () => {
      chat.clearChatError();
      graph.clearGraph();
    },
    onIngested: async (repoName) => {
      chat.announceRepository(repoName);
      await graph.loadGraph(repoName);
    },
    onDeleted: () => {
      graph.clearGraph();
      chat.resetChat();
    },
  });
  const { activeRepo } = repository;
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [isGraphMaximized, setIsGraphMaximized] = useState(false);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    setSelectedNodeId(null);
  }, [activeRepo]);

  const closeCodePanel = useCallback(() => setSelectedNodeId(null), []);
  const openFunctionCode = useCallback((_event, node) => {
    if (node.data?.nodeType === "Function") {
      setSelectedNodeId(node.id);
    }
  }, []);

  return (
    <main className="h-dvh overflow-hidden bg-[#f5f6f1] text-[#20332d]">
      <div
        className={`grid h-full grid-cols-1 transition-[grid-template-columns] duration-300 ease-in-out ${
          isGraphMaximized
            ? "lg:grid-cols-[0fr_minmax(0,1fr)]"
            : "lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
        }`}
      >
        <ChatPanel
          chat={chat}
          repository={repository}
          isGraphMaximized={isGraphMaximized}
        />
        <GraphPanel
          graph={graph}
          repository={repository}
          isGraphMaximized={isGraphMaximized}
          onToggleGraphMaximized={() =>
            setIsGraphMaximized((current) => !current)
          }
          onNodeClick={openFunctionCode}
        />
      </div>
      <CodePanel
        nodeId={selectedNodeId}
        repoName={activeRepo}
        onClose={closeCodePanel}
      />
    </main>
  );
}

export default App;
