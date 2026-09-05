// Card detection for the capture steps, built on OpenCV compiled to WebAssembly.
//
// The page used to decide "a card is in the box" from a 160-pixel grey sample:
// brightness steps around the box edges, a flat interior, enough print texture.
// That breaks on dark or shiny surfaces, a hand over an edge, or a card that is
// not lined up with the box. This module finds the card the way a document
// scanner does - edges, contours, the largest convex four-corner shape with an
// ID-1 card aspect ratio - and returns its corners, so the capture steps can
//   · know the card is really there, anywhere in the box, on any background,
//   · perspective-warp it to a flat, correctly proportioned rectangle before it
//     is sent to the reading model,
//   · measure blur and glare on that flat crop instead of guessing, and
//   · align the tilt frames so the hologram's shine can be measured directly.
//
// Every function takes the `cv` instance explicitly, so the same code runs in
// the browser (script tag from the CDN, see loadOpenCv) and in Node tests (the
// @techstark/opencv-js package). Images are plain {data, width, height} RGBA
// objects - an ImageData works as is. All OpenCV Mats are freed on every path.

export const CARD_ASPECT = 85.6 / 54; // ISO ID-1 card, landscape
export const OPENCV_URL = "https://cdn.jsdelivr.net/npm/@techstark/opencv-js@4.11.0-release.1/dist/opencv.js";

// --- Loading -----------------------------------------------------------------
// opencv.js is ~11 MB, so it is fetched once, in the background, the moment the
// page opens - never when a capture box is about to appear. Steps use it only if
// it is ready; otherwise they fall back to the old heuristic without waiting.

let cvPromise = null;
let readyCv = null;

async function settleCv(candidate) {
  let cv = candidate;
  if (!cv) throw new Error("opencv.js loaded but no cv global was defined");
  if (typeof cv.then === "function") cv = await cv; // newer builds expose a Promise
  if (!cv.Mat) {
    await new Promise((resolve) => { cv.onRuntimeInitialized = resolve; });
  }
  return cv;
}

export function loadOpenCv({ document: doc = globalThis.document, url = OPENCV_URL } = {}) {
  if (cvPromise) return cvPromise;
  cvPromise = new Promise((resolve, reject) => {
    if (!doc) { reject(new Error("no document to load opencv.js into")); return; }
    if (globalThis.cv?.Mat) { resolve(globalThis.cv); return; }
    const script = doc.createElement("script");
    script.src = url;
    script.async = true;
    script.onload = () => settleCv(globalThis.cv).then(resolve, reject);
    script.onerror = () => reject(new Error(`opencv.js failed to load from ${url}`));
    doc.head.append(script);
  }).then((cv) => { readyCv = cv; return cv; });
  cvPromise.catch(() => { /* reported by whoever awaits; never unhandled */ });
  return cvPromise;
}

// Tests and hosts that already hold a cv instance register it directly.
export function useOpenCv(cv) {
  readyCv = cv;
  cvPromise = Promise.resolve(cv);
  return cv;
}

// Synchronous: the cv instance if loading has finished, else null.
export function detectorReady() {
  return readyCv;
}

// --- Geometry (pure JS) ------------------------------------------------------

// Order four corner points as top-left, top-right, bottom-right, bottom-left.
export function orderCorners(points) {
  const pts = points.map((p) => ({ x: p.x, y: p.y }));
  const bySum = [...pts].sort((a, b) => a.x + a.y - (b.x + b.y));
  const tl = bySum[0];
  const br = bySum[3];
  const rest = pts.filter((p) => p !== tl && p !== br).sort((a, b) => a.y - a.x - (b.y - b.x));
  const tr = rest[0];
  const bl = rest[1];
  return [tl, tr, br, bl];
}

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

// Long side over short side of an ordered quad (>= 1 whatever the orientation).
export function quadAspect(corners) {
  const [tl, tr, br, bl] = corners;
  const w = (dist(tl, tr) + dist(bl, br)) / 2;
  const h = (dist(tl, bl) + dist(tr, br)) / 2;
  if (!w || !h) return 0;
  return Math.max(w, h) / Math.min(w, h);
}

// Shoelace area of an ordered quad.
export function quadArea(corners) {
  let area = 0;
  for (let i = 0; i < corners.length; i += 1) {
    const a = corners[i];
    const b = corners[(i + 1) % corners.length];
    area += a.x * b.y - b.x * a.y;
  }
  return Math.abs(area) / 2;
}

// --- Detection ---------------------------------------------------------------

function rgbaMat(cv, image) {
  return cv.matFromArray(image.height, image.width, cv.CV_8UC4, image.data);
}

// Run `fn` with a scratch list; every Mat pushed onto it is freed afterwards.
function withMats(fn) {
  const mats = [];
  const track = (mat) => { mats.push(mat); return mat; };
  try {
    return fn(track);
  } finally {
    for (const mat of mats) { try { mat.delete(); } catch { /* already freed */ } }
  }
}

// Find the card as the best convex quadrilateral in the image. Two edge maps are
// tried - Canny for crisp edges, an inverted Otsu threshold for low-contrast
// edges where Canny fragments - and the best-scoring quad across both wins.
// `minAreaFrac` is the smallest share of the image a card may cover; the caller
// samples an area a little larger than the guide box, so a card that fills the
// box covers roughly two thirds of the sample.
export function detectCardQuad(cv, image, {
  minAreaFrac = 0.15,
  maxAreaFrac = 0.98,
  aspect = CARD_ASPECT,
  aspectTol = 0.28,
  margin = 0.06,
  // Occlusion fallback: a finger over an edge breaks the clean four-corner
  // outline, but the contour still fills at least this much of its minimum
  // bounding rotated rectangle - that rectangle is then taken as the card.
  minFill = 0.82,
} = {}) {
  const empty = { found: false, corners: null, areaFrac: 0, aspect: 0, score: 0, method: "none" };
  if (!cv || !image || image.width < 32 || image.height < 32) return empty;
  return withMats((track) => {
    const src = track(rgbaMat(cv, image));
    const gray = track(new cv.Mat());
    cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY);
    const blurred = track(new cv.Mat());
    cv.GaussianBlur(gray, blurred, new cv.Size(5, 5), 0);
    const imageArea = image.width * image.height;
    const kernel = track(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(3, 3)));
    let best = empty;

    const consider = (edges) => {
      const dilated = track(new cv.Mat());
      cv.dilate(edges, dilated, kernel);
      const contours = track(new cv.MatVector());
      const hierarchy = track(new cv.Mat());
      cv.findContours(dilated, contours, hierarchy, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE);
      for (let i = 0; i < contours.size(); i += 1) {
        const contour = contours.get(i);
        try {
          const area = cv.contourArea(contour);
          if (area < minAreaFrac * imageArea || area > maxAreaFrac * imageArea) continue;
          const approx = track(new cv.Mat());
          cv.approxPolyDP(contour, approx, 0.03 * cv.arcLength(contour, true), true);
          let corners = null;
          let fill = 1;
          let method = "quad";
          if (approx.rows === 4 && cv.isContourConvex(approx)) {
            const pts = [];
            for (let k = 0; k < 4; k += 1) pts.push({ x: approx.data32S[k * 2], y: approx.data32S[k * 2 + 1] });
            corners = orderCorners(pts);
          } else {
            const rect = cv.minAreaRect(contour);
            const rectArea = rect.size.width * rect.size.height;
            fill = rectArea ? area / rectArea : 0;
            if (fill < minFill) continue;
            corners = orderCorners(cv.RotatedRect.points(rect));
            method = "rect";
          }
          const inside = corners.every((p) =>
            p.x >= -margin * image.width && p.x <= (1 + margin) * image.width &&
            p.y >= -margin * image.height && p.y <= (1 + margin) * image.height);
          if (!inside) continue;
          const ratio = quadAspect(corners);
          const aspectError = Math.abs(ratio - aspect) / aspect;
          if (aspectError > aspectTol) continue;
          const areaFrac = quadArea(corners) / imageArea;
          const score = areaFrac * (1 - aspectError / aspectTol) * fill;
          if (score > best.score) best = { found: true, corners, areaFrac, aspect: ratio, score, method };
        } finally {
          contour.delete();
        }
      }
    };

    const canny = track(new cv.Mat());
    cv.Canny(blurred, canny, 50, 150);
    consider(canny);
    // A card only a little darker or lighter than the surface it lies on (a
    // white card on a pale desk) has edges too weak for the strict pass.
    const softCanny = track(new cv.Mat());
    cv.Canny(blurred, softCanny, 15, 45);
    consider(softCanny);
    const otsu = track(new cv.Mat());
    cv.threshold(blurred, otsu, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU);
    const otsuEdges = track(new cv.Mat());
    cv.Canny(otsu, otsuEdges, 50, 150);
    consider(otsuEdges);
    return {
      ...best,
      areaFrac: Math.round(best.areaFrac * 1000) / 1000,
      aspect: Math.round(best.aspect * 1000) / 1000,
      score: Math.round(best.score * 1000) / 1000,
    };
  });
}

// Perspective-warp the quad `corners` (in `image` coordinates) to a flat
// outW x outH RGBA image.
export function warpCard(cv, image, corners, outW, outH) {
  return withMats((track) => {
    const src = track(rgbaMat(cv, image));
    const [tl, tr, br, bl] = orderCorners(corners);
    const from = track(cv.matFromArray(4, 1, cv.CV_32FC2, [tl.x, tl.y, tr.x, tr.y, br.x, br.y, bl.x, bl.y]));
    const to = track(cv.matFromArray(4, 1, cv.CV_32FC2, [0, 0, outW, 0, outW, outH, 0, outH]));
    const transform = track(cv.getPerspectiveTransform(from, to));
    const dst = track(new cv.Mat());
    cv.warpPerspective(src, dst, transform, new cv.Size(outW, outH), cv.INTER_LINEAR, cv.BORDER_REPLICATE);
    return { data: new Uint8ClampedArray(dst.data), width: outW, height: outH };
  });
}

// --- Quality -----------------------------------------------------------------

// Grey interior of a flat card crop. The detected corners are never exact, so a
// sliver of background can line an edge of the warp; measuring quality on the
// inner region keeps that sliver out of the blur and glare numbers.
function grayInterior(cv, track, image, inset) {
  const src = track(rgbaMat(cv, image));
  const gray = track(new cv.Mat());
  cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY);
  const x = Math.round(image.width * inset);
  const y = Math.round(image.height * inset);
  const w = Math.max(2, image.width - 2 * x);
  const h = Math.max(2, image.height - 2 * y);
  return track(gray.roi(new cv.Rect(x, y, w, h)));
}

// Variance of the Laplacian: sharp print scores high, motion blur scores low.
export function blurScore(cv, image, { inset = 0.1 } = {}) {
  return withMats((track) => {
    const gray = grayInterior(cv, track, image, inset);
    const lap = track(new cv.Mat());
    cv.Laplacian(gray, lap, cv.CV_64F);
    const mean = track(new cv.Mat());
    const stddev = track(new cv.Mat());
    cv.meanStdDev(lap, mean, stddev);
    const sd = stddev.data64F[0];
    return Math.round(sd * sd * 10) / 10;
  });
}

// Share of pixels that are blown out (specular glare on a laminated card).
export function glareRatio(cv, image, { level = 250, inset = 0.1 } = {}) {
  return withMats((track) => {
    const gray = grayInterior(cv, track, image, inset);
    const bright = track(new cv.Mat());
    cv.threshold(gray, bright, level - 1, 255, cv.THRESH_BINARY);
    return Math.round((cv.countNonZero(bright) / (gray.rows * gray.cols)) * 1000) / 1000;
  });
}

// Thresholds are for a flat card crop about 320 px wide. Print on a PAN card in
// focus scores well above 100; motion blur drops it under 30.
export const QUALITY = { blurMin: 45, glareMax: 0.06 };

export function cardQuality(cv, image, thresholds = QUALITY) {
  const blur = blurScore(cv, image);
  const glare = glareRatio(cv, image);
  const state = glare > thresholds.glareMax ? "glare" : blur < thresholds.blurMin ? "blurry" : "ok";
  return { blur, glare, state, ok: state === "ok" };
}

// --- Hologram shine (pure JS) ------------------------------------------------

function blockMeans(image, cols, rows) {
  const { data, width, height } = image;
  const means = new Float64Array(cols * rows);
  const counts = new Float64Array(cols * rows);
  for (let y = 0; y < height; y += 1) {
    const r = Math.min(rows - 1, Math.floor((y * rows) / height));
    for (let x = 0; x < width; x += 1) {
      const c = Math.min(cols - 1, Math.floor((x * cols) / width));
      const i = (y * width + x) * 4;
      const luma = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      means[r * cols + c] += luma;
      counts[r * cols + c] += 1;
    }
  }
  for (let k = 0; k < means.length; k += 1) means[k] = counts[k] ? means[k] / counts[k] : 0;
  return means;
}

// Given the SAME flat card crop from several tilt frames, a hologram is the
// spot whose brightness changes most from frame to frame while the rest of the
// card stays put. Returns the strongest per-block change (standard deviation of
// that block's mean brightness across frames) and where it was.
export function shineAcrossFrames(frames, { cols = 8, rows = 5 } = {}) {
  const usable = (frames || []).filter((f) => f && f.width && f.height && f.data);
  if (usable.length < 2) return { frames: usable.length, max: 0, median: 0, block: null, cols, rows };
  const grids = usable.map((f) => blockMeans(f, cols, rows));
  const stds = new Float64Array(cols * rows);
  for (let k = 0; k < stds.length; k += 1) {
    const values = grids.map((g) => g[k]);
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    stds[k] = Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length);
  }
  let maxK = 0;
  for (let k = 1; k < stds.length; k += 1) if (stds[k] > stds[maxK]) maxK = k;
  const sorted = [...stds].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  return {
    frames: usable.length,
    max: Math.round(stds[maxK] * 10) / 10,
    median: Math.round(median * 10) / 10,
    block: { row: Math.floor(maxK / cols), col: maxK % cols },
    cols,
    rows,
  };
}
