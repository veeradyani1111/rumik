import test from "node:test";
import assert from "node:assert/strict";

import { KYC_PROMPT, cardCropRect, chunkString, createKycConfig } from "../../kyc/kyc-config.js";


test("KYC is expressed entirely as a generic prompt and client tool", () => {
  const config = createKycConfig({ fetch: async () => ({ ok: true, json: async () => ({}) }) });

  assert.equal(config.vision, true);
  assert.match(KYC_PROMPT, /look.*motion=true/is);
  assert.match(KYC_PROMPT, /submitResult/);
  assert.deepEqual(Object.keys(config.tools), ["captureCard", "submitResult"]);
  // The flow verifies only name + DOB; the PAN number is never collected or matched.
  assert.deepEqual(config.tools.submitResult.parameters.properties.extracted.required, ["name", "dob"]);
  // Positioning a card takes human time; the capture tool must outlive the default timeout.
  assert.equal(config.tools.captureCard.timeoutSecs, 75);
  const schema = config.tools.submitResult.parameters;
  assert.equal(schema.type, "object");
  assert.deepEqual(schema.required, ["decision", "checks", "extracted", "notes"]);
  assert.equal(schema.properties.session_id, undefined);
  assert.deepEqual(schema.properties.checks.required, [
    "card_read",
    "hologram",
    "face_liveness",
    "name_match",
    "face_match",
  ]);
});


test("chunkString splits and reassembles without loss", () => {
  const text = "a".repeat(12_000) + "b".repeat(12_000) + "c".repeat(5);
  const chunks = chunkString(text, 12_000);

  assert.deepEqual(chunks.map((chunk) => chunk.length), [12_000, 12_000, 5]);
  assert.equal(chunks.join(""), text);
  assert.deepEqual(chunkString("", 12_000), []);
});


test("cardCropRect maps the centered guide box through object-fit cover", () => {
  // 640x400 display over a 1920x1080 video: cover scales by 400/1080.
  const rect = cardCropRect(640, 400, 1920, 1080, { margin: 0 });

  const scale = 400 / 1080;
  const expectedW = (640 * 0.74) / scale;
  assert.ok(Math.abs(rect.w - expectedW) < 1e-6);
  assert.ok(Math.abs(rect.h - expectedW / (85.6 / 54)) < 1e-6);
  // Crop stays centered and inside the video.
  assert.ok(Math.abs(rect.x + rect.w / 2 - 960) < 1e-6);
  assert.ok(Math.abs(rect.y + rect.h / 2 - 540) < 1e-6);
  assert.ok(rect.x >= 0 && rect.y >= 0);
  assert.ok(rect.x + rect.w <= 1920 && rect.y + rect.h <= 1080);
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
  config.onEvent({ type: "session_started", room: "sess_actual" });
  const result = { decision: "pass", session_id: "sess_hallucinated" };

  assert.deepEqual(await config.tools.submitResult.handler(result), { stored: true });
  const expected = { decision: "pass", session_id: "sess_actual" };
  assert.deepEqual(calls, [["/kyc-result", expected]]);
  assert.deepEqual(rendered, [expected]);
});
