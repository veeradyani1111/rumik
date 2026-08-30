import test from "node:test";
import assert from "node:assert/strict";

import { buildSessionPayload, runToolHandler } from "../../sdk/browser/rumik-agent.js";


test("buildSessionPayload sends schemas but never browser handlers", () => {
  const handler = async () => "secret-browser-result";
  const payload = buildSessionPayload({
    prompt: "Be helpful",
    vision: true,
    voice: { model: "muga" },
    options: { max_fps: 2 },
    tools: {
      submitResult: {
        description: "Store the result",
        parameters: { decision: "pass | fail | needs_review" },
        handler,
      },
    },
  });

  assert.deepEqual(payload.tools, [
    {
      name: "submitResult",
      description: "Store the result",
      parameters: { decision: "pass | fail | needs_review" },
    },
  ]);
  assert.equal(JSON.stringify(payload).includes("secret-browser-result"), false);
});


test("runToolHandler awaits the named browser function", async () => {
  const tools = {
    add: { handler: async ({ left, right }) => left + right },
  };

  assert.deepEqual(
    await runToolHandler(tools, { id: "call-1", name: "add", args: { left: 2, right: 3 } }),
    { type: "tool_result", id: "call-1", result: 5 },
  );
});


test("runToolHandler returns stable errors for missing and throwing handlers", async () => {
  assert.deepEqual(
    await runToolHandler({}, { id: "call-1", name: "missing", args: {} }),
    { type: "tool_result", id: "call-1", result: { error: "unknown_tool" } },
  );
  assert.deepEqual(
    await runToolHandler(
      { explode: { handler: async () => { throw new Error("boom"); } } },
      { id: "call-2", name: "explode", args: {} },
    ),
    { type: "tool_result", id: "call-2", result: { error: "boom" } },
  );
});
