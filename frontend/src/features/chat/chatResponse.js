export function extractSseText(data) {
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

export function extractSseError(data) {
  try {
    const payload = JSON.parse(data);
    return payload.error ?? data;
  } catch {
    return data;
  }
}

// Reads a chat response that is either a JSON body or a server-sent event
// stream, calling onText with the full answer accumulated so far after every
// chunk. Throws when the stream reports an error event.
export async function readChatResponse(response, onText) {
  let accumulated = "";
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const payload = await response.json();
    accumulated = payload.response ?? "";
    onText(accumulated);
    return;
  }
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
      onText(accumulated);
    }
    if (done) break;
  }
}
