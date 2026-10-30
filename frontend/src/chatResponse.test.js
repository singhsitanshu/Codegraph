import assert from "node:assert/strict";
import test from "node:test";

import { readChatResponse } from "./utils/chatResponse.js";

function streamResponse(chunks) {
  const encoder = new TextEncoder();
  return {
    headers: { get: () => "text/event-stream" },
    body: new ReadableStream({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
        controller.close();
      },
    }),
  };
}

test("JSON chat responses report the whole answer once", async () => {
  const updates = [];
  await readChatResponse(
    {
      headers: { get: () => "application/json" },
      json: async () => ({ response: "It calls save." }),
    },
    (text) => updates.push(text),
  );

  assert.deepEqual(updates, ["It calls save."]);
});

test("event streams accumulate text across split chunks", async () => {
  const updates = [];
  await readChatResponse(
    streamResponse([
      'data: {"token":"It "}\n\ndata: {"delta":{"te',
      'xt":"calls"}}\n\n',
      "data: [DONE]\n\n",
    ]),
    (text) => updates.push(text),
  );

  assert.deepEqual(updates, ["It ", "It calls", "It calls"]);
});

test("event stream errors reject after reporting earlier text", async () => {
  const updates = [];
  await assert.rejects(
    readChatResponse(
      streamResponse([
        'data: {"text":"partial"}\n\n',
        'event: error\ndata: {"error":"agent crashed"}\n\n',
      ]),
      (text) => updates.push(text),
    ),
    /agent crashed/,
  );
  assert.deepEqual(updates, ["partial"]);
});
