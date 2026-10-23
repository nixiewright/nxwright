// The font viewer's page (src/fontViewer.ts): the font's name and facts, a
// box for the sample's text, the sample drawn in the font, and, for a font of
// a source folder, "Create a variation of this font". The extension asks the
// language server for the font's details and sample, drawn again as the
// box's text changes, the theme changes, or the file changes on disk.
import { element } from "./elements.mjs";
import { debounced, rgbOf } from "./fonts-model.mjs";

const vscode = acquireVsCodeApi();
const byId = (id) => document.getElementById(id);
// The sample's first text, as the Fonts panel's.
const FIRST_SAMPLE = "The quick brown fox jumps over 0123456789";
// How long typing must pause before the sample is drawn again, in ms.
const PAUSE = 250;

const text = byId("text");
text.value = FIRST_SAMPLE;
// The font's name, once the server has given it.
let name = undefined;
// How many times the details were asked for: only the latest reply is shown,
// as replies to a box being typed in may come out of order.
let asked = 0;

const askSoon = debounced(() => askDetails(), PAUSE);
text.addEventListener("input", askSoon);
byId("vary").textContent = "Create a variation of this font";
byId("vary").addEventListener("click", () => vscode.postMessage({ type: "variation", name }));

window.addEventListener("message", (event) => {
  if (event.data.type === "details" && event.data.asked === asked) {
    show(event.data);
  } else if (event.data.type === "fileChanged") {
    askDetails();
  }
});

// A change of theme, which VS Code marks on the body's class, draws the
// sample again in the new text colour.
new MutationObserver(() => askDetails()).observe(document.body,
                                                 { attributes: true, attributeFilter: ["class"] });

// Asks for the font's details and a sample of the box's text, in the
// page's text colour, as the theme gives it now.
function askDetails() {
  vscode.postMessage({ type: "details", asked: ++asked, text: text.value,
                       colour: rgbOf(getComputedStyle(document.body).color) });
}

function show(reply) {
  const sample = byId("sample");
  if (reply.error !== undefined) {
    sample.replaceChildren(element("p", "problem", reply.error));
    return;
  }
  const details = reply.details;
  name = details.name;
  byId("name").textContent = details.name;
  byId("facts").textContent = details.height === undefined ? "" : [
    `${details.height} pixels`, details.encoding, details.smoothed ? "smoothed" : "not smoothed",
    `${details.characters} characters`, `stored at rotation ${details.rotation}`].join(", ");
  if (details.sample) {
    const picture = element("img");
    picture.src = details.sample;
    picture.alt = `${text.value}, drawn in ${details.name}`;
    sample.replaceChildren(picture);
  } else {
    sample.replaceChildren(element("p", "hint", `No sample: ${details.noSample}.`));
  }
  // A font of a source folder, drawn: a variation of it can be made there.
  byId("variation").hidden = details.folder === null || details.height === undefined;
}

askDetails();
