// The picture editor's page (src/pictureView.ts): an SVG picture as nxwright
// draws it, with its size above it, or why it cannot be drawn. The extension
// sends the picture again whenever a file it reads changes. The picture is
// sharp at its own size, and smoothed when it shrinks to fit a smaller
// editor, as in the page preview.
import { element } from "./elements.mjs";
import { smoothedAt } from "./zoom-model.mjs";

const vscode = acquireVsCodeApi();
const byId = (id) => document.getElementById(id);
// Follows the size of the picture shown, to sharpen or smooth it.
let sizeWatcher;

window.addEventListener("message", (event) => {
  if (event.data.type === "drawn") {
    show(event.data);
  }
});

function show(drawn) {
  const place = byId("picture");
  sizeWatcher?.disconnect();
  if (drawn.error !== undefined) {
    byId("facts").textContent = "";
    place.replaceChildren(element("p", "problem", drawn.error));
    return;
  }
  byId("facts").textContent = `${drawn.width} × ${drawn.height} pixels`;
  const picture = element("img");
  picture.src = drawn.picture;
  picture.width = drawn.width;
  picture.height = drawn.height;
  picture.alt = "The picture as nxwright draws it";
  sizeWatcher = new ResizeObserver(() => {
    const level = picture.clientWidth / drawn.width;
    picture.style.imageRendering = smoothedAt(level) ? "auto" : "pixelated";
  });
  sizeWatcher.observe(picture);
  place.replaceChildren(picture);
}

vscode.postMessage({ type: "ready" });
