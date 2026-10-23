// The simulator panel's webview (src/simulator.ts): paints the page shown,
// as the debug adapter sends its drawings, dimmed as the screen dims it; a
// page without background over what the screen showed when it was entered,
// as the screen draws it. Pressing the mouse on it presses the screen there,
// moving it while pressed moves the press, as a slider is dragged, and
// letting go releases it. Until the first drawing is painted, the canvas is
// hidden, and a message says how far the app's start has come. The zoom bar
// above it shows the screen larger or smaller (zoom.mjs); a press's place is
// divided back to the screen's pixels.
import { backdropChoice, dimScreen, imageSources, loadImage, paint } from "./preview-model.mjs";
import { ZoomBar } from "./zoom.mjs";
import { pagePixel } from "./zoom-model.mjs";

const vscode = acquireVsCodeApi();
const canvas = document.getElementById("screen");
const context = canvas.getContext("2d");
const startingMessage = document.getElementById("starting");
const zoomBar = document.getElementById("zoom");
const zoom = new ZoomBar(zoomBar, canvas, vscode, () => undefined);

// The screen's pixels as last painted, undimmed; what the page shown is drawn
// over, or null for black, the canvas's background; and the start and entry
// of the last drawing painted.
const screen = document.createElement("canvas");
let under = null;
let last;

// Loaded images by their source, kept while drawings use them.
let loaded = new Map();
// Drawings are painted in the order they came, each once its images have
// loaded. One is left out when a newer drawing of the same page entry
// follows, which shows that page later; so the last drawing of a page is
// always painted, as what the next page may be drawn over.
let painting = Promise.resolve();
let received = 0;
const newestOfEntry = new Map();      // "start:entry" -> the number of its newest drawing
let pressed = false;
// Where the press moved to, sent once per frame at most.
let moved = undefined;

window.addEventListener("message", (event) => {
  const message = event.data;
  if (message.type === "starting") {
    showStarting(message.progress);
    return;
  }
  if (message.type !== "drawing") {
    return;
  }
  const number = ++received;
  const entry = `${message.drawing.start}:${message.drawing.entry}`;
  newestOfEntry.set(entry, number);
  const images = loadImages(imageSources(message.drawing, message.pictureUris,
                                                       message.pictureMasks));
  painting = painting.then(async () => {
    const ready = await images;
    if (newestOfEntry.get(entry) === number) {
      newestOfEntry.delete(entry);
      paintDrawing(message.drawing, ready);
    }
  }).catch((error) => console.error(error));
});

// Paints a drawing: over black, over what the screen showed, or over what
// the page was drawn over before (backdropChoice); dimmed on the panel alone.
function paintDrawing(drawing, images) {
  const choice = backdropChoice(last, drawing);
  last = { start: drawing.start, entry: drawing.entry };
  if (choice === "black") {
    under = null;
  } else if (choice === "screen") {
    under = copyOf(screen);
  }
  screen.width = drawing.width;
  screen.height = drawing.height;
  paint(screen.getContext("2d"), drawing, images, drawing.transparent ? under : null);
  canvas.width = drawing.width;
  canvas.height = drawing.height;
  zoom.show(drawing.width, drawing.height);
  context.drawImage(screen, 0, 0);
  dimScreen(context, drawing);
  startingMessage.hidden = true;
  canvas.hidden = false;
  zoomBar.hidden = false;
}

// Says how far the app's start has come, until the first drawing is
// painted: later starts, such as a start again, keep the page shown.
function showStarting(progress) {
  if (startingMessage.hidden) {
    return;
  }
  startingMessage.textContent = progress.page === null
    ? "Starting the app" : `Compiling page ${progress.number} of ${progress.count}`;
}

// Returns a copy of a canvas's pixels, as a canvas.
function copyOf(source) {
  const copy = document.createElement("canvas");
  copy.width = source.width;
  copy.height = source.height;
  copy.getContext("2d").drawImage(source, 0, 0);
  return copy;
}

// The canvas captures the pointer while pressed, so that a move or a release
// outside the panel still reaches it.
canvas.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) {
    return;
  }
  pressed = true;
  canvas.setPointerCapture(event.pointerId);
  vscode.postMessage({ type: "press", ...screenPixel(event) });
});

canvas.addEventListener("pointermove", (event) => {
  if (!pressed) {
    return;
  }
  const waiting = moved !== undefined;
  moved = screenPixel(event);
  if (!waiting) {
    requestAnimationFrame(() => {
      if (moved !== undefined) {
        vscode.postMessage({ type: "move", ...moved });
        moved = undefined;
      }
    });
  }
});

// Returns the screen's pixel under a pointer event over the canvas.
function screenPixel(event) {
  return { x: pagePixel(event.offsetX, zoom.level), y: pagePixel(event.offsetY, zoom.level) };
}

canvas.addEventListener("pointerup", release);
canvas.addEventListener("pointercancel", release);

function release() {
  if (pressed) {
    pressed = false;
    if (moved !== undefined) {
      vscode.postMessage({ type: "move", ...moved });
      moved = undefined;
    }
    vscode.postMessage({ type: "release" });
  }
}

// Returns the images by key, loading those not loaded yet.
async function loadImages(sources) {
  const kept = new Map();
  const ready = new Map();
  await Promise.all(sources.map(async ([key, source, how, mask]) => {
    // One file loads otherwise as a picture stored without alpha, and a card
    // picture as its mask has it.
    const loading = mask === undefined ? `${how} ${source}` : `${how} ${source} ${mask}`;
    const image = loaded.get(loading) ?? await loadImage(source, how, mask);
    if (image) {
      kept.set(loading, image);
      ready.set(key, image);
    }
  }));
  loaded = kept;
  return ready;
}

vscode.postMessage({ type: "ready" });
