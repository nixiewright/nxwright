// The page preview's webview: paints the drawings the extension sends it
// (src/preview.ts), with the notes that come with them, and edits the page:
//  - a click selects the topmost component under the pointer, and the
//    canvas keeps the keyboard; Ctrl with a click, Cmd on a Mac, adds a
//    component to the selection or takes it out, and a drag that starts
//    where only the page is draws a box, selecting every component it
//    overlaps; with Shift, a drag draws the box wherever it starts, even on
//    a component. The component selected first is the anchor, which the side
//    bar shows, and which arranging goes by (arranging.mjs);
//  - dragging a selected component moves every selected one, and dragging
//    the handles of one alone resizes it; the arrow keys move them by one
//    pixel, or ten with Shift; Escape keeps the anchor alone;
//  - a double click opens the code of a component's default event, the
//    first of its events that has code, else its first;
//  - F12 opens the page file as text at the first selected component's
//    table, or the page's;
//  - the right-click menu, VS Code's own, opens an event of the first
//    selected component, picked from a list, shows its attributes, and
//    opens its table as F12 does;
//    adds a component where it opened; deletes, cuts, copies, and
//    duplicates the selected components, and pastes, as the Delete key and
//    Ctrl with X, C, V, and D do, Cmd on a Mac, and pastes where it opened
//    or where the components were copied from; clears their code
//    (src/pageComponents.ts); aligns, sizes, spaces, and moves them up or
//    down the ID order (src/preview.ts); locks and unlocks them; and groups
//    and ungroups them;
//  - a locked component shows a padlock, and is not moved: it has no
//    handles, and dragging, the arrow keys, and arranging move the other
//    selected components alone;
//  - the members of the selected components' groups are tinted, and
//    dragging or the arrow keys move them along, each once, a locked member
//    staying where it is (arranging.mjs).
// The page is painted on one canvas, at its own size, which the toolbar's
// zoom shows larger or smaller (zoom.mjs). A second canvas, laid over the
// part of it the window shows, holds the selection and, when the toolbar's
// toggle shows them, the components' names. It is drawn at the screen's own
// resolution, so that the names and the handles keep their size and stay
// legible at every level, and covers no more than the window, so that its
// pixels stay few however far the page is zoomed. The mouse's position is
// divided back to the page's pixels. The components without a place, such
// as timers and variables, are tiles of a strip under the page, which
// select them, Ctrl with a click adding them, and open their default event
// as the page does. Each change goes to the extension, which edits the file
// through the editor, so undo works; the drawing that follows shows it. The
// anchor's properties show in nxwright's side bar (media/properties.mjs).
import { arrangement, boxBetween, groupMembers, lockedAmong, movedTogether,
  movingNames, overlappingBox } from "./arranging.mjs";
import { clickOfSmallBox, componentAt, dragged, handleAt, handlePoints, idleTouchCaptures,
  imageSources, loadImage, NAME_COLOURS, NAME_FONT, nudged, onGrid, paint, paintNames,
  paintPadlocks, pressStarts } from "./preview-model.mjs";
import { element } from "./elements.mjs";
import { ZoomBar } from "./zoom.mjs";
import { inView, shownPart } from "./zoom-model.mjs";

const vscode = acquireVsCodeApi();
// A Mac's Delete key is the one browsers call Backspace. Elsewhere Backspace
// erases a character, and deletes no component.
const ON_A_MAC = /mac/i.test(navigator.userAgentData?.platform ?? navigator.platform);
const canvas = document.getElementById("page");
const context = canvas.getContext("2d");
const overlay = document.getElementById("overlay");
const overlayContext = overlay.getContext("2d");
const namesToggle = document.getElementById("names");
const strip = document.getElementById("strip");
const notes = document.getElementById("notes");
const zoom = new ZoomBar(document.getElementById("zoom"), canvas, vscode, () => sizeOverlay());
const SELECTION_COLOUR = "#3794ff";
// The wash over the members of the selected components' groups, a khaki
// near the Editor's.
const GROUP_TINT = "rgba(222, 210, 120, 0.45)";
// A box smaller than this, in the view's pixels, is a click.
const LEAST_BOX = 3;

let drawing = undefined;
let images = new Map();
// Loaded images by their source, kept while drawings use them.
let loaded = new Map();
// Only the latest drawing is painted, should an older one finish loading later.
let latest = 0;
let selected = undefined;    // the anchor: the object selected first
let others = [];             // the components selected with it, in the order selected
let grid = 1;                // the grid edges snap to, 1 for none
// While dragging: {handle, start, from, rects, pressed}, `from` and `rects`
// the selected components' rectangles before and during the drag, and
// `pressed` the component the drag started on.
let drag = undefined;
// While drawing a box: {start, end, adding, pressed, onHandle}, its corners
// in the page's pixels, `pressed` what the press landed on, and `onHandle`
// whether it landed on a handle.
let box = undefined;
let namesShown = false;      // whether the components' names are written on the page
let pageUri = undefined;     // the page file's URI, for the right-click menu's commands

window.addEventListener("message", async (event) => {
  const message = event.data;
  if (message.type === "drawing") {
    const asked = ++latest;
    const ready = await loadImages(imageSources(message.drawing, message.pictureUris,
                                                     message.pictureMasks));
    if (asked !== latest) {
      return;
    }
    drawing = message.drawing;
    images = ready;
    grid = message.grid || 1;
    canvas.width = drawing.width;
    canvas.height = drawing.height;
    zoom.show(drawing.width, drawing.height);
    // A page without background shows the checkerboard through it.
    canvas.classList.toggle("transparent", Boolean(drawing.transparent));
    if (selected && !isObject(selected)) {
      selected = undefined;
      others = [];
    }
    others = others.filter(isObject);
    paint(context, drawing, images);
    sizeOverlay();
    showStrip();
    showNotes(drawing.notes);
  } else if (message.type === "error") {
    // The page file does not read, such as while it is half typed: the last
    // drawing stays, under a note saying why.
    showNotes([`Not redrawn: ${message.error}`]);
  } else if (message.type === "select") {
    // The anchor chosen elsewhere selects it alone; the extension also
    // sends back the anchor chosen here, which keeps the others.
    if (message.name !== selected) {
      selected = message.name;
      others = [];
    }
    showSelection();
  } else if (message.type === "page") {
    pageUri = message.uri;
  } else if (message.type === "names") {
    namesShown = message.shown;
    namesToggle.checked = namesShown;
    paintOverlay();
  } else if (message.type === "arrange") {
    arrange(message.how);
  }
});

// The window's size, the screen's resolution, and what the window shows of
// the page change the overlay.
window.addEventListener("resize", () => sizeOverlay());
window.addEventListener("scroll", () => sizeOverlay());

// Lays the overlay over the part of the page's view the window shows, at
// the screen's own resolution, and paints it.
function sizeOverlay() {
  if (!drawing) {
    return;
  }
  const scale = window.devicePixelRatio || 1;
  const part = shownPart(canvas.getBoundingClientRect(), window.innerWidth, window.innerHeight);
  overlay.style.left = `${part.x}px`;
  overlay.style.top = `${part.y}px`;
  overlay.style.width = `${part.w}px`;
  overlay.style.height = `${part.h}px`;
  overlay.width = Math.round(part.w * scale);
  overlay.height = Math.round(part.h * scale);
  // The overlay's context draws in the view's pixels, from the view's corner.
  overlayContext.setTransform(scale, 0, 0, scale, -part.x * scale, -part.y * scale);
  paintOverlay();
}

// Paints the overlay: the names when shown, then the selected components'
// frames, where a drag has them, and the box being drawn. With one
// component selected, its frame has handles; with several, the anchor's
// frame is solid and the others' dashed.
function paintOverlay() {
  if (!drawing) {
    return;
  }
  overlayContext.save();
  overlayContext.setTransform(1, 0, 0, 1, 0, 0);
  overlayContext.clearRect(0, 0, overlay.width, overlay.height);
  overlayContext.restore();
  // The tint goes first, so that the names and padlocks over it stay legible.
  paintGroupTint();
  if (namesShown) {
    paintNames(overlayContext, drawing, zoom.level);
  }
  paintPadlocks(overlayContext, drawing, zoom.level);
  overlayContext.save();
  overlayContext.strokeStyle = SELECTION_COLOUR;
  overlayContext.fillStyle = SELECTION_COLOUR;
  overlayContext.lineWidth = 1;
  // During a drag, the components it moves are where it has them; locked
  // ones stay where they are.
  const rects = placedSelection().map((name) =>
    drag?.rects.find((rect) => rect.name === name) ?? rectOf(name));
  if (aloneWithHandles() && !isLocked(selected)) {
    frame(rects[0], true);
    for (const [, x, y] of handlePoints(inView(rects[0], zoom.level))) {
      overlayContext.fillRect(x - 3, y - 3, 6, 6);
    }
  } else {
    rects.forEach((rect, index) => frame(rect, index > 0 || rect.name !== selected));
  }
  if (rects.length === 0 && isPage(selected)) {
    frame(rectOf(selected), true);
  }
  if (box) {
    frame(boxBetween(box.start.x, box.start.y, box.end.x, box.end.y), true);
  }
  overlayContext.restore();
}

// Tints every member of the selected components' groups, under the names,
// the padlocks, and the selection's frames; during a drag, where it has them.
function paintGroupTint() {
  overlayContext.save();
  overlayContext.fillStyle = GROUP_TINT;
  for (const name of groupMembers(drawing.components, placedSelection())) {
    const rect = inView(drag?.rects.find((each) => each.name === name) ?? rectOf(name),
                        zoom.level);
    overlayContext.fillRect(rect.x, rect.y, rect.w, rect.h);
  }
  overlayContext.restore();
}

// Strokes the frame of a page's rectangle where the view shows it.
function frame(pageRect, dashed) {
  const rect = inView(pageRect, zoom.level);
  overlayContext.setLineDash(dashed ? [4, 2] : []);
  overlayContext.strokeRect(rect.x + 0.5, rect.y + 0.5, rect.w - 1, rect.h - 1);
}

// Returns the page's point under a mouse event over the canvas.
function pointOf(event) {
  return { x: event.offsetX / zoom.level, y: event.offsetY / zoom.level };
}

// Returns the rectangle {name, x, y, w, h} of a component with a place.
function rectOf(name) {
  const found = drawing?.components.find((component) => component.name === name);
  return found && { name, x: found.x, y: found.y, w: found.w, h: found.h };
}

// Whether the drawing has the object `name`, on the page or in the strip.
function isObject(name) {
  return [...drawing.components, ...drawing.unplaced].some((entry) => entry.name === name);
}

function isPage(name) {
  return name !== undefined && name === drawing?.components[0]?.name;
}

// Whether `name` is a component on the page, which moves: neither the page
// itself nor a component of the strip, which has no place.
function canMove(name) {
  const found = drawing?.components.find((component) => component.name === name);
  return Boolean(found) && found.type !== "page";
}

// Whether `name` is a locked component of the page, which does not move.
function isLocked(name) {
  return Boolean(drawing?.components.find((component) => component.name === name)?.locked);
}

// The names among `names` of locked components, which moves and
// arrangements leave where they are (arranging.mjs).
function lockedNames(names) {
  return lockedAmong(drawing.components, names);
}

// The selection, the anchor first; the page counts only when alone.
function selection() {
  return selected === undefined ? [] : [selected, ...others];
}

// The selected components, the page aside: those menus and keys act on.
function selectedComponents() {
  return selection().filter((name) => !isPage(name));
}

// The selected components with a place on the page, the anchor first.
function placedSelection() {
  return selection().filter(canMove);
}

// Whether one component alone is selected, on the page, which has handles.
function aloneWithHandles() {
  return selection().length === 1 && canMove(selected);
}

// Selects `name` alone, or nothing.
function select(name) {
  selectMany(name === undefined ? [] : [name]);
}

// Selects `names`, the first being the anchor.
function selectMany(names) {
  const anchor = names[0];
  others = names.slice(1);
  const changed = anchor !== selected;
  selected = anchor;
  showSelection();
  if (changed) {
    vscode.postMessage({ type: "select", name: anchor });
  }
}

// Adds a component to the selection, or takes it out (Ctrl with a click).
function toggle(name) {
  if (name === undefined || isPage(name)) {
    return;
  }
  const names = selection().filter((each) => !isPage(each));
  selectMany(names.includes(name) ? names.filter((each) => each !== name) : [...names, name]);
}

function showSelection() {
  paintOverlay();
  const names = selection();
  for (const tile of strip.children) {
    tile.classList.toggle("selected", names.includes(tile.dataset.name));
  }
}

// Whether a mouse or key event holds Ctrl, or Cmd on a Mac.
function withCommandKey(event) {
  return ON_A_MAC ? event.metaKey : event.ctrlKey;
}

// Sets what VS Code passes the commands of the right-click menu opened on
// `target`: the menu's section, "page" or "strip", the page file, the
// selected components, the page aside ("component", the first, tells the
// menu there are some), whether several and three or more of them have a
// place, which arranging and grouping need, those with a place, which
// locking and grouping take, whether some of those are locked, some
// unlocked, and some in a group, and on the page, the point clicked, on the
// grid (package.json's webview/context menu).
function setMenuContext(target, section, point = undefined) {
  const names = selectedComponents();
  const placed = placedSelection();
  target.dataset.vscodeContext = JSON.stringify({
    webviewSection: section, page: pageUri, component: names[0], components: names,
    placedComponents: placed, several: placed.length > 1, spaceable: placed.length > 2,
    locked: placed.some(isLocked), unlocked: placed.some((name) => !isLocked(name)),
    grouped: groupMembers(drawing.components, placed).length > 0, ...point,
    // Cut, copy, and paste of text have nothing to work on here.
    preventDefaultContextMenuItems: true,
  });
}

// Shows a tile for each component without a place, in ID order: its name,
// in its scope's colours as on the page, and its type. Of several touch
// captures, those that never run are dimmed.
function showStrip() {
  strip.textContent = "";
  const idle = idleTouchCaptures(drawing.unplaced);
  for (const entry of drawing.unplaced) {
    const tile = element("div", "tile");
    tile.dataset.name = entry.name;
    const name = element("span", "name", entry.name);
    const colours = entry.global ? NAME_COLOURS.global : NAME_COLOURS.local;
    name.style.font = NAME_FONT;
    name.style.color = colours.text;
    name.style.background = colours.back;
    tile.append(name, element("span", "type", entry.type));
    if (idle.has(entry.name)) {
      tile.classList.add("idle");
      tile.title = "Only the last touch capture of a page runs: this one never does.";
    }
    tile.addEventListener("mousedown", (event) => {
      if (event.button === 0) {
        // The canvas keeps the keyboard, as a click on the page leaves it.
        event.preventDefault();
        canvas.focus({ preventScroll: true });
        if (withCommandKey(event)) {
          toggle(entry.name);
        } else {
          select(entry.name);
        }
      }
    });
    tile.addEventListener("dblclick", () => {
      vscode.postMessage({ type: "openDefaultEvent", name: entry.name });
    });
    // A right click outside the selection selects its component, as a
    // click does, before VS Code's menu opens.
    tile.addEventListener("contextmenu", () => {
      if (!selection().includes(entry.name)) {
        select(entry.name);
      }
      setMenuContext(tile, "strip");
    });
    strip.appendChild(tile);
  }
  strip.hidden = drawing.unplaced.length === 0;
  showSelection();
}

namesToggle.addEventListener("change", () => {
  // The extension remembers the choice, and sends it to every preview.
  vscode.postMessage({ type: "showNames", shown: namesToggle.checked });
});

canvas.addEventListener("mousedown", (event) => {
  // Taking the focus would scroll a canvas larger than the view to its top.
  canvas.focus({ preventScroll: true });
  // Only the main button selects and drags.
  if (event.button !== 0) {
    return;
  }
  const point = pointOf(event);
  const name = componentAt(drawing, point.x, point.y);
  const placed = placedSelection();
  // Handles keep their size in the view: one is found where the view shows it.
  const handle = aloneWithHandles() && !isLocked(selected)
    ? handleAt(inView(rectOf(selected), zoom.level), event.offsetX, event.offsetY) : undefined;
  const starts = pressStarts({ onPage: isPage(name), onSelected: placed.includes(name),
                               onHandle: handle !== undefined, shift: event.shiftKey,
                               command: withCommandKey(event) });
  if (starts === "box" || starts === "adding box") {
    box = { start: point, end: point, adding: starts === "adding box", pressed: name,
            onHandle: handle !== undefined };
  } else if (starts === "toggle") {
    toggle(name);
  } else if (starts === "drag") {
    // Pressed on any selected component, locked or not, a drag moves those
    // not locked, and the other members of their groups; a handle resizes
    // its component alone.
    const moving = handle ? placed : movingNames(drawing.components, placed);
    drag = { handle, start: point, from: moving.map((each) => rectOf(each)), rects: [],
             pressed: name };
  } else {
    select(name);
  }
});

canvas.addEventListener("mousemove", (event) => {
  const point = pointOf(event);
  if (drag) {
    const dx = point.x - drag.start.x, dy = point.y - drag.start.y;
    if (drag.handle) {
      const [alone] = drag.from;
      drag.rects = [{ name: alone.name, ...dragged(alone, drag.handle, dx, dy, grid) }];
    } else {
      // The first that moves lands on the grid; the others keep their places from it.
      const locked = lockedNames(drag.from.map((rect) => rect.name));
      const lead = drag.from.find((rect) => !locked.has(rect.name));
      const step = lead && dragged(lead, undefined, dx, dy, grid);
      drag.rects = lead ? movedTogether(drag.from, step.x - lead.x, step.y - lead.y, locked) : [];
    }
    paintOverlay();
  } else if (box) {
    box.end = point;
    paintOverlay();
  }
});

window.addEventListener("mouseup", () => {
  if (drag) {
    const { rects, handle, pressed } = drag;
    drag = undefined;
    const changed = rects.filter((rect) => moved(rectOf(rect.name), rect));
    // A click on one of several selected, which moved nothing, selects it alone.
    if (changed.length === 0 && !handle && selection().length > 1) {
      select(pressed);
    } else {
      placeAll(changed);
    }
  } else if (box) {
    finishBox();
  }
});

// Selects what a box overlaps: in place of the selection, or added to it
// with Ctrl. A box too small to be one is a click on what its press landed
// on (clickOfSmallBox), so Shift with a click selects as a click does.
function finishBox() {
  const { start, end, adding, pressed, onHandle } = box;
  box = undefined;
  const drawn = boxBetween(start.x, start.y, end.x, end.y);
  if (drawn.w * zoom.level < LEAST_BOX && drawn.h * zoom.level < LEAST_BOX) {
    const click = clickOfSmallBox({ adding, onPage: isPage(pressed), onHandle });
    if (click === "select") {
      select(pressed);
    } else if (click === "toggle") {
      toggle(pressed);
    } else {
      paintOverlay();
    }
    return;
  }
  const overlapped = overlappingBox(drawing.components, drawn);
  if (adding) {
    const names = selectedComponents();
    selectMany([...names, ...overlapped.filter((name) => !names.includes(name))]);
  } else {
    selectMany(overlapped.length > 0 ? overlapped : [drawing.components[0].name]);
  }
}

canvas.addEventListener("contextmenu", (event) => {
  const point = pointOf(event);
  const name = componentAt(drawing, point.x, point.y);
  // A right click outside the selection selects what it is on, as a click does.
  if (!selection().includes(name)) {
    select(name);
  }
  setMenuContext(canvas, "page", { x: onGrid(point.x, grid), y: onGrid(point.y, grid) });
});

canvas.addEventListener("dblclick", (event) => {
  const { x, y } = pointOf(event);
  const name = componentAt(drawing, x, y);
  if (name) {
    vscode.postMessage({ type: "openDefaultEvent", name });
  }
});

canvas.addEventListener("keydown", (event) => {
  const names = selectedComponents();
  // The Delete key deletes the selected components, on the page or in the
  // strip; never the page.
  if ((event.key === "Delete" || (ON_A_MAC && event.key === "Backspace")) && names.length > 0) {
    event.preventDefault();
    vscode.postMessage({ type: "delete", names });
    return;
  }
  if (event.key === "Escape" && others.length > 0) {
    event.preventDefault();
    selectMany([selected]);
    return;
  }
  // F12, VS Code's key for Go to Definition: the page file's table of the
  // first selected component, or of the page.
  if (event.key === "F12" && !event.shiftKey && !event.altKey && !withCommandKey(event)) {
    event.preventDefault();
    vscode.postMessage({ type: "goToDefinition", name: names[0] });
    return;
  }
  // Ctrl, or Cmd on a Mac, with X, C, V, or D: cut, copy, paste, duplicate.
  // Only the canvas listens, so the same keys in the side bar's fields edit
  // their text as usual.
  const command = event.altKey || event.shiftKey || !withCommandKey(event)
    ? undefined : { x: "cut", c: "copy", v: "paste", d: "duplicate" }[event.key.toLowerCase()];
  if (command) {
    event.preventDefault();
    if (command === "paste" || names.length > 0) {
      vscode.postMessage({ type: command, names });
    }
    return;
  }
  const moving = movingNames(drawing.components, placedSelection());
  const rects = moving.map((name) => rectOf(name));
  const step = rects.length > 0 && nudged(rects[0], event.key, event.shiftKey);
  if (step) {
    event.preventDefault();
    placeAll(movedTogether(rects, step.x - rects[0].x, step.y - rects[0].y, lockedNames(moving)));
  }
});

// Arranges the selected components with a place, as the right-click
// menu's command `how` says (src/preview.ts): an alignment of arranging.mjs,
// "sameWidth", "sameHeight", "sameSize", "spaceAcross", or "spaceDown".
function arrange(how) {
  const rects = placedSelection().map((name) => rectOf(name));
  if (rects.length >= 2) {
    placeAll(arrangement(rects, how, lockedNames(placedSelection()))
      .filter((rect) => moved(rectOf(rect.name), rect)));
  }
}

function moved(from, to) {
  return from.x !== to.x || from.y !== to.y || from.w !== to.w || from.h !== to.h;
}

// Shows the components' frames at their new places until the drawing that
// follows the edit comes, and asks for the edit, one for them all.
function placeAll(rects) {
  if (rects.length === 0) {
    paintOverlay();
    return;
  }
  const places = {};
  for (const { name, x, y, w, h } of rects) {
    Object.assign(drawing.components.find((entry) => entry.name === name), { x, y, w, h });
    places[name] = { x, y, w, h };
  }
  paintOverlay();
  vscode.postMessage({ type: "place", places });
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

function showNotes(lines) {
  notes.textContent = "";
  for (const line of lines) {
    notes.appendChild(element("li", "", line));
  }
}

vscode.postMessage({ type: "ready" });
