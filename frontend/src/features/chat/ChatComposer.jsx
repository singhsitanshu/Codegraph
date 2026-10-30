import Icon from "../../shared/Icon.jsx";

export default function ChatComposer({ chat, repository }) {
  const { activeRepo, isDeleting, isRepositoryReady } = repository;
  const { chatError, input, setInput, streaming } = chat;

  return (
    <div className="shrink-0 px-5 pb-5 md:px-8 md:pb-7">
      <form
        onSubmit={(event) =>
          chat.sendMessage(event, isRepositoryReady ? activeRepo : null)
        }
        className="mx-auto max-w-2xl rounded-[20px] border border-[#d7e0da] bg-white p-2 shadow-[0_14px_40px_rgba(32,51,45,0.09)] focus-within:border-[#92aa9f]"
      >
        <textarea
          aria-label="Message"
          disabled={!isRepositoryReady}
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
              onClick={chat.stopStreaming}
              className="grid size-8 place-items-center rounded-xl bg-[#edf1ee] text-[#43554f] transition hover:bg-[#e1e8e3]"
              aria-label="Stop response"
            >
              <Icon name="stop" className="size-4" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim() || !activeRepo || isDeleting}
              className="grid size-8 place-items-center rounded-xl bg-[#174f3d] text-white transition hover:bg-[#0f3e2f] disabled:cursor-not-allowed disabled:opacity-35"
              aria-label="Send message"
            >
              <Icon name="arrow" className="size-4" />
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
