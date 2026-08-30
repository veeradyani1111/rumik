import test from "node:test";
import assert from "node:assert/strict";

import { KYC_PROMPT, createKycConfig } from "../../kyc/kyc-config.js";


test("KYC is expressed entirely as a generic prompt and client tool", () => {
  const config = createKycConfig({ fetch: async () => ({ ok: true, json: async () => ({}) }) });

  assert.equal(config.vision, true);
  assert.match(KYC_PROMPT, /look.*motion=true/is);
  assert.match(KYC_PROMPT, /submitResult/);
  assert.deepEqual(Object.keys(config.tools), ["submitResult", "validatePan"]);
});


test("submitResult persists through the developer proxy before rendering", async () => {
  const calls = [];
  const rendered = [];
  const config = createKycConfig({
    fetch: async (url, init) => {
      calls.push([url, JSON.parse(init.body)]);
      return { ok: true, json: async () => ({ stored: true }) };
    },
    onResult: (result) => rendered.push(result),
  });
  const result = { decision: "pass", session_id: "sess_1" };

  assert.deepEqual(await config.tools.submitResult.handler(result), { stored: true });
  assert.deepEqual(calls, [["/kyc-result", result]]);
  assert.deepEqual(rendered, [result]);
});
