import test from "node:test";
import assert from "node:assert/strict";

import { RumikAgent, buildSessionPayload, runToolHandler } from "../../sdk/browser/rumik-agent.js";


function fakeElement() {
  return {
    append() {},
    replaceChildren() {},
    textContent: "",
    hidden: false,
  };
}


test("RumikAgent keeps browser fetch bound to the global owner", async () => {
  const root = fakeElement();
  const document = {
    querySelector: () => root,
    createElement: () => fakeElement(),
  };
  let fetchOwner;
  function browserFetch() {
    fetchOwner = this;
    if (this !== globalThis) throw new TypeError("Illegal invocation");
    return Promise.resolve({
      ok: true,
      json: async () => ({ url: "wss://livekit.example", token: "token", room: "room" }),
    });
  }
  const order = [];
  class Bridge {
    async acquireMicrophone() { order.push("mic"); return { attach() {} }; }
    async acquireCamera() { order.push("camera"); return { attach() {} }; }
    async connect() { order.push("connect"); }
    async publishTrack() { order.push("publish"); }
  }
  const agent = RumikAgent.create(
    { session: "/session", prompt: "Help the user.", vision: true },
    { fetch: browserFetch, document, Bridge },
  );

  await agent.mount("#agent");

  assert.equal(fetchOwner, globalThis);
  // Permissions are obtained BEFORE the room is joined: the agent greets the
  // moment a participant appears, so the camera prompt must already be answered.
  assert.deepEqual(order, ["mic", "camera", "connect", "publish", "publish"]);
});


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


test("runToolHandler hands interactive tools the agent context", async () => {
  const sent = [];
  const context = { video: { id: "preview" }, sendData: async (message) => sent.push(message) };
  const tools = {
    snap: {
      handler: async (_args, ctx) => {
        await ctx.sendData({ type: "still", id: "s1", seq: 0, total: 1, data: "aGk=" });
        return { captured: true, video: ctx.video.id };
      },
    },
  };

  assert.deepEqual(
    await runToolHandler(tools, { id: "call-1", name: "snap", args: {} }, context),
    { type: "tool_result", id: "call-1", result: { captured: true, video: "preview" } },
  );
  assert.deepEqual(sent, [{ type: "still", id: "s1", seq: 0, total: 1, data: "aGk=" }]);
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
