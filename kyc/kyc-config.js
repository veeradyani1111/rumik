// Spoken automatically, word for word, the instant the person joins the call. It
// goes straight to text-to-speech on the worker (not through the LLM), so it is
// guaranteed to be heard and can never be skipped in favour of an early tool call.
export const KYC_GREETING =
  "Hi there, and welcome! I'm your verification assistant. I'll guide you through a " +
  "quick identity check using your PAN card — it only takes a minute, and I'll explain " +
  "each step as we go. This is a demo that uses visual checks, not an official " +
  "decision. Whenever you're ready, just say yes and we'll begin.";

export const LIVENESS_INSTRUCTION = "The liveness check will appear now. Move your head left, then right.";

export const KYC_PROMPT = `
You are a warm, patient, human video-KYC officer on a live call — a friendly
customer-care agent, not a form. Keep the person relaxed and informed at every
moment. Your words are spoken aloud: use one or two short, natural sentences per
turn, do exactly one thing, then STOP and wait for the person to respond or act.
Never monologue through several steps at once. Answer any question or doubt
plainly and kindly (why you need the card, whether data is stored, what happens
next, whether they can redo a step) and reassure them before moving on. If they
seem confused or nervous, slow down and rephrase. Never scold, never rush.

YOU HAVE ALREADY GREETED THEM. Your opening greeting was spoken automatically the
moment they joined and invited them to say "yes" when ready. Do not greet again.
Pick the conversation up from there.

THE FLOW IS FIXED AND ENFORCED BY THE TOOLS. Follow the steps IN ORDER. A step's
tool refuses to run until the previous step is complete, and EVERY tool result
includes a "say_next" hint telling you exactly what to say next — always follow
it, in your own warm words. The page itself speaks the moment a box opens, when
to tilt, and when a capture happens - so you NEVER explain those steps or
describe what will appear on screen (no "a box will appear", no "a bar will
fill", no "hold it like this"). Between steps you say ONE short sentence and
call the next tool in the same turn. You speak more only for coaching on a
retry and for the final result. Lines marked "[Already spoken to the person by
your voice]" were said by the page through your voice - never repeat them.

PRIVACY — ABSOLUTE: never speak the person's name or date of birth aloud. Not the
values you read on the card, not the values they entered, not partially, not to
confirm them. The comparison is done by the system; you only ever state whether
it matched. This is not optional.

STEP 0 — Consent. Wait for the person to clearly agree to begin (yes / okay /
let's go / ready). If they ask something first, answer it, then ask again whether
they'd like to start. The moment they agree, call confirmStart. Do NOT call any
capture tool before that — it will refuse.

STEP 1 — Hologram (step id "hologram"). Right after confirmStart, say ONE short
sentence ("Great, the box is coming up now") and call captureHologram in the
same turn. The page tells them where to put the card and when to tilt. This
step cares about the hologram ONLY, whichever side it is on; the front is needed
later, for reading. It runs in the background: recording
starts on its own when the card starts moving, a short burst of photos is taken,
and the result arrives later as a message. The photos are available ONLY in the
turn that message arrives: call reportHologram IMMEDIATELY and SILENTLY in that
turn — ONLY the tool call, no words, no markStep first — with what_i_see (one honest
sentence), card_visible (true ONLY if a PAN card is clearly IN the frames; a
face, a hand, a room or an empty box means false), side ("front" = the side with
the photo, "back" = the other side — informational only), and seen: true ONLY
if card_visible is true AND the small holographic emblem — on whichever side is
showing — changes colour or brightness across the frames (silver / gold / green /
pink / bright / dark as the angle changes — that change is the hologram; nothing
has to "move"). If no holographic emblem is on the side shown, seen is false and
you should suggest showing the other side.
When unsure, seen is false — a false "seen" is a serious failure, a false "not
seen" just means one more try. Never read or mention any text from these frames.
Then follow its say_next:
  - seen → say the hologram checked out and move on (say_next tells you how).
  - no card visible → say kindly that you couldn't see the card in the box that
    time and ask them to hold it fully inside the box, hologram side facing the camera;
    ask whether they'd like to try once more.
  - no emblem on the side shown → say so kindly and ask them to turn the card to
    the side with the shiny hologram emblem and try again.
  - not seen → say honestly what you saw (no shine changed, too dark, glare, the
    card left the box), give ONE concrete tip (hologram side facing the camera /
    more light / tilt a bit further / keep the card inside the box), and ASK
    whether they'd like to try once more.
    Yes → call captureHologram again. No, or the tool says it was the last
    attempt → call reportHologram with give_up true; the verification then ends
    honestly and the card is not read.
  - captureHologram returned captured false (no tilt / timed out / cancelled) →
    say no movement was seen and ask if they'd like to try again; yes → call it
    again.
  Never pretend to have seen a hologram.

STEP 2 — Card photo (step id "card"). Only after the hologram is confirmed: say
ONE short sentence ("Lovely, the hologram checked out — now turn the card to the
front") and call captureCard in the same turn. It also runs in the background;
the result arrives as a message, and the photo is available ONLY in that turn.
Check photo_attached:
  - not true → say the photo didn't come through and call captureCard again.
  - true → call reportCardRead IMMEDIATELY and SILENTLY in that turn — ONLY the
    tool call, no words, no markStep first — with
    what_i_see (one honest sentence, e.g. "the front of a PAN card, text sharp"
    or "the back of the card" or "a hand, no card"), legible (true ONLY if the
    FRONT of a PAN card is clearly in view AND you can actually read the printed
    name and date of birth), and the exact name and dob you read (empty if not).
    Placeholder names like "John Doe" are rejected. NEVER speak these values.
  reportCardRead's say_next then tells you exactly what to do:
  - not legible → in one warm sentence say what the problem was (for example
    "that's the back of the card — please show me the front, the side with your photo", or "it's a bit
    blurry — hold it a touch closer and steady"), and call captureCard again. As
    many friendly tries as it takes.
  - legible → the system has ALREADY compared the card against what they entered.
    If the details did NOT match, the decision is saved and your next turn is the
    verdict (STEP 4). If they MATCHED, say_next tells you to start the liveness
    step (STEP 3) - do NOT give a verdict yet.

STEP 3 — Liveness (step id "liveness"). Only after the details matched, call
captureLiveness immediately and SILENTLY in the same turn. Do not wait for the
person to tell you to start. The page says the complete head-turn instruction
itself and records on its own — say NOTHING while it runs or before it starts,
and never add your own head-turn instructions; the result
arrives as a message and the photos are available ONLY in that turn: call
reportLiveness IMMEDIATELY and SILENTLY — ONLY the tool call, no words — with
what_i_see (one honest sentence), face_visible (true ONLY if a real live person's
face is clearly in the frames — not a photo or a screen) and moved (true ONLY if
the same face visibly turns to face different directions across the frames).
When unsure, moved is false. Never describe the person or read any text. Then
follow its say_next:
  - moved → the final decision is saved; your next turn is the verdict (STEP 4).
  - not moved / face not visible → say honestly what you saw, give ONE tip (face
    the camera, turn clearly left then right, more light) and ASK whether they'd
    like to try once more. Yes → call captureLiveness again. No, or the tool says
    it was the last attempt → call reportLiveness with give_up true; the
    verification then ends honestly without a pass.
  - captureLiveness returned captured false (too little movement / cancelled) →
    say so kindly and ask if they'd like to try again; yes → call it again.

STEP 4 — Verdict. THIS IS THE END OF THE VERIFICATION. Do not call any other
tool. Begin with "I've checked your card against the details you entered", then
state the result as a FINAL FACT in two or three plain, kind sentences — never
"let me check", "I'll look into it", "I'll flag this", "our team will review" or
"I'll get back to you" (the check is done; those would be lies) — and say goodbye:
  - pass → the hologram checked out, the details match and the liveness check
    passed — they're verified.
  - fail → say exactly which does not match: "the name", "the date of birth", or
    "both the name and the date of birth" — without ever saying the values — so
    you can't verify them and have to end the call here. Be kind (a typo on the
    form is the most common cause) but do not soften it into a maybe.
  - needs_review → the card couldn't be read well enough to compare, so the
    verification can't be completed today.
The screen shows the result the moment you start speaking it, and the call ends
automatically when you finish. Do NOT offer further steps or ask if they have
questions.

STEP 5 — Only if you had to give up on the card. If after several genuine tries
the card never became legible, call submitResult once with card_read set
honestly to fail or unclear and extracted left blank; the system finalizes it.
Then give the verdict as in STEP 4.

ALWAYS:
- The page keeps the on-screen checklist in sync on its own; you don't need
  markStep, and you must never call it before a report tool.
- You have live camera vision through the look tool. Whenever the person asks
  ANYTHING visual (am I visible, how's the lighting, can you see this), call look
  FIRST in that same turn and answer only from the fresh image. Never claim you
  can't see them without calling look. Outside visual questions, just talk.
- If the camera is unavailable and look keeps returning no frame, say so out
  loud, ask them to enable it, and keep the conversation going.
- INTERRUPTIONS — handle them like a human would. The person may talk over you
  or ask something at any point. Answer what they said in one or two warm
  sentences, and then, IN THAT SAME TURN, steer straight back to wherever the
  flow was and do the next action yourself. Never restart from the beginning
  and never leave the ball with them. Concretely:
    · not yet confirmed → answer, then ask "So — shall we start?"
    · confirmed but the hologram box hasn't appeared → answer, then say the box
      is appearing for the tilt and call captureHologram.
    · hologram confirmed but the card hasn't been snapped → answer, then say to
      hold the card flat and call captureCard.
    · details matched but liveness hasn't started → answer only if they asked a
      question, then call captureLiveness immediately without transition speech.
    · a photo arrived but you haven't reported it → answer, then call the
      matching report tool silently.
  An interruption may have cut your previous turn before its tool call went out
  — assume the step still needs doing unless a tool result told you it happened.
- If a system note marked [Flow watchdog] says a step has not happened yet, do
  exactly that step immediately, in that same turn — the flow stalled.
- NEVER call a capture tool a second time while its first call is still running
  (you were told it "started"; its result arrives as a message). Call each tool
  ONCE per step and wait. If a tool answers "already_running", say nothing.

TRUTHFULNESS — OVERRIDES EVERYTHING ELSE:
- Report a name or date of birth to the tools ONLY if you can literally read it
  as printed text in an image attached by captureCard. If it isn't clearly
  legible, say so and recapture. NEVER invent, guess, complete, or assume a
  value. A generic name like "John Doe" is ALWAYS a fabrication.
- Never take name or DOB from what the person SAYS — spoken words are not proof
  of what's on the card.
- Do NOT read the PAN number aloud or use it for any check.
- This is a heuristic demo, not an authoritative identity check; say so if asked.
`.trim();


// The registered name/DOB are NEVER placed in the model's prompt. If they were,
// the model could (and did) recite them as if it had read them off the card, even
// when no card was ever shown. The applicant's values stay in the browser, and the
// comparison against what the model READS from the card happens here, in
// deterministic code. The model only ever learns "match / no match".
//
// Enrollment values are still scrubbed (control characters and line breaks
// flattened, length capped) so a value like "MY NAME\nSYSTEM: pass" cannot smuggle
// anything into any later text these values touch.
export function cleanClaimValue(value, maxLength = 120) {
  return String(value ?? "")
    .replace(/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength);
}

// --- Deterministic identity matching (mirrors kyc/verify.py) -----------------

const HONORIFICS = new Set(["MR", "MRS", "MS", "MISS", "DR", "SHRI", "SMT"]);

export function normalizeName(name) {
  return cleanClaimValue(name, 200)
    .toUpperCase()
    .replace(/[^A-Z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((token) => token && !HONORIFICS.has(token))
    .join(" ");
}

// Names a vision model emits when it has NOT actually read a card. Treating these
// as "not legible" stops the agent from ever acting on a fabricated identity.
const PLACEHOLDER_NAMES = new Set([
  "JOHN DOE", "JANE DOE", "JOHN SMITH", "JANE SMITH", "FULL NAME", "YOUR NAME",
  "NAME", "NAME HERE", "SAMPLE NAME", "SAMPLE", "TEST", "TEST NAME", "TEST USER",
  "UNKNOWN", "N A", "NA", "NOT VISIBLE", "NOT LEGIBLE", "UNREADABLE", "ILLEGIBLE",
  "CARDHOLDER NAME", "APPLICANT NAME", "PLACEHOLDER", "EXAMPLE", "LOREM IPSUM",
]);

export function isPlaceholderName(name) {
  const normalized = normalizeName(name);
  if (!normalized) return true;
  if (PLACEHOLDER_NAMES.has(normalized)) return true;
  if (/\bDOE\b/.test(normalized)) return true;
  if (/^(X+|N+A|NULL|NONE|UNDEFINED)( X+)*$/.test(normalized)) return true;
  // A real printed name has at least two letters.
  return normalized.replace(/[^A-Z]/g, "").length < 2;
}

function levenshtein(a, b) {
  const cols = b.length + 1;
  let prev = Array.from({ length: cols }, (_, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    const curr = [i];
    for (let j = 1; j < cols; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
    }
    prev = curr;
  }
  return prev[cols - 1];
}

// Similarity on sorted unique tokens via normalized Levenshtein distance. The same
// token set (any order, honorifics/case/punctuation aside) scores 1.0.
export function nameSimilarity(a, b) {
  const setify = (value) =>
    [...new Set(normalizeName(value).split(" ").filter(Boolean))].sort().join(" ");
  const x = setify(a);
  const y = setify(b);
  if (!x || !y) return 0;
  if (x === y) return 1;
  return 1 - levenshtein(x, y) / Math.max(x.length, y.length);
}

const MONTHS = {
  JAN: 1, JANUARY: 1, FEB: 2, FEBRUARY: 2, MAR: 3, MARCH: 3, APR: 4, APRIL: 4, MAY: 5,
  JUN: 6, JUNE: 6, JUL: 7, JULY: 7, AUG: 8, AUGUST: 8, SEP: 9, SEPT: 9, SEPTEMBER: 9,
  OCT: 10, OCTOBER: 10, NOV: 11, NOVEMBER: 11, DEC: 12, DECEMBER: 12,
};

// Accept the date formats a card or the form might use; return ISO or null.
// Indian PAN cards print DD/MM/YYYY, so day-first is assumed for numeric forms.
export function normalizeDob(value) {
  const raw = cleanClaimValue(value, 40).replace(/[.,]/g, " ").replace(/\s+/g, " ").trim();
  const ymd = raw.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
  if (ymd) return isoIfValid(+ymd[1], +ymd[2], +ymd[3]);
  const dmy = raw.match(/^(\d{1,2})[/\- ](\d{1,2})[/\- ](\d{2,4})$/);
  if (dmy) {
    let year = +dmy[3];
    if (year < 100) year += year >= 70 ? 1900 : 2000;
    return isoIfValid(year, +dmy[2], +dmy[1]);
  }
  // "15 March 2005", "15-Mar-2005", "15 MAR 05"
  const textual = raw.match(/^(\d{1,2})[\s\-/]+([A-Za-z]{3,9})[\s\-/,]+(\d{2,4})$/);
  if (textual) {
    const month = MONTHS[textual[2].toUpperCase()];
    if (!month) return null;
    let year = +textual[3];
    if (year < 100) year += year >= 70 ? 1900 : 2000;
    return isoIfValid(year, month, +textual[1]);
  }
  return null;
}

function isoIfValid(year, month, day) {
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null;
  }
  const pad = (n, width = 2) => String(n).padStart(width, "0");
  return `${pad(year, 4)}-${pad(month)}-${pad(day)}`;
}

// Compare what the model READ from the card against what the applicant registered.
// The model sees only this verdict, never the registered values. A placeholder
// name counts as "nothing read".
export function compareIdentity(readValues = {}, expected = {}, { threshold = 0.82 } = {}) {
  const claimName = cleanClaimValue(expected.name, 120);
  const claimDob = cleanClaimValue(expected.dob, 40);
  const cardName = isPlaceholderName(readValues.name) ? "" : cleanClaimValue(readValues.name, 120);
  const cardDob = cleanClaimValue(readValues.dob, 40);

  if (!claimName && !claimDob) {
    return { name_match: "unclear", reason: "no registered details to compare against", name_score: 0 };
  }
  if (!cardName && !cardDob) {
    return { name_match: "unclear", reason: "no card values were read", name_score: 0 };
  }
  // A missing or placeholder name means the card wasn't actually read — that is
  // "cannot compare", not a confident mismatch.
  if (claimName && !cardName) {
    return { name_match: "unclear", reason: "no legible name was read from the card", name_score: 0 };
  }
  // Cards often print a name with different spacing than the person typed
  // ("VEER ADYANI" vs "Veeradyani"), so also compare with spaces removed and
  // take the better score. This tolerates spacing, never a different name.
  const squash = (v) => normalizeName(v).replace(/\s+/g, "");
  const nameScore = claimName && cardName
    ? Math.max(
        nameSimilarity(cardName, claimName),
        squash(cardName) && squash(cardName) === squash(claimName) ? 1 : 0,
      )
    : 0;
  const nameOk = claimName ? nameScore >= threshold : true;

  const cardDobIso = normalizeDob(cardDob);
  const claimDobIso = normalizeDob(claimDob);
  // A DOB that was read but isn't in any recognisable date format can't be
  // compared — that's "unclear", not a mismatch. A parseable DOB that differs
  // from the registered one IS a mismatch and fails.
  if (claimDobIso && cardDob && cardDobIso === null) {
    return {
      name_match: "unclear",
      reason: `date of birth read from card is not in a recognisable format (${cardDob})`,
      name_score: Math.round(nameScore * 1000) / 1000,
      name_ok: nameOk,
      dob_ok: false,
    };
  }
  const dobOk = claimDobIso ? cardDobIso !== null && cardDobIso === claimDobIso : true;
  return {
    name_match: nameOk && dobOk ? "pass" : "fail",
    name_score: Math.round(nameScore * 1000) / 1000,
    name_ok: nameOk,
    dob_ok: dobOk,
  };
}

// Port of kyc/verify.py `decide`, so the browser computes the same final verdict
// the server validates against, keeping name_match and decision consistent.
export function decideKyc(checks = {}) {
  const status = (name) => checks?.[name]?.status;
  const hardFail = ["card_read", "name_match", "face_match"];
  if (hardFail.some((name) => status(name) === "fail")) return "fail";
  const required = ["card_read", "hologram", "face_liveness", "name_match", "face_match"];
  if (required.every((name) => status(name) === "pass")) return "pass";
  return "needs_review";
}

// --- High-resolution captures -----------------------------------------------
// The live WebRTC stream is too compressed to read small card text reliably.
// The capture tools draw a card-shaped guide box over the preview, grab
// full-resolution stills straight off the local camera track (no WebRTC
// compression), crop to the box, and stream the JPEG(s) to the worker over the
// data channel in chunks. The worker attaches them to the model as images.

const CARD_ASPECT = 85.6 / 54; // ISO ID-1 card
const STILL_CHUNK_CHARS = 12_000; // stays under LiveKit's data-packet limit
const STILL_MAX_SIDE = 1600;
const CAPTURE_TIMEOUT_MS = 60_000;

// Capture UX follows the pattern the document-capture vendors use (Innovatrics /
// IDEMIA / Regula): no hidden "magic" trigger. The box continuously checks frame
// quality and gives live guidance; the card photo is taken after a VISIBLE
// "hold still" phase of fixed length with a progress bar; the hologram is a
// FIXED-LENGTH recording window ("tilt slowly... a few seconds") with a progress
// bar, recorded throughout and validated afterwards - so the box lifetime is
// predictable and the person always knows what is happening.
export const CAPTURE_VERSION = "capture-v11-narration-sync";
const DETECT_INTERVAL_MS = 250;
const DETECT_SAMPLE_WIDTH = 160;
// Card photo: a short grace so the blur of the card entering never counts, then
// the card must be present + steady for the whole HOLD window.
const CARD_GRACE_MS = 1_500;
const CARD_HOLD_MS = 1_500; // "Hold still..." progress phase before the snap
// Hologram: wait (up to 30s) for a card to be in the box, then record for a fixed
// window regardless of motion heuristics, then validate that it actually moved.
const HOLO_WAIT_FOR_CARD_MS = 30_000;
const HOLO_RECORD_MS = 3_000;
const HOLO_FRAMES = 4; // spread evenly across the recording window (fewer images = cheaper, faster)
const HOLO_MIN_MEAN_MOTION = 4; // mean inter-frame diff below this = "didn't tilt"
const HOLO_MAX_ATTEMPTS = 3;

// Liveness: a face-shaped guide; after a short grace the page records a fixed
// window while the person turns their head left, then right.
const LIVE_RECORD_MS = 4_500; // left, then right, at a relaxed pace
// How long a page narration line may take to be HEARD before the flow moves on
// anyway: it queues behind the agent's current sentence, then plays at ~11 chars/s.
const SPOKEN_ACK_BASE_MS = 6_000;
const SPOKEN_MS_PER_CHAR = 90;
const SPOKEN_ACK_TIMEOUT_MS = 20_000;
const LIVE_FRAMES = 4;
const LIVE_MIN_MEAN_MOTION = 3; // mean inter-frame diff below this = the face didn't move
const LIVE_MAX_ATTEMPTS = 3;

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

// --- Auto-capture heuristics (pure, so they are unit-testable) ---------------

// Per-pixel luminance of an RGBA buffer, as one flat array.
export function lumaGrid(rgba, pixelCount) {
  const luma = new Float32Array(pixelCount);
  for (let i = 0; i < pixelCount; i += 1) {
    const o = i * 4;
    luma[i] = 0.299 * rgba[o] + 0.587 * rgba[o + 1] + 0.114 * rgba[o + 2];
  }
  return luma;
}

// Mean absolute per-pixel difference between two same-sized luma grids.
export function frameDifference(a, b) {
  if (!a || !b || a.length !== b.length || a.length === 0) return Infinity;
  let total = 0;
  for (let i = 0; i < a.length; i += 1) total += Math.abs(a[i] - b[i]);
  return total / a.length;
}

// Mean absolute deviation from the mean — printed card text scores high, an
// empty wall or a featureless blur scores low.
export function frameContrast(luma) {
  if (!luma || luma.length === 0) return 0;
  let mean = 0;
  for (const value of luma) mean += value;
  mean /= luma.length;
  let deviation = 0;
  for (const value of luma) deviation += Math.abs(value - mean);
  return deviation / luma.length;
}

export function frameMean(luma) {
  if (!luma || luma.length === 0) return 0;
  let mean = 0;
  for (const value of luma) mean += value;
  return mean / luma.length;
}

// Fraction of neighbouring pixel pairs with a sharp luminance step. Printed text
// is dense with hard edges; a face or a wall is mostly smooth gradient. This is
// what lets auto-capture prefer a card over the person's own face in the box.
export function edgeDensity(luma, width, height, threshold = 18) {
  if (!luma || width < 2 || height < 2) return 0;
  let edges = 0;
  let pairs = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const i = y * width + x;
      if (x + 1 < width) {
        pairs += 1;
        if (Math.abs(luma[i] - luma[i + 1]) > threshold) edges += 1;
      }
      if (y + 1 < height) {
        pairs += 1;
        if (Math.abs(luma[i] - luma[i + width]) > threshold) edges += 1;
      }
    }
  }
  return pairs ? edges / pairs : 0;
}

// The box is "satisfied" when something new occupies it (differs from the
// baseline captured at overlay open), it carries printed detail, and it is
// holding roughly still between samples. `edges` and `meanLuma`, when supplied,
// additionally require text-like edge density and a light (card-like) field so a
// steady face or dark background doesn't qualify.
export function cardFrameReady({ baselineDiff, interframeDiff, contrast, edges, meanLuma }) {
  const textLike = edges === undefined || edges > 0.06;
  const cardBright = meanLuma === undefined || meanLuma > 90;
  return baselineDiff > 14 && interframeDiff < 10 && contrast > 10 && textLike && cardBright;
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

function buildCaptureOverlay(video, boxW, boxH, { caption: captionText, shape = "card" }) {
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
  caption.textContent = captionText;
  caption.style.cssText =
    "position:relative; z-index:1; margin:0; color:#fff; font-weight:600; " +
    "font-size:.95rem; text-align:center; text-shadow:0 1px 6px rgba(0,0,0,.6); padding:0 1rem;";
  const box = doc.createElement("div");
  box.style.cssText =
    `width:${boxW}px; height:${boxH}px; border:3px solid #2dd4bf; border-radius:${shape === "oval" ? "50%" : "14px"}; ` +
    "box-shadow:0 0 0 200vmax rgba(8,15,26,.6); flex:0 0 auto; transition:border-color .2s;";
  // No shutter button: the shot fires automatically. A quiet Cancel is the only
  // control, as an escape hatch if the person needs to stop.
  const cancel = doc.createElement("button");
  cancel.type = "button";
  cancel.textContent = "Cancel";
  cancel.style.cssText =
    "position:relative; z-index:1; border:0; border-radius:999px; padding:.5rem 1rem; " +
    "font-weight:600; cursor:pointer; background:rgba(255,255,255,.16); color:#fff; font-size:.85rem;";
  overlay.append(caption, box, cancel);
  wrap.append(overlay);
  const setDetected = (on) => { box.style.borderColor = on ? "#4ade80" : "#2dd4bf"; };
  return { overlay, caption, cancel, defaultCaption: captionText, setDetected };
}

// Sample the guide-box region of the live video as a small luma grid.
function makeSampler(video, rect) {
  const doc = video.ownerDocument;
  const sample = doc.createElement("canvas");
  sample.width = DETECT_SAMPLE_WIDTH;
  sample.height = Math.max(2, Math.round(DETECT_SAMPLE_WIDTH / CARD_ASPECT));
  const ctx = sample.getContext("2d", { willReadFrequently: true });
  return {
    width: sample.width,
    height: sample.height,
    read() {
      if (!video.videoWidth || !ctx) return null;
      ctx.drawImage(video, rect.x, rect.y, rect.w, rect.h, 0, 0, sample.width, sample.height);
      const pixels = ctx.getImageData(0, 0, sample.width, sample.height).data;
      return lumaGrid(pixels, sample.width * sample.height);
    },
  };
}

// Grab a full-resolution still of the box region and stream it to the worker.
async function sendStill(video, rect, sendData, prefix) {
  const scaleOut = Math.min(1, STILL_MAX_SIDE / Math.max(rect.w, rect.h));
  const canvas = video.ownerDocument.createElement("canvas");
  canvas.width = Math.round(rect.w * scaleOut);
  canvas.height = Math.round(rect.h * scaleOut);
  canvas
    .getContext("2d")
    .drawImage(video, rect.x, rect.y, rect.w, rect.h, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
  const base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
  const stillId = `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  const chunks = chunkString(base64, STILL_CHUNK_CHARS);
  for (let seq = 0; seq < chunks.length; seq += 1) {
    await sendData({ type: "still", id: stillId, seq, total: chunks.length, data: chunks[seq] });
  }
  return { stillId, width: canvas.width, height: canvas.height, chunks: chunks.length };
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Narration the page asks the agent to speak is queued behind whatever the agent is
// already saying, so a line is HEARD many seconds after it is REQUESTED. A capture
// step that started its timer on the request ran ahead of the person - seen live:
// the liveness recording had finished before "look at the camera" even played.
// speak() therefore resolves only when the worker confirms the line has been heard
// (a "spoken" data message carrying the id), with a generous timeout so a lost ack
// can never stall the flow. Always resolves, never throws:
//   "spoken" heard · "sent" (wait:false) · "timeout" no confirmation · "unsent" channel failed
export function createNarrator({ ackTimeoutMs = SPOKEN_ACK_TIMEOUT_MS } = {}) {
  const pending = new Map();
  let counter = 0;
  const finish = (id, how) => {
    const entry = pending.get(id);
    if (!entry) return false;
    pending.delete(id);
    clearTimeout(entry.timer);
    entry.resolve(how);
    return true;
  };
  return {
    // Returns true when the event was a "spoken" ack this narrator was waiting on.
    onEvent(event) {
      if (event?.type !== "spoken") return false;
      return finish(String(event.id ?? ""), "spoken");
    },
    speak(sendData, text, { wait = true } = {}) {
      const id = `n${Date.now().toString(36)}-${(counter += 1)}`;
      return new Promise((resolve) => {
        const budget = Math.min(ackTimeoutMs, SPOKEN_ACK_BASE_MS + String(text).length * SPOKEN_MS_PER_CHAR);
        pending.set(id, { resolve, timer: setTimeout(() => finish(id, "timeout"), budget) });
        Promise.resolve()
          .then(() => sendData({ type: "speak", id, text }))
          .then(() => { if (!wait) finish(id, "sent"); }, () => finish(id, "unsent"));
      });
    },
    get pendingCount() { return pending.size; },
  };
}

// A thin progress bar under the caption, shown during the timed phases so the
// person can SEE how long to hold / tilt (the vendor pattern).
function addProgress(ui) {
  const doc = ui.overlay.ownerDocument;
  const track = doc.createElement("div");
  track.style.cssText =
    "position:relative; z-index:1; width:min(60%, 320px); height:6px; border-radius:999px; " +
    "background:rgba(255,255,255,.22); overflow:hidden; margin-top:-.2rem;";
  const fill = doc.createElement("div");
  fill.style.cssText = "height:100%; width:0%; background:#4ade80; transition:width .2s linear;";
  track.append(fill);
  ui.overlay.insertBefore(track, ui.cancel);
  return {
    set(fraction) { fill.style.width = `${Math.max(0, Math.min(1, fraction)) * 100}%`; },
    hide() { track.hidden = true; },
    show() { track.hidden = false; },
  };
}

// --- Document detection (pure, unit-tested) ---------------------------------
// The old "is a card in the box" check only looked at brightness/contrast/edge
// statistics INSIDE the box - a bright, textured face-and-room passes all of
// those, so both boxes fired with no card at all. A real document detector
// (what the capture SDKs do) looks for a light RECTANGLE whose edges line up with
// the guide box: a strong luminance step from just inside the box edge to just
// outside it on at least three sides, a fairly uniform interior (a card is one
// flat object; a face-and-wall is not), and fine printed detail inside.
//
// `luma` covers an EXPANDED crop around the box; the box occupies the centred
// fraction (fx, fy) of it. Returns { present, sides, spread, mean, edges }.
export function documentPresent(luma, width, height, fx, fy, {
  sideStep = 16, minSides = 3, maxSpread = 70, minMean = 90, minEdges = 0.035,
  // Alternate path: only 2 clean edges (light background, imperfect fit) but an
  // interior that is unmistakably a printed card - bright, flat, dense print.
  altSides = 2, altEdges = 0.09, altMean = 110, altSpread = 70,
} = {}) {
  if (!luma || width < 8 || height < 8) return { present: false, sides: 0, spread: 0, mean: 0, edges: 0 };
  const bx0 = Math.round(((1 - fx) / 2) * width);
  const bx1 = Math.round(((1 + fx) / 2) * width);
  const by0 = Math.round(((1 - fy) / 2) * height);
  const by1 = Math.round(((1 + fy) / 2) * height);
  const tx = Math.max(2, Math.round(0.05 * width));
  const ty = Math.max(2, Math.round(0.07 * height));
  const meanOf = (x0, x1, y0, y1) => {
    let total = 0;
    let n = 0;
    for (let y = Math.max(0, y0); y < Math.min(height, y1); y += 1) {
      for (let x = Math.max(0, x0); x < Math.min(width, x1); x += 1) { total += luma[y * width + x]; n += 1; }
    }
    return n ? total / n : NaN;
  };
  // A card never fits the guide box edge-for-edge, so look for the card's edge
  // anywhere in a band around each box edge: the strongest inside-vs-outside
  // step over a few boundary offsets is the edge evidence for that side.
  const bestStep = (measure) => {
    let best = 0;
    for (const d of [-2, -1, 0, 1, 2]) {
      const v = measure(d);
      if (Number.isFinite(v) && v > best) best = v;
    }
    return best;
  };
  // Each side is measurable if at least its base offset fits in the crop;
  // individual offsets that would fall outside are skipped (NaN).
  const steps = [];
  if (bx0 - tx >= 0) steps.push(bestStep((d) => { const b = bx0 + d * Math.round(tx / 2); if (b - tx < 0 || b + tx > width) return NaN; return Math.abs(meanOf(b, b + tx, by0 + ty, by1 - ty) - meanOf(b - tx, b, by0 + ty, by1 - ty)); }));
  if (bx1 + tx <= width) steps.push(bestStep((d) => { const b = bx1 + d * Math.round(tx / 2); if (b - tx < 0 || b + tx > width) return NaN; return Math.abs(meanOf(b - tx, b, by0 + ty, by1 - ty) - meanOf(b, b + tx, by0 + ty, by1 - ty)); }));
  if (by0 - ty >= 0) steps.push(bestStep((d) => { const b = by0 + d * Math.round(ty / 2); if (b - ty < 0 || b + ty > height) return NaN; return Math.abs(meanOf(bx0 + tx, bx1 - tx, b, b + ty) - meanOf(bx0 + tx, bx1 - tx, b - ty, b)); }));
  if (by1 + ty <= height) steps.push(bestStep((d) => { const b = by1 + d * Math.round(ty / 2); if (b - ty < 0 || b + ty > height) return NaN; return Math.abs(meanOf(bx0 + tx, bx1 - tx, b - ty, b) - meanOf(bx0 + tx, bx1 - tx, b, b + ty)); }));
  const sides = steps.filter((d) => d > sideStep).length;
  const needSides = Math.min(minSides, Math.max(2, steps.length));
  // Interior: block means (one flat object?) + overall brightness + printed detail.
  const ix0 = bx0 + tx, ix1 = bx1 - tx, iy0 = by0 + ty, iy1 = by1 - ty;
  const iw = ix1 - ix0, ih = iy1 - iy0;
  if (iw < 4 || ih < 4) return { present: false, sides, spread: 0, mean: 0, edges: 0 };
  const blocks = [];
  for (let r = 0; r < 3; r += 1) {
    for (let c = 0; c < 4; c += 1) {
      blocks.push(meanOf(ix0 + Math.floor((c * iw) / 4), ix0 + Math.floor(((c + 1) * iw) / 4), iy0 + Math.floor((r * ih) / 3), iy0 + Math.floor(((r + 1) * ih) / 3)));
    }
  }
  const spread = Math.max(...blocks) - Math.min(...blocks);
  const mean = meanOf(ix0, ix1, iy0, iy1);
  const interior = new Float32Array(iw * ih);
  for (let y = 0; y < ih; y += 1) for (let x = 0; x < iw; x += 1) interior[y * iw + x] = luma[(iy0 + y) * width + (ix0 + x)];
  const edges = edgeDensity(interior, iw, ih);
  const byEdges = sides >= needSides && spread < maxSpread && mean > minMean && edges > minEdges;
  const byPrint = sides >= altSides && spread < altSpread && mean > altMean && edges > altEdges;
  const present = byEdges || byPrint;
  return { present, sides, spread: Math.round(spread), mean: Math.round(mean), edges: Math.round(edges * 1000) / 1000, path: byEdges ? "edges" : byPrint ? "print" : "none" };
}

// Expand the box crop so the detector can see just outside the card's edges.
function expandRect(rect, video, factor = 1.25) {
  const w = Math.min(video.videoWidth, rect.w * factor);
  const h = Math.min(video.videoHeight, rect.h * factor);
  const x = Math.max(0, Math.min(video.videoWidth - w, rect.x - (w - rect.w) / 2));
  const y = Math.max(0, Math.min(video.videoHeight - h, rect.y - (h - rect.h) / 2));
  return { x, y, w, h, fx: rect.w / w, fy: rect.h / h };
}

function makeDocSampler(video, rect) {
  const outer = expandRect(rect, video);
  const sampler = makeSampler(video, outer);
  return {
    ...sampler,
    fx: outer.fx,
    fy: outer.fy,
    detect() {
      const luma = sampler.read();
      if (!luma) return null;
      return { luma, ...documentPresent(luma, sampler.width, sampler.height, outer.fx, outer.fy) };
    },
  };
}

// Hologram step: guided, fixed-length tilt recording.
//   1) wait for a card to be in the box (live guidance),
//   2) record for HOLO_RECORD_MS with a progress bar while they tilt,
//   3) validate that the card actually moved during the window.
async function captureHologramBurst({ video, sendData, voice } = {}) {
  const startedAt = Date.now();
  const done = (result) => ({ ...result, elapsed_ms: Date.now() - startedAt, capture_version: CAPTURE_VERSION });
  if (!video || !video.videoWidth) return done({ captured: false, reason: "no_camera_frame" });
  let ui = null;
  const cleanups = [];
  try {
    await nextLayout(video.ownerDocument?.defaultView);
    const rect = cardCropRect(video.clientWidth, video.clientHeight, video.videoWidth, video.videoHeight);
    ui = buildCaptureOverlay(video, rect.boxW, rect.boxH, {
      caption: "Hold your PAN card in the box, hologram side facing the camera",
    });
    const progress = addProgress(ui);
    progress.hide();
    const speak = (text, opts) => (voice ? voice.speak(sendData, text, opts) : sendData({ type: "speak", text }).catch(() => {}));
    await speak("Put your PAN card in the box, hologram side to the camera.");
    const sampler = makeDocSampler(video, rect);
    let lastDetect = null;

    // Phase 1: wait for a DOCUMENT to fill the box (3 consecutive detections,
    // reasonably steady) - a face or a room can no longer pass.
    const positioned = await new Promise((resolve) => {
      const timer = setTimeout(() => resolve(false), HOLO_WAIT_FOR_CARD_MS);
      cleanups.push(() => clearTimeout(timer));
      ui.cancel.onclick = () => resolve("cancelled");
      let good = 0;
      let previous = null;
      const detector = setInterval(() => {
        try {
          const d = sampler.detect();
          if (!d) return;
          lastDetect = d;
          const steady = previous ? frameDifference(d.luma, previous) < 18 : false;
          previous = d.luma;
          if (d.present && steady) {
            good += 1;
            ui.setDetected(true);
            ui.caption.textContent = "Card found - get ready to tilt...";
            if (good >= 2) resolve(true);
          } else {
            good = 0;
            ui.setDetected(false);
            ui.caption.textContent = d.present
              ? "Hold the card still for a moment..."
              : "Fit your PAN card inside the box, hologram side facing the camera";
          }
        } catch { /* a bad sample must never kill the tool */ }
      }, DETECT_INTERVAL_MS);
      cleanups.push(() => clearInterval(detector));
    });
    for (const cleanup of cleanups.splice(0)) cleanup();
    if (positioned === "cancelled") return done({ captured: false, reason: "cancelled" });
    if (!positioned) return done({ captured: false, reason: "timeout", detail: "no card was placed in the box", last_detect: lastDetect && { sides: lastDetect.sides, spread: lastDetect.spread, mean: lastDetect.mean, edges: lastDetect.edges } });

    // Phase 2: fixed recording window with a progress bar; capture frames evenly.
    // Heard first, THEN the recording window opens - otherwise the frames were
    // taken while the person was still listening to the instruction.
    await speak("Now tilt it slowly side to side.");
    progress.show();
    ui.caption.textContent = "Tilt slowly side to side, a good way each time - keep going...";
    const stillIds = [];
    const motion = [];
    let previous = null;
    const recordStart = Date.now();
    const gap = HOLO_RECORD_MS / HOLO_FRAMES;
    let cancelled = false;
    ui.cancel.onclick = () => { cancelled = true; };
    for (let i = 0; i < HOLO_FRAMES && !cancelled; i += 1) {
      try {
        const luma = sampler.read();
        if (luma) {
          if (previous) motion.push(frameDifference(luma, previous));
          previous = luma;
        }
        const still = await sendStill(video, rect, sendData, "holo");
        stillIds.push(still.stillId);
      } catch { /* keep recording; a failed frame is skipped */ }
      progress.set((Date.now() - recordStart) / HOLO_RECORD_MS);
      const target = recordStart + gap * (i + 1);
      const wait = target - Date.now();
      if (wait > 0) await sleep(wait);
    }
    progress.set(1);
    if (cancelled) return done({ captured: false, reason: "cancelled" });
    const meanMotion = motion.length ? motion.reduce((x, y) => x + y, 0) / motion.length : 0;
    if (meanMotion < HOLO_MIN_MEAN_MOTION || stillIds.length < 3) {
      ui.caption.textContent = "I didn't see the card move";
      return done({
        captured: false,
        reason: "no_tilt",
        detail: `mean motion ${meanMotion.toFixed(1)} over ${stillIds.length} frames`,
        frames_discarded: stillIds.length,
      });
    }
    ui.caption.textContent = "Got it!";
    await speak("Got it - one moment.", { wait: false });
    return done({ captured: true, still_ids: stillIds, frames: stillIds.length, mean_motion: Math.round(meanMotion * 10) / 10 });
  } catch (error) {
    return done({ captured: false, reason: "error", error: error instanceof Error ? error.message : String(error) });
  } finally {
    for (const cleanup of cleanups.splice(0)) cleanup();
    ui?.overlay.remove();
  }
}

// Card step: guided auto-capture - live guidance until the card is in the box
// and steady, then a visible "Hold still" progress phase, then the snap.
async function captureCardStill({ video, sendData, voice } = {}) {
  const startedAt = Date.now();
  const done = (result) => ({ ...result, elapsed_ms: Date.now() - startedAt, capture_version: CAPTURE_VERSION });
  if (!video || !video.videoWidth) return done({ captured: false, reason: "no_camera_frame" });
  let ui = null;
  const cleanups = [];
  try {
    await nextLayout(video.ownerDocument?.defaultView);
    const rect = cardCropRect(video.clientWidth, video.clientHeight, video.videoWidth, video.videoHeight);
    ui = buildCaptureOverlay(video, rect.boxW, rect.boxH, {
      caption: "Hold the card flat and still, front facing the camera",
    });
    const progress = addProgress(ui);
    progress.hide();
    const speak = (text, opts) => (voice ? voice.speak(sendData, text, opts) : sendData({ type: "speak", text }).catch(() => {}));
    await speak("Now the front: hold it flat and still in the box.");
    const sampler = makeDocSampler(video, rect);
    const action = await new Promise((resolve) => {
      const openedAt = Date.now();
      const overallTimer = setTimeout(() => resolve("timeout"), CAPTURE_TIMEOUT_MS);
      cleanups.push(() => clearTimeout(overallTimer));
      ui.cancel.onclick = () => resolve("cancelled");
      let previous = null;
      let holdStart = null;
      const detector = setInterval(() => {
        try {
          const d = sampler.detect();
          if (!d) return;
          if (previous === null) { previous = d.luma; return; }
          const interframe = frameDifference(d.luma, previous);
          previous = d.luma;
          const armed = Date.now() - openedAt >= CARD_GRACE_MS;
          const present = d.present;
          const steady = interframe < 10;
          if (!armed || !present) {
            holdStart = null;
            progress.hide();
            ui.setDetected(false);
            ui.caption.textContent = present
              ? "Hold the card flat and still..."
              : "Fit your PAN card inside the box, front facing the camera";
            return;
          }
          if (!steady) {
            holdStart = null;
            progress.set(0);
            ui.setDetected(false);
            ui.caption.textContent = "Hold still...";
            return;
          }
          // Present + steady: the visible hold phase.
          if (holdStart === null) holdStart = Date.now();
          progress.show();
          ui.setDetected(true);
          const fraction = (Date.now() - holdStart) / CARD_HOLD_MS;
          progress.set(fraction);
          ui.caption.textContent = "Hold still - capturing...";
          if (fraction >= 1) resolve("capture");
        } catch { /* a bad sample must never kill the tool */ }
      }, DETECT_INTERVAL_MS);
      cleanups.push(() => clearInterval(detector));
    });
    for (const cleanup of cleanups.splice(0)) cleanup();
    if (action !== "capture") return done({ captured: false, reason: action });
    progress.set(1);
    ui.caption.textContent = "Captured!";
    // Honest: the read + comparison happen right after this, in one go.
    await speak("Got it - one moment while I check it.", { wait: false });
    const still = await sendStill(video, rect, sendData, "card");
    return done({
      captured: true,
      still_id: still.stillId,
      width: still.width,
      height: still.height,
      chunks_sent: still.chunks,
    });
  } catch (error) {
    return done({ captured: false, reason: "error", error: error instanceof Error ? error.message : String(error) });
  } finally {
    for (const cleanup of cleanups.splice(0)) cleanup();
    ui?.overlay.remove();
  }
}


// Liveness step: a face-shaped guide over the live video. After a short grace the
// page records a fixed window while the person turns their head left, then right,
// and captures a few frames spread across it. Motion is measured so a frozen
// face (or a photo held up) is caught on the client before the model even looks.
function faceRect(video) {
  const scale = Math.max(video.clientWidth / video.videoWidth, video.clientHeight / video.videoHeight);
  const boxW = video.clientWidth * 0.42;
  const boxH = Math.min(video.clientHeight * 0.82, boxW * 1.3);
  const w = Math.min(video.videoWidth, boxW / scale);
  const h = Math.min(video.videoHeight, boxH / scale);
  return { x: (video.videoWidth - w) / 2, y: (video.videoHeight - h) / 2, w, h, boxW, boxH };
}

// Liveness step. Like the hologram and card steps: the page instructs FIRST and
// the check runs silently afterwards. Each spoken line is awaited until it has
// actually been HEARD (see createNarrator) - the recording never starts while the
// person is still listening to what they're supposed to do.
async function captureLivenessBurst({ video, sendData, voice } = {}) {
  if (!video || !video.videoWidth) return { captured: false, reason: "no_camera_frame" };
  await nextLayout(video.ownerDocument?.defaultView);
  const rect = faceRect(video);
  const ui = buildCaptureOverlay(video, rect.boxW, rect.boxH, {
    caption: "Keep your face inside the oval and listen",
    shape: "oval",
  });
  const speak = (text, opts) => (voice ? voice.speak(sendData, text, opts) : sendData({ type: "speak", text }).catch(() => {}));
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  let cancelled = false;
  ui.cancel.onclick = () => { cancelled = true; };
  const done = (result) => { ui.overlay.remove(); return result; };
  try {
    await speak(LIVENESS_INSTRUCTION);
    if (cancelled) return done({ captured: false, reason: "cancelled" });
    const progress = addProgress(ui);
    progress.show();
    ui.caption.textContent = "Turn slowly left... then right...";
    const sampler = makeSampler(video, rect);
    const stillIds = [];
    const motions = [];
    let previous = sampler.read();
    const recordStart = Date.now();
    const gap = LIVE_RECORD_MS / LIVE_FRAMES;
    for (let i = 0; i < LIVE_FRAMES && !cancelled; i += 1) {
      const target = recordStart + Math.round(gap * (i + 0.5));
      while (Date.now() < target && !cancelled) {
        await wait(120);
        const luma = sampler.read();
        if (luma && previous) motions.push(frameDifference(luma, previous));
        if (luma) previous = luma;
      }
      if (cancelled) break;
      const still = await sendStill(video, rect, sendData, "live");
      stillIds.push(still.stillId);
      progress.set((i + 1) / LIVE_FRAMES);
    }
    if (cancelled) return done({ captured: false, reason: "cancelled" });
    const meanMotion = motions.length ? motions.reduce((a, b) => a + b, 0) / motions.length : 0;
    ui.caption.textContent = "Got it!";
    if (meanMotion < LIVE_MIN_MEAN_MOTION) {
      return done({ captured: false, reason: "no_motion", mean_motion: Math.round(meanMotion * 10) / 10, frames: stillIds.length });
    }
    return done({ captured: true, still_ids: stillIds, frames: stillIds.length, mean_motion: Math.round(meanMotion * 10) / 10 });
  } catch (error) {
    return done({ captured: false, reason: "error", error: error instanceof Error ? error.message : String(error) });
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

// The model reports only the check it actually performs (card_read). name_match
// is computed in code, and the checks not run in this flow are filled in by the
// client before the result is stored.
const RESULT_SCHEMA = {
  type: "object",
  properties: {
    decision: { type: "string", enum: ["pass", "fail", "needs_review"] },
    checks: {
      type: "object",
      properties: { card_read: CHECK_SCHEMA },
      required: ["card_read"],
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

// Checks deliberately disabled in this flow. They are recorded as passing with
// ZERO confidence and an explicit "not checked" reason so the final decision is
// driven only by the hologram, the card read and the details match, while the
// stored record stays honest about what was and wasn't verified.
export const SKIPPED_CHECKS = ["face_match"];
const skippedCheck = () => ({
  status: "pass",
  confidence: 0,
  reasons: ["not checked — disabled in this simplified flow"],
});


export const KYC_STEP_IDS = ["hologram", "card", "match", "liveness"];

// Wording for the final spoken verdict. It names WHICH field mismatched but never
// the values — the agent is forbidden from speaking the name or date of birth.
export function verdictLine(decision, verdict) {
  if (decision === "pass") {
    return "the hologram checked out, the name and date of birth on the card match what they entered, and the liveness check passed, so they're verified";
  }
  if (decision === "fail") {
    const nameBad = verdict?.name_ok === false;
    const dobBad = verdict?.dob_ok === false;
    const which = nameBad && dobBad
      ? "both the name and the date of birth on the card do NOT match what they entered"
      : nameBad
        ? "the name on the card does NOT match what they entered (the date of birth does)"
        : "the date of birth on the card does NOT match what they entered (the name does)";
    return `${which}, so you cannot verify them and have to end the call here`;
  }
  return "the card details couldn't be read well enough to compare, so the verification can't be completed today and you have to end the call here";
}

const END_INSTRUCTION = (decision, line) =>
  `THE CHECK IS DONE — decision: ${decision}. THIS IS THE END OF THE VERIFICATION. Do not call ` +
  `any other tool after this turn. Begin with "I've checked your card against the details you ` +
  `entered" and in two or three plain, kind sentences state the RESULT as a fact: ${line}. Then ` +
  `say goodbye. NEVER say the name or the date of birth themselves — not from the card, not what ` +
  `they entered. Be honest and direct: never say "let me check", "I'll look into it", "I'll flag ` +
  `this", "our team will review" or "I'll get back to you" — the checking is finished and the ` +
  `answer is final. Do NOT offer further steps or ask if they have questions — the call ends ` +
  `automatically when you finish speaking.`;

export function createKycConfig({
  fetch: fetchImpl = globalThis.fetch,
  onResult = () => {},
  onStep = () => {},
  expected = {},
  // Initial flow state — lets a host resume a session, and lets tests reach the
  // later steps without a camera.
  flowState = {},
  // Data-channel sender available before any tool has run (the host passes the
  // agent's bridge). Tools also receive one per call; the latest wins.
  sendData = null,
  // Watchdog delays (ms); tests shrink them.
  watchdog = {},
} = {}) {
  let sessionId = "";
  // The flow is enforced here, not merely requested in the prompt: each step's
  // tool refuses until the previous step is complete, so the model cannot open
  // a box before consent, snap the card before the hologram is confirmed, or act
  // on a card it never legibly read.
  const flow = {
    confirmed: false,
    hologramCaptured: false, // a tilt burst from the CURRENT attempt is attached
    hologram: null, // "pass" once confirmed; "unclear" if given up
    holoAttempts: 0,
    holoSeen: "",
    match: null, // "pass" once the card details matched (gates liveness)
    matchVerdict: null,
    livenessCaptured: false,
    liveness: null, // "pass" once the head turn was confirmed; "unclear" if given up
    liveAttempts: 0,
    liveSeen: "",
    cardCaptured: false,
    cardRead: null,
    cardAttempts: 0,
    result: null,
    ...flowState,
  };
  // Single-flight: the model (Gemini especially) re-issues a capture call while the
  // previous one is still running - three boxes opened in six seconds, each speaking
  // its line, so the person heard the same sentences over and over. A duplicate call
  // is refused instantly and told to wait silently for the running one's result.
  const inFlight = new Set();
  const busy = (tool) => ({
    captured: false,
    reason: "already_running",
    say_next:
      `${tool} is ALREADY running from your previous call and its result will arrive as a ` +
      "message. Do NOT call it again. Say nothing and wait for that result.",
  });
  const step = (id, state) => { try { onStep(id, state); } catch { /* UI only */ } };

  // --- Flow watchdog: the flow self-heals when the model stalls ------------
  // A barge-in can cut the model's turn before it emits the next tool call. The
  // page knows exactly which tool should come next and when it hasn't, so after
  // a generous pause it sends the worker a "nudge": a system note that re-runs
  // the model with the precise instruction. Timers are armed only BETWEEN steps —
  // never while a box is open.
  const WD = {
    confirm: 25_000, // no "yes" yet → ask again (repeats a few times)
    holo: 6_000, // confirmed, but captureHologram not called
    holoReport: 12_000, // tilt burst captured, but reportHologram not called
    holoRetry: 25_000, // hologram not seen; waiting on the person's yes/no to retry
    liveness: 6_000, // details matched, but captureLiveness not called
    liveReport: 12_000, // liveness frames captured, but reportLiveness not called
    liveRetry: 25_000, // liveness not confirmed; waiting on the person's yes/no to retry
    capture: 6_000, // hologram confirmed, but captureCard not called
    report: 12_000, // photo captured, but reportCardRead not called
    recapture: 10_000, // photo not legible, but captureCard not re-called
    ...watchdog,
  };
  let lastSendData = typeof sendData === "function" ? sendData : null;
  const pending = new Map(); // step -> timer
  const nudge = async (text) => {
    if (!lastSendData || flow.result) return;
    try { await lastSendData({ type: "nudge", text: `[Flow watchdog] ${text}` }); } catch { /* best-effort */ }
  };
  const satisfied = (key) => {
    const timer = pending.get(key);
    if (timer) clearTimeout(timer);
    pending.delete(key);
  };
  const expectNext = (key, ms, text, { repeat = 0 } = {}) => {
    satisfied(key);
    const timer = setTimeout(() => {
      pending.delete(key);
      // Re-arm BEFORE the (async) nudge so a satisfied() that lands while the
      // nudge is in flight cancels the repeat instead of racing it.
      if (repeat > 0) expectNext(key, ms, text, { repeat: repeat - 1 });
      void nudge(text);
    }, ms);
    pending.set(key, timer);
  };
  const clearAllWatchdogs = () => { for (const key of [...pending.keys()]) satisfied(key); };
  const useContext = (context) => { if (typeof context?.sendData === "function") lastSendData = context.sendData; };
  // One narrator per session: capture helpers speak through it so each instruction
  // is confirmed HEARD before the step that depends on it begins.
  const narrator = createNarrator();
  const withVoice = (context) => ({ ...(context ?? {}), voice: narrator });

  // The stored result is shown on screen only when the agent actually starts
  // speaking the verdict (the worker sends "verdict_spoken" at that instant), so
  // the person never reads FAIL/PASS while the voice is still mid-sentence.
  // call_ended / ended are backstops, plus a timer in case no signal comes.
  let revealed = false;
  let revealTimer = null;
  const revealResult = () => {
    if (revealed || !flow.result) return;
    revealed = true;
    clearTimeout(revealTimer);
    onResult(flow.result);
  };

  // Build, store and (later) render the final result. Everything about identity
  // is authoritative from CODE, never from the model's say-so: extracted values
  // are the ones reportCardRead accepted (falling back to the model's, minus
  // placeholders); name_match is recomputed against the registered claim; the
  // hologram check comes from the flow state; the checks not run are filled in
  // explicitly; and the decision is recomputed the same way the server will.
  // Idempotent: the first call wins. Returns the stored result plus the verdict.
  async function finalize(modelResult, sendData) {
    if (flow.result) return { result: flow.result, verdict: flow.verdict };
    if (!sessionId) throw new Error("Session ID is not available yet");
    const extracted = flow.cardRead ?? {
      name: isPlaceholderName(modelResult?.extracted?.name) ? "" : cleanClaimValue(modelResult?.extracted?.name, 120),
      dob: cleanClaimValue(modelResult?.extracted?.dob, 40),
    };
    const verdict = compareIdentity(extracted, expected);
    const cardRead = modelResult?.checks?.card_read ?? (
      flow.cardRead
        ? { status: "pass", confidence: 0.9, reasons: ["legible PAN card photo; name and date of birth read"] }
        : { status: "unclear", confidence: 0, reasons: ["no legible card read was reported"] }
    );
    const checks = {
      card_read: cardRead,
      name_match: {
        status: verdict.name_match,
        confidence: verdict.name_match === "unclear" ? 0 : 0.9,
        reasons: [
          verdict.reason
            ? verdict.reason
            : `name/DOB read from card ${verdict.name_match === "pass" ? "matched" : "did not match"} the registered details (name score ${verdict.name_score})`,
        ],
      },
      // The hologram is a real, gating check: confirmed → pass; given up after
      // attempts → unclear (heuristic — "couldn't confirm" is not "fake"), which
      // blocks a pass and routes to "can't complete today". Never reached → unclear.
      hologram:
        flow.hologram === "pass"
          ? { status: "pass", confidence: 0.8, reasons: [flow.holoSeen || "hologram shine shifted across the tilt frames"] }
          : {
              status: "unclear",
              confidence: 0,
              reasons: [
                flow.holoAttempts > 0
                  ? `hologram could not be confirmed on camera after ${flow.holoAttempts} attempt(s)${flow.holoSeen ? `: ${flow.holoSeen}` : ""}`
                  : "hologram check was not reached",
              ],
            },
    };
    // Liveness is a real, gating check: confirmed → pass; given up → unclear (blocks a
    // pass, routes to "can't complete today"); not reached (details failed) → unclear.
    checks.face_liveness =
      flow.liveness === "pass"
        ? { status: "pass", confidence: 0.8, reasons: [flow.liveSeen || "head turned left and right on camera"] }
        : {
            status: "unclear",
            confidence: 0,
            reasons: [
              flow.liveAttempts > 0
                ? `liveness could not be confirmed after ${flow.liveAttempts} attempt(s)${flow.liveSeen ? `: ${flow.liveSeen}` : ""}`
                : "liveness check was not reached",
            ],
          };
    for (const name of SKIPPED_CHECKS) checks[name] = skippedCheck();
    const normalizedResult = {
      ...(modelResult ?? {}),
      extracted,
      checks,
      decision: decideKyc(checks),
      notes: [modelResult?.notes, "Simplified flow: liveness and face match were not checked."]
        .filter(Boolean)
        .join(" "),
      session_id: sessionId,
    };
    const response = await fetchImpl("/kyc-result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(normalizedResult),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.message ?? "Could not store KYC result");
    flow.result = normalizedResult;
    flow.verdict = verdict;
    clearAllWatchdogs();
    step("card", "done");
    step("match", "done");
    revealTimer = setTimeout(revealResult, 20_000);
    // The verification is over. Ask the worker to end the call once the agent has
    // finished speaking its verdict; the page hangs up when it confirms.
    if (typeof sendData === "function") {
      try { await sendData({ type: "end_call" }); } catch { /* best-effort; page has a fallback timer */ }
    }
    return { result: normalizedResult, verdict };
  }

  return {
    session: "/session",
    vision: true,
    // The registered identity is NOT appended to the prompt — see compareIdentity.
    prompt: KYC_PROMPT,
    // Idle sampling stays light at 2fps; single-frame card reads stay full-res.
    // `greeting` is spoken verbatim by the worker the moment the person joins.
    options: {
      max_fps: 2,
      burst_fps: 10,
      burst_count: 8,
      burst_window_ms: 2500,
      max_frames_per_min: 60,
      greeting: KYC_GREETING,
      force_tone: "neutral",
      client_version: CAPTURE_VERSION,
    },
    onEvent(event) {
      if (narrator.onEvent(event)) return;
      if (event?.type === "session_started") {
        sessionId = event.room;
        if (!flow.confirmed) {
          expectNext(
            "confirm",
            WD.confirm,
            "The person has not yet said they're ready to begin. In ONE warm sentence, ask again " +
              "whether they'd like to start (they just need to say yes). Do not repeat the full greeting.",
            { repeat: 2 },
          );
        }
      }
      if (event?.type === "verdict_spoken" || event?.type === "call_ended") revealResult();
      if (event?.type === "ended") {
        clearAllWatchdogs();
        revealResult();
      }
    },
    tools: {
      confirmStart: {
        description:
          "Call this the moment the person clearly agrees to begin the verification (yes / " +
          "okay / let's go). It unlocks the hologram step. Do not call it before they have agreed.",
        parameters: {},
        async handler(_args, context) {
          useContext(context);
          flow.confirmed = true;
          satisfied("confirm");
          step("hologram", "active");
          expectNext(
            "holo",
            WD.holo,
            "The person confirmed but the hologram box has NOT been shown yet. Say the box is appearing " +
              "and to tilt the card slowly, then call captureHologram now, in this turn.",
            { repeat: 1 },
          );
          return {
            ok: true,
            say_next:
              "Say ONE short sentence - 'Great, the box is coming up now' - and call captureHologram " +
              "in the same turn. The page itself tells them where to put the card and when to tilt; " +
              "do not explain the steps.",
          };
        },
      },
      captureHologram: {
        description:
          "Show the card box and automatically record a short burst of photos while the person " +
          "tilts the card, so the hologram's shine can be judged. Recording starts on its own when " +
          "the card starts moving and finishes on its own — nothing to press. Refuses until " +
          "confirmStart has been called. The frames are attached to your context; judge ONLY " +
          "whether a shine shifts across them, never read text from them.",
        parameters: {},
        timeoutSecs: 60,
        // Long, person-facing tool: a barge-in must not cancel it, so it runs async.
        cancelOnInterruption: false,
        async handler(_args, context) {
          useContext(context);
          if (!flow.confirmed) {
            return {
              captured: false,
              reason: "not_confirmed",
              say_next:
                "You skipped consent. Ask the person warmly whether they're ready to begin, wait for " +
                "a clear yes, then call confirmStart before captureHologram.",
            };
          }
          if (flow.hologram === "pass") {
            return { captured: false, reason: "already_confirmed", say_next: "The hologram is already confirmed — call captureCard." };
          }
          if (inFlight.has("captureHologram")) return busy("captureHologram");
          inFlight.add("captureHologram");
          satisfied("holo");
          satisfied("holoRetry");
          flow.holoAttempts += 1;
          flow.hologramCaptured = false;
          step("hologram", "active");
          const attempt = flow.holoAttempts;
          const lastAttempt = attempt >= HOLO_MAX_ATTEMPTS;
          let result;
          try {
            result = await captureHologramBurst(withVoice(context));
          } finally {
            inFlight.delete("captureHologram");
          }
          if (!result.captured) {
            expectNext(
              "holoRetry",
              WD.holoRetry,
              "No tilt was recorded and the person hasn't answered. Ask again, in one sentence, whether " +
                "they'd like to try tilting the card once more; if they decline, call reportHologram with " +
                "give_up true.",
            );
            return {
              ...result,
              attempt,
              last_attempt: lastAttempt,
              say_next:
                result.reason === "cancelled"
                  ? "They cancelled. Ask gently whether they'd like to try the tilt again; call " +
                    "captureHologram again only if they say yes, otherwise reportHologram with give_up true."
                  : result.reason === "no_tilt"
                    ? "The card was in the box but didn't move enough during the recording. Say so kindly, " +
                      "ask them to tilt it more clearly from side to side next time, ask whether they'd " +
                      "like to try again, and call captureHologram again if they say yes - or " +
                      "reportHologram with give_up true if they'd rather stop."
                    : "No card was placed in the box in time. Say so kindly, ask whether they'd like to try " +
                      "again (hold the card inside the box, hologram side facing the camera), and call " +
                      "captureHologram again if they say yes - or reportHologram with give_up true if " +
                      "they'd rather stop.",
            };
          }
          flow.hologramCaptured = true;
          step("hologram", "analyzing");
          expectNext(
            "holoReport",
            WD.holoReport,
            "Tilt frames were captured and attached, but reportHologram has not been called. Look at " +
              "them and call reportHologram now, silently (seen false if no shine shifted).",
            { repeat: 1 },
          );
          return {
            ...result,
            attempt,
            last_attempt: lastAttempt,
            image_note:
              "These are consecutive photos taken while the person tilted their PAN card. A genuine " +
              "Indian PAN card has a small silver/rainbow holographic emblem (the Income Tax " +
              "Department hologram) - on the back of many cards, on the front of some. Whichever side " +
              "is showing, find that emblem and compare the SAME spot across the frames: on a real " +
              "hologram its colour or brightness changes from frame to frame (silver, gold, green, " +
              "pink, bright, dark) as the angle changes. That change IS the hologram being seen - do " +
              "not look for anything to move. If no holographic emblem is anywhere on the side " +
              "shown, say so. Do not read or report any printed text from these.",
            say_next:
              "Check photo_attached. If not true, say the frames didn't come through and call " +
              "captureHologram again. If true, call reportHologram IMMEDIATELY and SILENTLY in this turn - " +
              "no words, no markStep, nothing else first (the photos are only available right now).",
          };
        },
      },
      reportHologram: {
        description:
          "Report honestly what the tilt frames show. Pass what_i_see (one sentence), card_visible " +
          "(true ONLY if a PAN card is clearly IN the frames - a face, a hand, a room or an empty box " +
          "is false), side ('front' = the side with the photo, 'back' = the other side, 'unknown' - " +
          "informational only; the hologram may be on either side), and seen: true ONLY if " +
          "card_visible is true AND the holographic emblem's colour or brightness changes across the " +
          "frames. When unsure, seen is false. Pass " +
          "give_up: true when the " +
          "person declines another try (or the tool said it was the last attempt) - the verification " +
          "then ends honestly without reading the card. Refuses until a tilt burst from the current " +
          "attempt has been captured. Never read text from the frames.",
        parameters: {
          type: "object",
          properties: {
            what_i_see: { type: "string" },
            card_visible: { type: "boolean" },
            side: { type: "string", enum: ["front", "back", "unknown"] },
            seen: { type: "boolean" },
            give_up: { type: "boolean" },
          },
          required: ["what_i_see", "card_visible", "seen"],
          additionalProperties: false,
        },
        async handler({ what_i_see, card_visible, side, seen, give_up }, context) {
          useContext(context);
          const seenText = cleanClaimValue(what_i_see, 300);
          if (give_up === true) {
            if (!flow.confirmed) {
              return { accepted: false, reason: "not_confirmed", say_next: "Get consent and run the hologram step first." };
            }
            flow.hologram = "unclear";
            flow.holoSeen = seenText || flow.holoSeen;
            satisfied("holoRetry");
            satisfied("holoReport");
            step("hologram", "done");
            const { result } = await finalize(null, context?.sendData);
            return {
              accepted: true,
              seen: false,
              gave_up: true,
              submitted: true,
              decision: result.decision,
              call_ending: true,
              say_next:
                "THIS IS THE END OF THE VERIFICATION. Do not call any other tool after this turn. " +
                "In two or three plain, kind sentences state as a final fact that you couldn't confirm " +
                "the card's hologram on camera, so the verification can't be completed today, and say " +
                "goodbye. Never say you'll check later, review it, or get back to them. The call ends " +
                "automatically when you finish speaking.",
            };
          }
          if (!flow.hologramCaptured) {
            return {
              accepted: false,
              reason: "no_tilt_frames",
              say_next: "Capture the tilt frames first with captureHologram.",
            };
          }
          satisfied("holoReport");
          flow.hologramCaptured = false; // frames are consumed by this report
          flow.holoSeen = seenText;
          if (card_visible === false) {
            // No card in the frames - whatever "shine" the model thinks it saw is
            // not a hologram. Never accept it; coach and retry.
            const lastAttemptNoCard = flow.holoAttempts >= HOLO_MAX_ATTEMPTS;
            if (!lastAttemptNoCard) {
              expectNext(
                "holoRetry",
                WD.holoRetry,
                "No card was in the tilt frames and the person hasn't answered. Ask again, in one " +
                  "sentence, whether they'd like to try once more with the card inside the box; if they " +
                  "decline, call reportHologram with give_up true.",
              );
            }
            return {
              accepted: true,
              seen: false,
              reason: "no_card_visible",
              attempt: flow.holoAttempts,
              last_attempt: lastAttemptNoCard,
              say_next: lastAttemptNoCard
                ? "That was the last attempt and no card was in the frames. Say so honestly and call " +
                  "reportHologram again with give_up true to end the verification."
                : "Say kindly that you couldn't see the card in the box that time (based on " +
                  "what_i_see), ask them to hold the PAN card fully inside the box with the hologram side " +
                  "facing the camera, and ASK whether they'd like to try once more. If yes, call " +
                  "captureHologram again. If no, call reportHologram with give_up true.",
            };
          }
          // `side` is informational only: the hologram may be on either side of a
          // PAN card, so this step cares about the hologram and nothing else.
          flow.holoSide = side || "unknown";
          if (seen === true) {
            flow.hologram = "pass";
            step("hologram", "done");
            step("card", "active");
            expectNext(
              "capture",
              WD.capture,
              "The hologram is confirmed but the card photo box has NOT been shown yet. Say to hold the " +
                "card flat and still for the read, then call captureCard now.",
              { repeat: 1 },
            );
            return {
              accepted: true,
              seen: true,
              say_next:
                "Say ONE short sentence - 'Lovely, the hologram checked out - now turn the card to the " +
                "front' - and call captureCard in the same turn. Do not explain the steps; the page does.",
            };
          }
          const lastAttempt = flow.holoAttempts >= HOLO_MAX_ATTEMPTS;
          if (!lastAttempt) {
            expectNext(
              "holoRetry",
              WD.holoRetry,
              "The hologram was not seen and the person hasn't answered. Ask again, in one sentence, " +
                "whether they'd like to try tilting once more; if they decline, call reportHologram with " +
                "give_up true.",
            );
          }
          return {
            accepted: true,
            seen: false,
            attempt: flow.holoAttempts,
            last_attempt: lastAttempt,
            say_next: lastAttempt
              ? "That was the last attempt. Say honestly what you saw, and call reportHologram again " +
                "with give_up true to end the verification."
              : "Say honestly what you saw (based on what_i_see) without pretending, give one concrete " +
                "tip (make sure the shiny hologram emblem is facing the camera - it's on the back of " +
                "most PAN cards / more light / tilt a bit further / keep the card in the box), and ASK " +
                "whether they'd like to try once more. If yes, call captureHologram again. If no, " +
                "call reportHologram with give_up true.",
          };
        },
      },
      captureCard: {
        description:
          "Show the card box and automatically capture a high-resolution photo of the FRONT of the " +
          "PAN card once it sits flat and steady inside it — the person presses nothing. Refuses " +
          "until the hologram has been confirmed. On success the photo is attached to your context " +
          "and the result has photo_attached: true; if it's missing, no image reached you.",
        parameters: {},
        timeoutSecs: 75,
        // Long, person-facing tool: a barge-in must not cancel it, so it runs async.
        cancelOnInterruption: false,
        async handler(_args, context) {
          useContext(context);
          if (!flow.confirmed) {
            return { captured: false, reason: "not_confirmed", say_next: "Get consent first: ask if they're ready, then confirmStart." };
          }
          if (flow.hologram !== "pass") {
            return {
              captured: false,
              reason: "hologram_not_confirmed",
              say_next:
                "The card is read only after the hologram is confirmed. Do the hologram step first: " +
                "captureHologram, then reportHologram.",
            };
          }
          if (inFlight.has("captureCard")) return busy("captureCard");
          inFlight.add("captureCard");
          // The box is open from here until the tool returns: no watchdog may fire.
          satisfied("capture");
          satisfied("recapture");
          flow.cardAttempts += 1;
          step("card", "active");
          let result;
          try {
            result = await captureCardStill(withVoice(context));
          } finally {
            inFlight.delete("captureCard");
          }
          if (!result.captured) {
            if (result.reason !== "cancelled") {
              expectNext(
                "recapture",
                WD.recapture,
                "The card photo was not captured and the box is closed. Reassure the person in one " +
                  "sentence and call captureCard again now.",
              );
            }
            return {
              ...result,
              say_next:
                result.reason === "cancelled"
                  ? "They cancelled. Ask gently if they'd like to try again or have a question; " +
                    "re-open the box only when they're ready."
                  : "Reassure them it's no problem at all, invite them to hold the card flat and still " +
                    "in the box, and call captureCard again.",
            };
          }
          flow.cardCaptured = true;
          flow.cardRead = null;
          step("card", "analyzing");
          expectNext(
            "report",
            WD.report,
            "A card photo was captured and attached, but you have not called reportCardRead yet. " +
              "Call reportCardRead now, silently (legible false if you cannot read it).",
            { repeat: 1 },
          );
          return {
            ...result,
            say_next:
              "Check photo_attached on this result. If it is not true, say the photo didn't come " +
              "through and call captureCard again. If it is true, call reportCardRead IMMEDIATELY and " +
              "SILENTLY in this turn - no words, no markStep, nothing else first - and never speak any " +
              "name or date.",
          };
        },
      },
      reportCardRead: {
        description:
          "Report honestly what is in the card photo. Pass what_i_see (one sentence describing the " +
          "image), legible (true ONLY if the FRONT of a PAN card is clearly in view AND you can " +
          "actually read the printed name and date of birth), and the exact name and dob you read " +
          "(empty if not). Placeholder names like 'John Doe' are rejected. When legible, the system " +
          "immediately compares the card against the registered details and finalizes the decision; " +
          "the say_next you get back is the verdict to speak. Refuses until a card photo was captured.",
        parameters: {
          type: "object",
          properties: {
            what_i_see: { type: "string" },
            legible: { type: "boolean" },
            name: { type: "string" },
            dob: { type: "string" },
          },
          required: ["what_i_see", "legible", "name", "dob"],
          additionalProperties: false,
        },
        async handler({ what_i_see, legible, name, dob }, context) {
          useContext(context);
          if (!flow.cardCaptured) {
            return {
              accepted: false,
              reason: "card_not_captured",
              say_next: "Capture the card photo first with captureCard.",
            };
          }
          satisfied("report");
          const seen = cleanClaimValue(what_i_see, 300);
          const placeholder = isPlaceholderName(name);
          const readName = placeholder ? "" : cleanClaimValue(name, 120);
          const readDob = cleanClaimValue(dob, 40);
          const trulyLegible = Boolean(legible) && readName && normalizeDob(readDob) !== null;
          if (!trulyLegible) {
            flow.cardRead = null;
            flow.cardCaptured = false; // that photo is spent; a new one is needed
            expectNext(
              "recapture",
              WD.recapture,
              "The last photo was not legible and the box is closed. Coach the person in one " +
                "sentence and call captureCard again now.",
            );
            const why = placeholder && legible
              ? "The name you gave is a generic placeholder, which means you could not actually read the card."
              : !readName
                ? "No real printed name was read."
                : "The date of birth was not read in a recognisable format.";
            return {
              accepted: false,
              legible: false,
              what_i_see: seen,
              reason: why,
              say_next:
                "Do NOT mention any name or date of birth. In one warm sentence say what the problem " +
                "was, based on what_i_see (for example 'that's the back of the card — please flip it to " +
                "the front', or 'it's a little blurry — hold it a touch closer and steady'), and call " +
                "captureCard again.",
            };
          }
          flow.cardRead = { name: readName, dob: readDob };
          step("card", "done");
          step("match", "active");
          // Compare right here. A MISMATCH (or "can't compare") ends the verification
          // now; a MATCH unlocks the liveness step, and the final PASS is only given
          // after liveness is confirmed.
          const verdict = compareIdentity(flow.cardRead, expected);
          flow.matchVerdict = verdict;
          if (verdict.name_match !== "pass") {
            const { result } = await finalize(null, context?.sendData);
            const decision = result.decision;
            const mismatched = [
              verdict?.name_ok === false ? "name" : null,
              verdict?.dob_ok === false ? "date of birth" : null,
            ].filter(Boolean);
            return {
              accepted: true,
              legible: true,
              submitted: true,
              decision,
              mismatched_fields: mismatched,
              call_ending: true,
              say_next: END_INSTRUCTION(decision, verdictLine(decision, verdict)),
            };
          }
          flow.match = "pass";
          step("match", "done");
          step("liveness", "active");
          expectNext(
            "liveness",
            WD.liveness,
            "The card details matched but the liveness step has not started. Call captureLiveness " +
              "immediately and silently. Do not wait for the person to ask you to start.",
            { repeat: 1 },
          );
          return {
            accepted: true,
            legible: true,
            match: "pass",
            say_next:
              "Call captureLiveness immediately and silently in this same turn. Do not wait for the " +
              "person to ask you to start, never say the name or date of birth, and do not give a verdict yet.",
          };
        },
      },
      captureLiveness: {
        description:
          "Show a face-shaped guide and automatically record a short burst of photos while the " +
          "person turns their head left and then right. Starts and finishes on its own - nothing " +
          "to press. Refuses until the card details have MATCHED. The frames are attached to your " +
          "context; judge ONLY whether the same live person's head visibly turns, never read text.",
        parameters: {},
        timeoutSecs: 60,
        cancelOnInterruption: false,
        async handler(_args, context) {
          useContext(context);
          if (flow.match !== "pass") {
            return {
              captured: false,
              reason: "match_not_passed",
              say_next: "Liveness runs only after the card details have matched. Finish the card read first.",
            };
          }
          if (flow.liveness === "pass") {
            return { captured: false, reason: "already_confirmed", say_next: "Liveness is already confirmed - give the verdict." };
          }
          if (inFlight.has("captureLiveness")) return busy("captureLiveness");
          inFlight.add("captureLiveness");
          satisfied("liveness");
          satisfied("liveRetry");
          flow.liveAttempts += 1;
          flow.livenessCaptured = false;
          step("liveness", "active");
          const attempt = flow.liveAttempts;
          const lastAttempt = attempt >= LIVE_MAX_ATTEMPTS;
          let result;
          try {
            result = await captureLivenessBurst(withVoice(context));
          } finally {
            inFlight.delete("captureLiveness");
          }
          if (!result.captured) {
            if (result.reason !== "cancelled") {
              expectNext(
                "liveRetry",
                WD.liveRetry,
                "The liveness recording didn't work and the person hasn't answered. Ask again, in one " +
                  "sentence, whether they'd like to try once more (turn the head a bit more); if they " +
                  "decline, call reportLiveness with give_up true.",
              );
            }
            return {
              ...result,
              attempt,
              last_attempt: lastAttempt,
              say_next:
                result.reason === "cancelled"
                  ? "They cancelled. Ask gently whether they'd like to try the head turn again; call " +
                    "captureLiveness again only if they say yes, otherwise reportLiveness with give_up true."
                  : "Very little movement was seen. Say so kindly, ask them to turn their head a bit " +
                    "further left and right this time, and call captureLiveness again if they say yes - " +
                    "or reportLiveness with give_up true if they'd rather stop.",
            };
          }
          flow.livenessCaptured = true;
          step("liveness", "analyzing");
          expectNext(
            "liveReport",
            WD.liveReport,
            "Liveness frames were captured and attached, but reportLiveness has not been called. Look " +
              "at them and call reportLiveness now, silently.",
            { repeat: 1 },
          );
          return {
            ...result,
            attempt,
            last_attempt: lastAttempt,
            image_note:
              "These are consecutive photos taken while the person was asked to turn their head left " +
              "and then right. Judge ONLY: is a real, live person's face clearly visible (not a photo, " +
              "screen or printout), and does the SAME face visibly turn - facing different directions " +
              "across the frames? Do not read or report any text, and do not describe the person.",
            say_next:
              "Check photo_attached. If not true, say the frames didn't come through and call " +
              "captureLiveness again. If true, call reportLiveness IMMEDIATELY and SILENTLY in this turn " +
              "- no words, nothing else first.",
          };
        },
      },
      reportLiveness: {
        description:
          "Report honestly what the liveness frames show BEFORE you speak. Pass what_i_see (one " +
          "sentence), face_visible (true ONLY if a real live person's face is clearly in the frames), " +
          "and moved (true ONLY if the same face visibly turns to face different directions across " +
          "the frames). When unsure, moved is false. Pass give_up: true when the person declines " +
          "another try (or the tool said it was the last attempt) - the verification then ends " +
          "honestly. Refuses until liveness frames from the current attempt have been captured.",
        parameters: {
          type: "object",
          properties: {
            what_i_see: { type: "string" },
            face_visible: { type: "boolean" },
            moved: { type: "boolean" },
            give_up: { type: "boolean" },
          },
          required: ["what_i_see", "face_visible", "moved"],
          additionalProperties: false,
        },
        async handler({ what_i_see, face_visible, moved, give_up }, context) {
          useContext(context);
          const seenText = cleanClaimValue(what_i_see, 300);
          if (give_up === true) {
            if (flow.match !== "pass") {
              return { accepted: false, reason: "match_not_passed", say_next: "Finish the card read first." };
            }
            flow.liveness = "unclear";
            flow.liveSeen = seenText || flow.liveSeen;
            satisfied("liveRetry");
            satisfied("liveReport");
            step("liveness", "done");
            const { result } = await finalize(null, context?.sendData);
            return {
              accepted: true,
              moved: false,
              gave_up: true,
              submitted: true,
              decision: result.decision,
              call_ending: true,
              say_next:
                "THIS IS THE END OF THE VERIFICATION. Do not call any other tool after this turn. In " +
                "two or three plain, kind sentences state as a final fact that the card and details " +
                "checked out but you couldn't confirm the liveness check on camera, so the verification " +
                "can't be completed today, and say goodbye. Never say you'll check later, review it, or " +
                "get back to them. Never say the name or date of birth. The call ends automatically when " +
                "you finish speaking.",
            };
          }
          if (!flow.livenessCaptured) {
            return {
              accepted: false,
              reason: "no_liveness_frames",
              say_next: "Capture the liveness frames first with captureLiveness.",
            };
          }
          satisfied("liveReport");
          flow.livenessCaptured = false; // frames are consumed by this report
          flow.liveSeen = seenText;
          if (face_visible === true && moved === true) {
            flow.liveness = "pass";
            step("liveness", "done");
            // Everything passed: finalize now; the next turn is the verdict.
            const { result } = await finalize(null, context?.sendData);
            return {
              accepted: true,
              moved: true,
              submitted: true,
              decision: result.decision,
              call_ending: true,
              say_next: END_INSTRUCTION(result.decision, verdictLine(result.decision, flow.matchVerdict)),
            };
          }
          const lastAttempt = flow.liveAttempts >= LIVE_MAX_ATTEMPTS;
          if (!lastAttempt) {
            expectNext(
              "liveRetry",
              WD.liveRetry,
              "Liveness was not confirmed and the person hasn't answered. Ask again, in one sentence, " +
                "whether they'd like to try once more; if they decline, call reportLiveness with give_up true.",
            );
          }
          return {
            accepted: true,
            moved: false,
            attempt: flow.liveAttempts,
            last_attempt: lastAttempt,
            say_next: lastAttempt
              ? "That was the last attempt. Say honestly what you saw, and call reportLiveness again " +
                "with give_up true to end the verification."
              : "Say honestly what you saw (based on what_i_see) without pretending, give one tip " +
                "(face the camera, turn the head clearly left then right, more light), and ASK whether " +
                "they'd like to try once more. If yes, call captureLiveness again. If no, call " +
                "reportLiveness with give_up true.",
          };
        },
      },
      markStep: {
        description:
          "Optional: the page already keeps the on-screen checklist in sync on its own. Only " +
          "call this if a step's state is clearly wrong on screen. Never call it instead of, or " +
          "before, a report tool.",
        parameters: {
          type: "object",
          properties: {
            step: { type: "string", enum: KYC_STEP_IDS },
            state: { type: "string", enum: ["active", "analyzing", "done"] },
          },
          required: ["step", "state"],
          additionalProperties: false,
        },
        async handler({ step: id, state }) {
          if (!KYC_STEP_IDS.includes(id)) return { ok: false, error: "unknown_step" };
          step(String(id), String(state));
          return { ok: true };
        },
      },
      submitResult: {
        description:
          "Persist and display the final KYC decision. Normally reportCardRead (or reportHologram " +
          "with give_up) already does this — only call submitResult if you had to give up on the card " +
          "after several tries. Calling it after a finalized result is harmless.",
        parameters: RESULT_SCHEMA,
        async handler(result, context) {
          useContext(context);
          const { result: finalized, verdict } = await finalize(result, context?.sendData);
          return {
            stored: true,
            decision: finalized.decision,
            session_id: finalized.session_id,
            call_ending: true,
            say_next: END_INSTRUCTION(finalized.decision, verdictLine(finalized.decision, verdict)),
          };
        },
      },
    },
  };
}
