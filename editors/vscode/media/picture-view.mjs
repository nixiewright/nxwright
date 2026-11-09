// The picture editor's page (src/pictureView.ts): an SVG picture as nxwright
// draws it, at its own size, with its size above it, or why it cannot be
// drawn. The extension sends the picture again whenever a file it reads
// changes.
import { element } from "./elements.mjs";

const vscode = acquireVsCodeApi();
const byId = (id) => document.getElementById(id);

window.addEventListener("message", (event) => {
  if (event.data.type === "drawn") {
    show(event.data);
  }
});

function show(drawn) {
  const place = byId("picture");
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
  place.replaceChildren(picture);
}

vscode.postMessage({ type: "ready" });
