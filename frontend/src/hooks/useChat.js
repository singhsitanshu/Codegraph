import { useEffect, useRef, useState } from "react";

import { requestChat } from "../api.js";
import { readChatResponse } from "../utils/chatResponse.js";

const starterMessages = [
  {
    id: "welcome",
    role: "assistant",
    content:
      "Ask me about the call graph — for example, “What calls verify_signature?”",
  },
];

// Owns the conversation with the code agent. `abortRef` is the request slot
// shared with repository ingestion, so either side can cancel the other.
export default function useChat(abortRef) {
  const [messages, setMessages] = useState(starterMessages);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [chatError, setChatError] = useState("");
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const stopStreaming = () => abortRef.current?.abort();

  const clearChatError = () => setChatError("");

  const resetChat = () => {
    setMessages(starterMessages);
    setInput("");
    setChatError("");
  };

  const announceRepository = (repoName) =>
    setMessages([
      starterMessages[0],
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `${repoName} is indexed and ready for questions.`,
      },
    ]);

  // `readyRepo` is the repository name when one is ready for questions, else null.
  const sendMessage = async (event, readyRepo) => {
    event.preventDefault();
    const prompt = input.trim();
    if (!prompt || streaming) return;
    if (!readyRepo) {
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
    const showAccumulatedResponse = () =>
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, content: accumulated }
            : message,
        ),
      );

    try {
      const response = await requestChat(prompt, readyRepo, {
        signal: controller.signal,
      });
      await readChatResponse(response, (text) => {
        accumulated = text;
        showAccumulatedResponse();
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        if (!accumulated) accumulated = "Response stopped.";
      } else {
        const message = error instanceof Error ? error.message : "Chat request failed";
        setChatError(message);
        if (!accumulated) accumulated = `Agent request failed: ${message}`;
      }
      showAccumulatedResponse();
    } finally {
      abortRef.current = null;
      setStreaming(false);
    }
  };

  return {
    messages,
    input,
    setInput,
    streaming,
    chatError,
    messagesEndRef,
    sendMessage,
    stopStreaming,
    clearChatError,
    resetChat,
    announceRepository,
  };
}
