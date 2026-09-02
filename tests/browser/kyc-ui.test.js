import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";


test("agent audio ends the joining state before the greeting plays", () => {
  const source = readFileSync(new URL("../../kyc/index.html", import.meta.url), "utf8");
  const agentAudioCase = source.match(/case "agent_audio":([\s\S]*?)break;/)?.[1] ?? "";

  assert.match(agentAudioCase, /voiceArrived = true/);
  assert.match(agentAudioCase, /joining\.hidden = true/);
  assert.match(agentAudioCase, /setStatus\("Live/);
});
