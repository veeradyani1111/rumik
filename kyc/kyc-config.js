export const KYC_PROMPT = `
You are a warm, human video-KYC officer running a live verification call. You are
having a real two-way conversation with a person on camera, not reading a script.

How to converse:
- Open by greeting them by voice, saying you'll guide them through a quick identity
  check, and noting this is a demo that uses heuristic visual checks, not an
  authoritative identity decision.
- Speak in short, natural turns of one or two sentences, because your words are
  spoken aloud. Do exactly one thing per turn, then STOP and wait for the person to
  respond or act before you continue. Never monologue through all the steps at once.
- Listen. Acknowledge what they say, answer any questions or doubts plainly (for
  example why you need the card, whether their data is stored, what happens next),
  and reassure them before moving on. If they seem confused, slow down and rephrase.
- You have live camera vision through the look tool. Whenever the person asks
  ANYTHING visual — "am I visible", "can you see me", "how do I look", "is the
  lighting okay", their appearance, what they are wearing, an object they hold up,
  their surroundings, or their card — you MUST call look FIRST, in that same turn,
  and answer only from the fresh image it returns. You can only see during a turn
  in which you actually call look, so NEVER claim you cannot see them, and never
  guess at what might be visible, without calling look first. Outside of visual
  questions, just talk; don't call tools you don't need.
- Narrate as you go: before every check, say in one short sentence what is about
  to happen and what they should do, so they are never left wondering.

TRUTHFULNESS — THIS OVERRIDES EVERYTHING ELSE:
- You may ONLY report a name or date of birth that you can literally read as
  printed text in an image returned by look or attached by captureCard. If a PAN
  card is not clearly in view, or a field is blurry, glared, cut off, or
  unreadable, you MUST say exactly that and ask for a new capture. NEVER invent,
  guess, complete, or assume any value. A made-up detail is a serious failure;
  asking again is always correct.
- Never take the name or DOB from what the person SAYS out loud — spoken words
  are not proof of what is on the card. The card's values come only from the image.
- Before reading any field, first describe out loud what you actually see in the
  frame (for example "I can see your face but no card yet", or "I can see a card but
  the text is too blurry to read"). Only read out details once you can genuinely
  make them out.
- Do NOT read the PAN number aloud and do not use it for any check — this flow
  verifies only the printed name and date of birth.

Run these checks in order, one conversational turn at a time:
1. Card photo. Tell them a card-shaped frame is about to appear on their screen:
   they should hold their PAN card flat inside the box and press "Capture photo"
   (a short countdown fires the shot). Then call captureCard and wait patiently —
   it takes as long as the person takes, and that is normal. When it returns with
   photo_attached true, you receive a high-resolution photo of the card: FIRST
   describe what you actually see in it, then read the name and date of birth back
   to them. Ignore the PAN number entirely. If it returns captured false, or a
   field is blurry, glared, or cut off, say what went wrong, coach them (more
   light, hold closer, keep steady, tilt away from glare), and call captureCard
   again — up to three attempts. If you never get a legible photo, mark card_read
   as fail — do not fabricate values to move on.
2. Ask them to tilt the card slowly side to side. Call look with motion=true and
   check the burst for a shifting hologram or specular reflection (hologram check).
3. Give one liveness challenge such as "please blink twice" or "slowly turn their
   head left and right". Call look with motion=true and judge whether the requested
   motion actually happened (face_liveness check).
4. Face match: check that the person on camera is the same person as the photo
   printed on their PAN card. Ask them to hold the card beside their face, call look
   with motion=false, and compare the printed card photo to their live face. Mark
   face_match pass only if they are clearly the same person, fail if they are clearly
   different, and unclear if the photo or face is not visible enough to judge. This
   is a heuristic visual comparison, not biometric proof — say so.
5. Confirm the identity against the claim. The values this applicant registered are
   given under CLAIMED IDENTITY below (if provided). Set name_match to pass only when
   the name and DOB you actually READ FROM THE CARD match those claimed values;
   fail when they clearly differ; unclear when you could not read enough to compare.
   Minor formatting differences (letter case, honorifics like MR/MS, or the date
   written in a different format such as 12/05/1998 vs 1998-05-12) still count as a
   match. If no claim was provided, instead ask them to say their full name and
   compare it with the name printed on the card.
6. When every check is done, call submitResult exactly once with the complete
   structured result, filling card_read, hologram, face_liveness, face_match, and
   name_match. Decide:
   - pass  → only when ALL FIVE checks pass. Tell them warmly: "You're verified."
   - fail  → when the card cannot be read, the details don't match the claim, or the
             face clearly doesn't match the card photo. Give the reason kindly.
   - needs_review → anything inconclusive. Say: "Thanks — we've noted your details and
             our team will review this and get back to you shortly."
   Never announce a verdict before you have actually run the checks and called
   submitResult.

If the camera stays unavailable and look keeps returning no frame, do not loop
silently: explain out loud that you cannot see their camera, ask them to enable it,
and keep the conversation going rather than going quiet.

Never claim the visual liveness or face-match checks are tamper-proof. Put that
limitation in notes.
`.trim();


// Appended per session so the agent has a reference to verify against. The claimed
// identity is what the applicant registered BEFORE the call — the card and face are
// checked against it. It is never to be read out as if it came from the card.
function claimedIdentityBlock(expected = {}) {
  const name = String(expected.name ?? "").trim();
  const dob = String(expected.dob ?? "").trim();
  if (!name && !dob) {
    return (
      "\n\nCLAIMED IDENTITY: none was provided for this session. For the name_match " +
      "check, ask the person to say their full name and compare it with the name " +
      "printed on the card."
    );
  }
  return (
    "\n\nCLAIMED IDENTITY (registered by this applicant before the call — verify the " +
    "card and live face against THESE values; do NOT read them aloud as if they came " +
    "from the card):\n" +
    `- name: ${name || "(not provided)"}\n` +
    `- date of birth: ${dob || "(not provided)"}`
  );
}

// --- High-resolution card capture -------------------------------------------
// The live WebRTC stream is too compressed to read small card text reliably.
// captureCard shows a card-shaped guide box over the preview, lets the person
// position the card, then grabs a full-resolution still straight off the local
// camera track (no WebRTC compression), crops to the box, and streams the JPEG
// to the worker over the data channel in chunks. The worker attaches it to the
// model as an image, so the card is read from a crisp photo.

const CARD_ASPECT = 85.6 / 54; // ISO ID-1 card
const STILL_CHUNK_CHARS = 12_000; // stays under LiveKit's data-packet limit
const STILL_MAX_SIDE = 1600;
const CAPTURE_TIMEOUT_MS = 60_000;
const CAPTURE_COUNTDOWN_S = 3;

export function chunkString(text, size) {
  const chunks = [];
  for (let start = 0; start < text.length; start += size) {
    chunks.push(text.slice(start, start + size));
  }
  return chunks;
}

// Map the centered on-screen guide box into native video pixels, accounting for
// object-fit: cover. A small margin keeps slight misalignment from clipping the
// card edges. Both the box and the cover-crop are centered, so the crop is too.
export function cardCropRect(dispW, dispH, vidW, vidH, { boxFraction = 0.74, margin = 0.06 } = {}) {
  const scale = Math.max(dispW / vidW, dispH / vidH);
  let boxW = dispW * boxFraction;
  let boxH = boxW / CARD_ASPECT;
  if (boxH > dispH * 0.8) {
    boxH = dispH * 0.8;
    boxW = boxH * CARD_ASPECT;
  }
  const w = Math.min(vidW, (boxW / scale) * (1 + margin * 2));
  const h = Math.min(vidH, (boxH / scale) * (1 + margin * 2));
  return { x: (vidW - w) / 2, y: (vidH - h) / 2, w, h, boxW, boxH };
}

// Let pending layout settle so freshly attached or resized video elements
// report their real geometry before we measure them. rAF stalls entirely on
// hidden pages, so a timeout fallback keeps the tool from hanging.
function nextLayout(view) {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, 200);
    const raf = view?.requestAnimationFrame?.bind(view);
    if (raf) raf(() => raf(() => { clearTimeout(timer); resolve(); }));
  });
}

function buildCaptureOverlay(video, boxW, boxH) {
  const doc = video.ownerDocument;
  const wrap = video.parentElement;
  if (!wrap.style.position) wrap.style.position = "relative";
  const videoRect = video.getBoundingClientRect();
  const wrapRect = wrap.getBoundingClientRect();
  const overlay = doc.createElement("div");
  overlay.style.cssText =
    `position:absolute; left:${videoRect.left - wrapRect.left}px; top:${videoRect.top - wrapRect.top}px; ` +
    `width:${videoRect.width}px; height:${videoRect.height}px; z-index:5; ` +
    "display:flex; flex-direction:column; align-items:center; justify-content:center; " +
    "gap:.8rem; overflow:hidden; font-family:inherit;";
  overlay.style.borderRadius = getComputedStyle(video).borderRadius;
  const caption = doc.createElement("p");
  caption.textContent = "Fit your PAN card inside the box, then press Capture";
  caption.style.cssText =
    "position:relative; z-index:1; margin:0; color:#fff; font-weight:600; " +
    "font-size:.95rem; text-align:center; text-shadow:0 1px 6px rgba(0,0,0,.6); padding:0 1rem;";
  const box = doc.createElement("div");
  box.style.cssText =
    `width:${boxW}px; height:${boxH}px; border:3px solid #2dd4bf; border-radius:14px; ` +
    "box-shadow:0 0 0 200vmax rgba(8,15,26,.6); flex:0 0 auto;";
  const controls = doc.createElement("div");
  controls.style.cssText = "position:relative; z-index:1; display:flex; gap:.6rem;";
  const capture = doc.createElement("button");
  capture.type = "button";
  capture.textContent = "Capture photo";
  capture.style.cssText =
    "border:0; border-radius:999px; padding:.6rem 1.3rem; font-weight:700; cursor:pointer; " +
    "background:#0d9488; color:#fff; font-size:.95rem;";
  const cancel = doc.createElement("button");
  cancel.type = "button";
  cancel.textContent = "Cancel";
  cancel.style.cssText =
    "border:0; border-radius:999px; padding:.6rem 1.1rem; font-weight:600; cursor:pointer; " +
    "background:rgba(255,255,255,.18); color:#fff; font-size:.95rem;";
  controls.append(capture, cancel);
  overlay.append(caption, box, controls);
  wrap.append(overlay);
  return { overlay, caption, capture, cancel };
}

async function captureCardStill({ video, sendData } = {}) {
  if (!video || !video.videoWidth) return { captured: false, reason: "no_camera_frame" };
  await nextLayout(video.ownerDocument?.defaultView);
  const rect = cardCropRect(video.clientWidth, video.clientHeight, video.videoWidth, video.videoHeight);
  const ui = buildCaptureOverlay(video, rect.boxW, rect.boxH);
  try {
    const action = await new Promise((resolve) => {
      const timer = setTimeout(() => resolve("timeout"), CAPTURE_TIMEOUT_MS);
      ui.cancel.onclick = () => { clearTimeout(timer); resolve("cancelled"); };
      ui.capture.onclick = async () => {
        // Short countdown so the click-hand shake settles before the shot.
        ui.capture.disabled = true;
        ui.cancel.disabled = true;
        for (let n = CAPTURE_COUNTDOWN_S; n > 0; n--) {
          ui.caption.textContent = `Hold steady… ${n}`;
          await new Promise((tick) => setTimeout(tick, 1000));
        }
        clearTimeout(timer);
        resolve("capture");
      };
    });
    if (action !== "capture") return { captured: false, reason: action };
    const scaleOut = Math.min(1, STILL_MAX_SIDE / Math.max(rect.w, rect.h));
    const canvas = video.ownerDocument.createElement("canvas");
    canvas.width = Math.round(rect.w * scaleOut);
    canvas.height = Math.round(rect.h * scaleOut);
    canvas
      .getContext("2d")
      .drawImage(video, rect.x, rect.y, rect.w, rect.h, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
    const base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
    const stillId = `card_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    const chunks = chunkString(base64, STILL_CHUNK_CHARS);
    for (let seq = 0; seq < chunks.length; seq += 1) {
      await sendData({ type: "still", id: stillId, seq, total: chunks.length, data: chunks[seq] });
    }
    return { captured: true, still_id: stillId, width: canvas.width, height: canvas.height };
  } finally {
    ui.overlay.remove();
  }
}

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
        face_match: CHECK_SCHEMA,
      },
      required: ["card_read", "hologram", "face_liveness", "name_match", "face_match"],
      additionalProperties: false,
    },
    extracted: {
      type: "object",
      properties: {
        name: { type: "string" },
        dob: { type: "string" },
      },
      required: ["name", "dob"],
      additionalProperties: false,
    },
    notes: { type: "string" },
  },
  required: ["decision", "checks", "extracted", "notes"],
  additionalProperties: false,
};


export function createKycConfig({ fetch: fetchImpl = globalThis.fetch, onResult = () => {}, expected = {} } = {}) {
  let sessionId = "";
  return {
    session: "/session",
    vision: true,
    prompt: KYC_PROMPT + claimedIdentityBlock(expected),
    // Lighter vision: 3 motion frames instead of 5 (fewer images per look = faster
    // vision turns) over a shorter window. Single-frame card reads stay full-res.
    options: { max_fps: 2, burst_count: 3, burst_window_ms: 1000, max_frames_per_min: 40 },
    onEvent(event) {
      if (event?.type === "session_started") sessionId = event.room;
    },
    tools: {
      captureCard: {
        description:
          "Show an on-screen card frame and capture a high-resolution photo of the user's " +
          "PAN card. Waits for the user to position the card and press the capture button; " +
          "on success the photo is attached to your context as an image.",
        parameters: {},
        timeoutSecs: 75,
        async handler(_args, context) {
          return captureCardStill(context);
        },
      },
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
    },
  };
}
