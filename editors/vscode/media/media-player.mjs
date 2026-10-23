// The player of the media viewer (src/mediaViewer.ts): an animation's or a
// video's frames, which the extension sends as the language server reads
// them (nxwright/mediaFrames), again when the file changes, drawn in turn
// at their timing, again and again, with play and pause, and a slider
// choosing the frame shown. Each frame is drawn as the preview draws it
// (preview-model.mjs, paintFrame): turned back for the rotation its file was
// made for, cut to its size.
import { element } from "./elements.mjs";
import { loadImage, paintFrame } from "./preview-model.mjs";

const vscode = acquireVsCodeApi();
const byId = (id) => document.getElementById(id);
const canvas = byId("screen");
const context = canvas.getContext("2d");
const playButton = byId("play");
const slider = byId("frame");

let frames = undefined;   // as the extension sent them
let images = [];          // each frame's picture, loaded
let shown = 0;            // the frame shown
let playing = false;
// While playing: when the run started, by the page's clock, in ms, as if it
// had played without pause from the start of the frame shown.
let startedAt = 0;
// How many times playing started: a tick of an earlier start stops, so that
// starting again, as on frames sent again, never runs two loops.
let runs = 0;
// How many times frames were sent: only the latest's pictures are kept, as
// those of frames sent before may finish loading after them.
let sends = 0;

window.addEventListener("message", (event) => {
  if (event.data.type === "frames") {
    if (event.data.error !== undefined) {
      byId("facts").replaceChildren(element("span", "problem", event.data.error));
    } else {
      void start(event.data.frames);
    }
  }
});

playButton.addEventListener("click", () => (playing ? pause() : play()));
slider.addEventListener("input", () => {
  pause();
  show(Number(slider.value));
});

async function start(sent) {
  // Frames sent again, as when the file changed: the run playing stops first.
  pause();
  const send = ++sends;
  if (sent.pictures.length === 0) {
    frames = sent;
    images = [];
    canvas.hidden = true;
    byId("controls").hidden = true;
    byId("facts").textContent = "The file holds no frames.";
    return;
  }
  // In their JPEG pictures' own colours, as the preview draws frames
  // (nxwright/drawing/media_drawing.py).
  const loaded = await Promise.all(sent.pictures.map((picture) => loadImage(picture, "text")));
  if (send !== sends) {
    return;
  }
  frames = sent;
  images = loaded;
  canvas.width = frames.width;
  canvas.height = frames.height;
  canvas.hidden = false;
  byId("controls").hidden = false;
  slider.max = String(frames.pictures.length - 1);
  byId("facts").textContent = [
    `${frames.width} x ${frames.height} pixels`, `${frames.pictures.length} frames`,
    `${frames.length} ms a run`,
    ...(frames.rotation ? [`stored for a screen turned ${frames.rotation} degrees`] : [])]
    .join(", ");
  show(0);
  play();
}

function show(number) {
  shown = number;
  context.clearRect(0, 0, canvas.width, canvas.height);
  paintFrame(context, images[number], { x: 0, y: 0, w: frames.width, h: frames.height,
                                        rotation: frames.rotation });
  slider.value = String(number);
  byId("position").textContent =
    `frame ${number + 1} of ${frames.pictures.length}, at ${frames.starts[number]} ms`;
}

function play() {
  playing = true;
  playButton.textContent = "Pause";
  startedAt = performance.now() - frames.starts[shown];
  const run = ++runs;
  requestAnimationFrame((now) => tick(now, run));
}

function pause() {
  playing = false;
  playButton.textContent = "Play";
}

// Shows the frame the time into the run falls on, the run starting again
// once it ends.
function tick(now, run) {
  if (!playing || run !== runs) {
    return;
  }
  const time = frames.length > 0 ? (now - startedAt) % frames.length : 0;
  const number = frameAt(time);
  if (number !== shown) {
    show(number);
  }
  requestAnimationFrame((later) => tick(later, run));
}

// The number of the frame showing `time` ms into a run, as Frames.at says.
function frameAt(time) {
  let number = 0;
  while (number + 1 < frames.starts.length && frames.starts[number + 1] <= time) {
    number += 1;
  }
  return number;
}

vscode.postMessage({ type: "ready" });
