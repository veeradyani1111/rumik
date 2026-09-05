import test from "node:test";
import assert from "node:assert/strict";

import {
  CARD_ASPECT,
  blurScore,
  cardQuality,
  detectCardQuad,
  detectorReady,
  glareRatio,
  orderCorners,
  quadArea,
  quadAspect,
  shineAcrossFrames,
  useOpenCv,
  warpCard,
} from "../../kyc/card-detector.js";

// The same OpenCV build the page loads from the CDN, here from npm for Node.
const cv = await (await import("@techstark/opencv-js")).default;
useOpenCv(cv);

// --- Synthetic scenes ----------------------------------------------------------

function blank(width, height, shade) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < data.length; i += 4) { data[i] = shade; data[i + 1] = shade; data[i + 2] = shade; data[i + 3] = 255; }
  return { data, width, height };
}

const inQuad = (corners, x, y) => {
  let sign = 0;
  for (let i = 0; i < 4; i += 1) {
    const a = corners[i];
    const b = corners[(i + 1) % 4];
    const cross = (b.x - a.x) * (y - a.y) - (b.y - a.y) * (x - a.x);
    if (cross === 0) continue;
    if (sign === 0) sign = Math.sign(cross);
    else if (Math.sign(cross) !== sign) return false;
  }
  return true;
};

// A card of the ID-1 aspect, centred, rotated by `angle` degrees, with a few
// dark "print" lines inside so the crop has real detail.
function cardScene({ width = 320, height = 240, cardW = 200, angle = 8, background = 40, card = 205, print = true } = {}) {
  const image = blank(width, height, background);
  const cardH = cardW / CARD_ASPECT;
  const rad = (angle * Math.PI) / 180;
  const cx = width / 2;
  const cy = height / 2;
  const rot = (x, y) => ({ x: cx + x * Math.cos(rad) - y * Math.sin(rad), y: cy + x * Math.sin(rad) + y * Math.cos(rad) });
  const corners = [rot(-cardW / 2, -cardH / 2), rot(cardW / 2, -cardH / 2), rot(cardW / 2, cardH / 2), rot(-cardW / 2, cardH / 2)];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (!inQuad(corners, x + 0.5, y + 0.5)) continue;
      // Position inside the (unrotated) card, for the print lines.
      const dx = x + 0.5 - cx;
      const dy = y + 0.5 - cy;
      const u = dx * Math.cos(-rad) - dy * Math.sin(-rad) + cardW / 2;
      const v = dx * Math.sin(-rad) + dy * Math.cos(-rad) + cardH / 2;
      const line = print && v > cardH * 0.35 && v < cardH * 0.85 && Math.floor(v / 6) % 2 === 0 && u > cardW * 0.1 && u < cardW * 0.9;
      const shade = line ? 30 : card;
      const i = (y * width + x) * 4;
      image.data[i] = shade; image.data[i + 1] = shade; image.data[i + 2] = shade;
    }
  }
  return { image, corners, cardW, cardH };
}

const near = (a, b, tol) => Math.hypot(a.x - b.x, a.y - b.y) <= tol;

// --- Pure geometry -------------------------------------------------------------

test("orderCorners returns top-left, top-right, bottom-right, bottom-left whatever the input order", () => {
  const shuffled = [{ x: 90, y: 60 }, { x: 10, y: 8 }, { x: 12, y: 62 }, { x: 88, y: 10 }];
  assert.deepEqual(orderCorners(shuffled), [{ x: 10, y: 8 }, { x: 88, y: 10 }, { x: 90, y: 60 }, { x: 12, y: 62 }]);
  const quad = orderCorners(shuffled);
  assert.ok(Math.abs(quadAspect(quad) - 79 / 52) < 0.05);
  assert.ok(Math.abs(quadArea(quad) - 78 * 52) < 200);
  // Portrait input reports the same long-over-short ratio.
  assert.ok(Math.abs(quadAspect([{ x: 0, y: 0 }, { x: 52, y: 0 }, { x: 52, y: 79 }, { x: 0, y: 79 }]) - 79 / 52) < 1e-9);
});

test("shineAcrossFrames finds the one block whose brightness changes across frames", () => {
  const frames = [];
  for (let f = 0; f < 4; f += 1) {
    const frame = blank(160, 100, 120);
    // A hologram emblem near the top-right that goes dark → bright → dark → bright.
    const shade = f % 2 ? 250 : 60;
    for (let y = 10; y < 30; y += 1) for (let x = 120; x < 150; x += 1) { const i = (y * 160 + x) * 4; frame.data[i] = shade; frame.data[i + 1] = shade; frame.data[i + 2] = shade; }
    frames.push(frame);
  }
  const shine = shineAcrossFrames(frames);
  assert.equal(shine.frames, 4);
  assert.ok(shine.max > 40, `emblem block should swing strongly, got ${shine.max}`);
  assert.equal(shine.median, 0, "the rest of the card does not change");
  assert.deepEqual(shine.block, { row: 0, col: 6 });
  // Identical frames: no shine anywhere.
  assert.equal(shineAcrossFrames([frames[0], frames[0], frames[0]]).max, 0);
  assert.equal(shineAcrossFrames([frames[0]]).max, 0);
});

// --- OpenCV-backed detection -------------------------------------------------------

test("detectCardQuad finds a rotated card on a dark background with its corners", () => {
  assert.equal(detectorReady(), cv);
  const { image, corners } = cardScene({ angle: 8 });
  const found = detectCardQuad(cv, image);
  assert.equal(found.found, true);
  assert.ok(Math.abs(found.aspect - CARD_ASPECT) < 0.1, `aspect ${found.aspect}`);
  assert.ok(found.areaFrac > 0.25 && found.areaFrac < 0.4, `areaFrac ${found.areaFrac}`);
  for (let i = 0; i < 4; i += 1) {
    assert.ok(near(found.corners[i], corners[i], 5), `corner ${i}: ${JSON.stringify(found.corners[i])} vs ${JSON.stringify(corners[i])}`);
  }
});

test("detectCardQuad copes with a light background and rejects an empty or wrong-shaped scene", () => {
  // Card slightly darker than a bright desk: low contrast, but still a quad.
  const light = cardScene({ angle: -5, background: 235, card: 200 });
  const onLight = detectCardQuad(cv, light.image);
  assert.equal(onLight.found, true);
  for (let i = 0; i < 4; i += 1) assert.ok(near(onLight.corners[i], light.corners[i], 6));
  // Nothing in the frame.
  assert.equal(detectCardQuad(cv, blank(320, 240, 90)).found, false);
  // A square is not a card.
  const square = blank(320, 240, 40);
  for (let y = 40; y < 200; y += 1) for (let x = 80; x < 240; x += 1) { const i = (y * 320 + x) * 4; square.data[i] = square.data[i + 1] = square.data[i + 2] = 210; }
  assert.equal(detectCardQuad(cv, square).found, false);
  // A card that is too small (far from the camera) does not count.
  assert.equal(detectCardQuad(cv, cardScene({ cardW: 90 }).image).found, false);
});

test("a finger over the card's edge still yields the card, via the rotated-rectangle fallback", () => {
  const { image, corners } = cardScene({ angle: 6 });
  // A dark "finger" blob crossing the bottom edge into the card.
  const fx = 190;
  const fy = Math.round((corners[2].y + corners[3].y) / 2);
  for (let y = fy - 18; y < fy + 30; y += 1) for (let x = fx - 14; x < fx + 14; x += 1) {
    if (y < 0 || y >= image.height || x < 0 || x >= image.width) continue;
    const i = (y * image.width + x) * 4;
    image.data[i] = image.data[i + 1] = image.data[i + 2] = 40;
  }
  const found = detectCardQuad(cv, image);
  assert.equal(found.found, true, JSON.stringify(found));
  assert.ok(Math.abs(found.aspect - CARD_ASPECT) < 0.15, `aspect ${found.aspect}`);
  for (let i = 0; i < 4; i += 1) assert.ok(near(found.corners[i], corners[i], 8), `corner ${i}: ${JSON.stringify(found.corners[i])} vs ${JSON.stringify(corners[i])}`);
});

test("warpCard flattens the detected quad and quality metrics separate sharp from blurred and glare", () => {
  const { image } = cardScene({ angle: 10 });
  const found = detectCardQuad(cv, image);
  const flat = warpCard(cv, image, found.corners, 320, 202);
  assert.equal(flat.width, 320);
  assert.equal(flat.height, 202);
  // The flattened crop is the card: bright overall (no dark background corners).
  const cornerPixel = (x, y) => flat.data[(y * 320 + x) * 4];
  for (const [x, y] of [[3, 3], [316, 3], [316, 198], [3, 198]]) assert.ok(cornerPixel(x, y) > 150, `corner (${x},${y}) = ${cornerPixel(x, y)}`);
  // Sharp print scores well above the threshold; a flat card face is "blurry".
  const sharp = cardQuality(cv, flat);
  assert.equal(sharp.state, "ok", JSON.stringify(sharp));
  const plain = warpCard(cv, cardScene({ angle: 10, print: false }).image, found.corners, 320, 202);
  assert.ok(blurScore(cv, plain) < sharp.blur / 4);
  assert.equal(cardQuality(cv, plain).state, "blurry");
  // Glare: blow out a patch of the flat card.
  const glared = { ...flat, data: new Uint8ClampedArray(flat.data) };
  for (let y = 20; y < 80; y += 1) for (let x = 200; x < 300; x += 1) { const i = (y * 320 + x) * 4; glared.data[i] = glared.data[i + 1] = glared.data[i + 2] = 255; }
  assert.ok(glareRatio(cv, glared) > 0.06);
  assert.equal(cardQuality(cv, glared).state, "glare");
});
