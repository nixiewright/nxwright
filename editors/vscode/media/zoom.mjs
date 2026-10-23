// The zoom bar of the page preview's and the simulator panel's webviews:
// zoom out, the level, which goes back to 100 percent, zoom in, and Fit,
// the highest level at which the page fits the view. Ctrl with the mouse
// wheel over the canvas zooms about the pointer. The canvas keeps the
// page's own pixels: only its size on the screen changes, sharp from 100
// percent up, smoothed below (zoom-model.mjs). Each webview keeps its level
// in VS Code's webview state, so that it comes back when its tab shows again.
import { element } from "./elements.mjs";
import { fittingLevel, scrollToKeep, smoothedAt, zoomedIn, zoomedOut } from "./zoom-model.mjs";

export class ZoomBar {
  // Puts the bar's buttons in `bar`, to zoom `canvas`, keeping the level in
  // the state of `vscode`, the webview's API. `onZoom(level)` is called
  // once the level changes and the canvas has its new size.
  constructor(bar, canvas, vscode, onZoom) {
    this.canvas = canvas;
    this.vscode = vscode;
    this.onZoom = onZoom;
    this.level = vscode.getState()?.zoom ?? 1;
    this.size = undefined;       // the page's {width, height}, once shown
    const button = (text, title, act) => {
      const made = element("button", "", text);
      made.title = title;
      made.addEventListener("click", act);
      bar.append(made);
      return made;
    };
    button("-", "Zoom out", () => this.set(zoomedOut(this.level)));
    this.label = button("", "Back to 100%", () => this.set(1));
    button("+", "Zoom in", () => this.set(zoomedIn(this.level)));
    button("Fit", "The highest level at which the page fits the view", () => this.fit());
    canvas.addEventListener("wheel", (event) => {
      if (event.ctrlKey) {
        event.preventDefault();
        this.set(event.deltaY < 0 ? zoomedIn(this.level) : zoomedOut(this.level), event);
      }
    }, { passive: false });
    this.label.textContent = `${Math.round(this.level * 100)}%`;
  }

  // Shows the page, `width` by `height` pixels, at the level.
  show(width, height) {
    this.size = { width, height };
    this.canvas.style.width = `${width * this.level}px`;
    this.canvas.style.height = `${height * this.level}px`;
    this.canvas.style.imageRendering = smoothedAt(this.level) ? "auto" : "pixelated";
  }

  // Zooms to `level`; about the point of `pointer`, a mouse event over the
  // canvas, when given, so that the page's point under it stays there.
  set(level, pointer = undefined) {
    const old = this.level;
    if (level === old) {
      return;
    }
    this.level = level;
    this.vscode.setState({ ...(this.vscode.getState() ?? {}), zoom: level });
    this.label.textContent = `${Math.round(level * 100)}%`;
    if (this.size) {
      this.show(this.size.width, this.size.height);
    }
    this.onZoom(level);
    if (pointer) {
      window.scrollBy(scrollToKeep(pointer.offsetX, old, level),
                      scrollToKeep(pointer.offsetY, old, level));
    }
  }

  // Zooms to the highest level at which the page fits the view, below and
  // right of where the canvas starts, a margin as wide as the body's left.
  fit() {
    if (!this.size) {
      return;
    }
    const place = this.canvas.getBoundingClientRect();
    const left = place.left + window.scrollX;
    const top = place.top + window.scrollY;
    this.set(fittingLevel(this.size.width, this.size.height,
                          document.documentElement.clientWidth - 2 * left,
                          window.innerHeight - top - left));
  }
}
