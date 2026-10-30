import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import Icon from "./Icon.jsx";

export default function ChatMessage({ message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="mt-1 grid size-7 shrink-0 place-items-center rounded-full bg-[#174f3d] text-[#e4ff9b]">
          <Icon name="graph" className="size-3.5" />
        </div>
      )}
      <div
        className={`max-w-[82%] rounded-2xl px-4 py-3 text-[13px] leading-6 ${
          isUser
            ? "whitespace-pre-wrap rounded-br-md bg-[#20332d] text-white"
            : "rounded-bl-md border border-[#dce4de] bg-white text-[#3d4c47] shadow-[0_5px_18px_rgba(32,51,45,0.05)]"
        }`}
      >
        {message.content ? (
          isUser ? (
            message.content
          ) : (
            <div className="chat-markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )
        ) : (
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
