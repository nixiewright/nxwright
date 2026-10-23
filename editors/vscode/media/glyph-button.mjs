// A text button with a glyph (media/glyphs.mjs), as the side bar's webview
// sections draw their main actions.
import { GLYPHS } from "./glyphs.mjs";

const SVG = "http://www.w3.org/2000/svg";

// Returns the drawing of a glyph, hidden from screen readers, which read
// the button's text or label instead.
export function glyphDrawing(glyph) {
  const drawing = document.createElementNS(SVG, "svg");
  drawing.setAttribute("viewBox", "0 0 16 16");
  drawing.setAttribute("aria-hidden", "true");
  // The glyphs are the extension's own drawings, never text from elsewhere.
  drawing.innerHTML = GLYPHS[glyph];
  return drawing;
}

// Returns a button with `glyph` before `text`, in the style `className`, if
// given. `data` becomes its data attributes, such as { command }, the
// command a click on it asks for.
export function glyphButton(data, glyph, text, className) {
  const button = document.createElement("button");
  Object.assign(button.dataset, data);
  if (className) {
    button.className = className;
  }
  const label = document.createElement("span");
  label.textContent = text;
  button.append(glyphDrawing(glyph), label);
  return button;
}
