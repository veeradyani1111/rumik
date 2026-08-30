export const KYC_PROMPT = `
You are a warm, concise video-KYC verification agent. Explain that this is a demo
using heuristic visual checks, not an authoritative identity decision.

Follow these steps in order:
1. Ask the user to hold their PAN card steady. Call look with motion=false. Read
   the name, PAN, and DOB. Retry at most three times if the card is unusable.
2. Ask the user to tilt the card slowly side to side. Call look with motion=true
   and compare the burst for a shifting hologram or specular reflection.
3. Give one random liveness challenge: blink twice or turn their head. Call look
   with motion=true and judge whether the requested motion occurred.
4. Ask the user to say their full name. Compare it with the card name.
5. Call submitResult exactly once with the complete structured result. Pass only
   when card_read, hologram, face_liveness, and name_match all pass. Fail when the
   card read or name match fails. Otherwise use needs_review.

Never claim the visual liveness checks are tamper-proof. Put that limitation in notes.
`.trim();

const CHECK_SCHEMA = {
  type: "object",
  properties: {
    status: { type: "string", enum: ["pass", "fail", "unclear"] },
    confidence: { type: "number", minimum: 0, maximum: 1 },
    reasons: { type: "array", items: { type: "string" } },
  },
  required: ["status", "confidence", "reasons"],
  additionalProperties: false,
};

const RESULT_SCHEMA = {
  type: "object",
  properties: {
    decision: { type: "string", enum: ["pass", "fail", "needs_review"] },
    checks: {
      type: "object",
      properties: {
        card_read: CHECK_SCHEMA,
        hologram: CHECK_SCHEMA,
        face_liveness: CHECK_SCHEMA,
        name_match: CHECK_SCHEMA,
      },
      required: ["card_read", "hologram", "face_liveness", "name_match"],
      additionalProperties: false,
    },
    extracted: {
      type: "object",
      properties: {
        name: { type: "string" },
        pan: { type: "string" },
        dob: { type: "string" },
      },
      required: ["name", "pan", "dob"],
      additionalProperties: false,
    },
    session_id: { type: "string", description: "Injected by the browser SDK event when omitted" },
    notes: { type: "string" },
  },
  required: ["decision", "checks", "extracted", "notes"],
  additionalProperties: false,
};


export function createKycConfig({ fetch: fetchImpl = globalThis.fetch, onResult = () => {} } = {}) {
  let sessionId = "";
  return {
    session: "/session",
    vision: true,
    prompt: KYC_PROMPT,
    options: { max_fps: 2, burst_count: 5, burst_window_ms: 1500, max_frames_per_min: 40 },
    onEvent(event) {
      if (event?.type === "session_started") sessionId = event.room;
    },
    tools: {
      submitResult: {
        description: "Persist and display the final structured KYC decision",
        parameters: RESULT_SCHEMA,
        async handler(result) {
          if (!sessionId) throw new Error("Session ID is not available yet");
          const normalizedResult = { ...result, session_id: sessionId };
          const response = await fetchImpl("/kyc-result", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(normalizedResult),
          });
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.message ?? "Could not store KYC result");
          onResult(normalizedResult);
          return payload;
        },
      },
      validatePan: {
        description: "Check whether a normalized PAN has the expected Indian PAN format",
        parameters: { pan: "string" },
        async handler({ pan }) {
          const normalized = String(pan ?? "").trim().toUpperCase();
          return { normalized, valid: /^[A-Z]{5}[0-9]{4}[A-Z]$/.test(normalized) };
        },
      },
    },
  };
}
