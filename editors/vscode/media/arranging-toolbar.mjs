// The page preview's arranging toolbar, a row of icon buttons for the
// arranging commands of the right-click menu, so that a command can be
// repeated without reopening the menu. arranging-toolbar-model.mjs lists the
// buttons. A button that does not apply to the selection is greyed out rather
// than hidden, so that the others keep their places.
import { element } from "./elements.mjs";
import { glyphDrawing } from "./glyph-button.mjs";
import { isEnabled, TOOLBAR_GROUPS } from "./arranging-toolbar-model.mjs";

export class ArrangingToolbar {
  // Puts the buttons in `bar`, each group in a span of its own. A click
  // calls `act(entry)` with the button's entry of TOOLBAR_GROUPS. Pressing
  // a button with the mouse gives the keyboard focus to `canvas`, the page's
  // canvas, rather than to the button, so that the arrow keys still move the
  // selection.
  constructor(bar, canvas, act) {
    this.buttons = [];
    for (const group of TOOLBAR_GROUPS) {
      const span = element("span", "group");
      for (const entry of group) {
        const made = element("button");
        made.title = entry.title;
        made.setAttribute("aria-label", entry.title);
        made.disabled = true;
        made.append(glyphDrawing(entry.glyph));
        made.addEventListener("mousedown", (event) => {
          event.preventDefault();
          canvas.focus({ preventScroll: true });
        });
        made.addEventListener("click", () => act(entry));
        span.append(made);
        this.buttons.push([made, entry]);
      }
      bar.append(span);
    }
  }

  // Enables the buttons that apply to `selection`, and disables the others.
  // `selection` has the form that `isEnabled` takes.
  update(selection) {
    for (const [made, entry] of this.buttons) {
      made.disabled = !isEnabled(entry, selection);
    }
  }
}
