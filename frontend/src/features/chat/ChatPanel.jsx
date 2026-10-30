import ChatComposer from "./ChatComposer.jsx";
import ChatMessage from "./ChatMessage.jsx";
import Icon from "../../shared/Icon.jsx";
import RepositoryForm from "../repository/RepositoryForm.jsx";

export default function ChatPanel({ chat, repository, isGraphMaximized }) {
  const { activeRepo, isDeleting, isIngesting } = repository;

  return (
    <section
      className={`flex min-h-0 min-w-0 flex-col border-b border-[#d9e0da] bg-[#f8f9f5] transition-opacity duration-200 lg:border-r lg:border-b-0 ${
        isGraphMaximized
          ? "lg:pointer-events-none lg:invisible lg:overflow-hidden lg:opacity-0"
          : "lg:visible lg:opacity-100"
      }`}
    >
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
              activeRepo ? "bg-[#65a56c]" : "bg-[#c6a34d]"
            }`}
          />
          {isIngesting
            ? "Indexing"
            : isDeleting
              ? "Deleting"
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
          <RepositoryForm repository={repository} />
          {chat.messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}
          <div ref={chat.messagesEndRef} />
        </div>
      </div>

      <ChatComposer chat={chat} repository={repository} />
    </section>
  );
}
