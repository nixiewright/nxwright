// The page preview's painting, kept apart from the webview so that Node's
// test runner can check it. A drawing comes from the language server's
// nxwright/pageDrawing request (nxwright/drawing/page_drawing.py says what
// it holds): the server knows what each attribute means, and this only
// paints its shapes, in order.

import { inView } from "./zoom-model.mjs";

// The colour of outlines: hotspots, and components of types not drawn in full.
export const OUTLINE_COLOUR = "#ff40ff";
// A component's `aph` when it is drawn wholly opaque (page_drawing.py).
export const OPAQUE = 127;

// Returns the images a drawing needs, as [key, source, how it loads, its
// mask or undefined]: each picture by its name (pictureKey), its source the
// address `pictureUris` gives it, loaded "picture", in the screen's colours,
// or "opaque", flattened on white first, where its shape says the screen
// keeps no alpha (inScreenColours), or "card", a file of an SD card, as it
// is, with the mask `pictureMasks` gives it applied (withMask), as the
// Editor's simulator shows such a file in its own colours; each text
// picture by its data URL, which is also its source, loaded "text", as it
// is, being drawn in its colour attributes', which already are.
export function imageSources(drawing, pictureUris, pictureMasks = {}) {
  const sources = new Map();
  for (const shape of drawing.shapes) {
    if (shape.kind === "picture" && pictureUris[shape.picture]) {
      const how = shape.card ? "card" : shape.opaque ? "opaque" : "picture";
      sources.set(pictureKey(shape), [pictureUris[shape.picture], how,
                                      shape.card ? pictureMasks[shape.picture] : undefined]);
    } else if (shape.kind === "text") {
      sources.set(shape.image, [shape.image, "text", undefined]);
    }
  }
  return [...sources].map(([key, [source, how, mask]]) => [key, source, how, mask]);
}

// Gives RGBA pixels, as a canvas's getImageData gives them, the alpha of
// `mask`'s pixels, of the same size: a picture file of an SD card in
// PictureBox's form keeps its picture as JPEG and its transparency apart.
export function withMask(pixels, mask) {
  for (let index = 3; index < pixels.length; index += 4) {
    pixels[index] = mask[index];
  }
}

// The key a picture shape's image is kept by: its picture's name, marked
// when the screen keeps no alpha, as the same file then shows otherwise.
function pictureKey(shape) {
  return shape.opaque ? `${shape.picture}#opaque` : shape.picture;
}

// Converts RGBA pixels, as a canvas's getImageData gives them, to the colours
// the screen shows a picture in, as the Editor's simulator shows them. The
// screen keeps 5 bits of red, 6 of green, and 5 of blue. The Editor widens
// them back to 8 by repeating their top bits: red 232 keeps 29, shown as 239.
// Alpha stays as it is, but when `opaque`, on a screen that keeps no alpha:
// there the build first multiplies each channel by alpha, rounding, and
// adds white for the transparent share (screen_copy.py, stored_pixels), so
// the picture covers what is under it.
export function screenColours(pixels, opaque = false) {
  for (let index = 0; index < pixels.length; index += 4) {
    if (opaque) {
      const alpha = pixels[index + 3];
      for (let channel = index; channel < index + 3; channel++) {
        pixels[channel] = Math.floor((pixels[channel] * alpha + 127) / 255) + 255 - alpha;
      }
      pixels[index + 3] = 255;
    }
    pixels[index] = (pixels[index] & 0xf8) | (pixels[index] >> 5);
    pixels[index + 1] = (pixels[index + 1] & 0xfc) | (pixels[index + 1] >> 6);
    pixels[index + 2] = (pixels[index + 2] & 0xf8) | (pixels[index + 2] >> 5);
  }
}

// Loads an image from `source`, resolving to it, or to undefined when it
// cannot load, as `how` says (imageSources): a picture comes as a canvas in
// the screen's colours, flattened on white when "opaque".
//
// A canvas drawn from another origin's image cannot be read. So a picture
// is fetched for cross-origin use, which VS Code's webview files allow. A
// picture that does not load that way is loaded again as a plain image, and
// one whose pixels still cannot be read keeps its PNG's colours, rather
// than being left out or stopping the painting.
export function loadImage(source, how, mask = undefined) {
  if (how === "card") {
    return loadCardPicture(source, mask);
  }
  const picture = how !== "text";
  return new Promise((resolve) => {
    const image = new Image();
    if (picture) {
      image.crossOrigin = "anonymous";
    }
    image.onload = () => {
      try {
        resolve(picture ? inScreenColours(image, how === "opaque") : image);
      } catch {
        resolve(image);
      }
    };
    image.onerror = () => resolve(picture ? loadImage(source, "text") : undefined);
    image.src = source;
  });
}

// Loads a picture file of an SD card from `source` as it is, and, when it
// comes with a mask, as a canvas with the mask's alpha (withMask). Both are
// data URLs, so the canvas can be read.
async function loadCardPicture(source, mask) {
  const image = await loadImage(source, "text");
  const masking = image && mask ? await loadImage(mask, "text") : undefined;
  if (!masking) {
    return image;
  }
  // As loadImage: a picture whose pixels cannot be read shows unmasked,
  // rather than stopping the painting.
  try {
    const pixels = pixelsOf(image);
    withMask(pixels.data, pixelsOf(masking).data);
    const canvas = document.createElement("canvas");
    canvas.width = pixels.width;
    canvas.height = pixels.height;
    canvas.getContext("2d").putImageData(pixels, 0, 0);
    return canvas;
  } catch {
    return image;
  }
}

// Returns a loaded image's pixels, as getImageData gives them.
function pixelsOf(image) {
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext("2d");
  context.drawImage(image, 0, 0);
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

// Returns a loaded picture as a canvas, in the screen's colours, flattened
// on white when `opaque` (screenColours).
function inScreenColours(image, opaque) {
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext("2d");
  context.drawImage(image, 0, 0);
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
  screenColours(pixels.data, opaque);
  context.putImageData(pixels, 0, 0);
  return canvas;
}

// Paints a drawing on a canvas's 2D context, its images loaded and kept in
// `images` by the keys imageSources gives. A picture not loaded is left out.
// `backdrop`, a canvas, is painted first: what a page without background is
// drawn over. A "backdrop" shape shows its part of it again, or black
// without one, as after a start.
export function paint(context, drawing, images, backdrop = null) {
  context.clearRect(0, 0, drawing.width, drawing.height);
  if (backdrop) {
    context.drawImage(backdrop, 0, 0);
  }
  for (const shape of drawing.shapes) {
    const { x, y, w, h } = shape;
    // A shape of a translucent component is laid over what is under it that
    // opaque, part by part, as the Editor's simulator blends one.
    context.globalAlpha = shape.aph === undefined ? 1 : shape.aph / OPAQUE;
    if (shape.kind === "backdrop" && backdrop) {
      context.drawImage(backdrop, x, y, w, h, x, y, w, h);
    } else if (shape.kind === "backdrop") {
      context.fillStyle = "#000000";
      context.fillRect(x, y, w, h);
    } else if (shape.kind === "colour") {
      context.fillStyle = shape.colour;
      context.fillRect(x, y, w, h);
    } else if (shape.kind === "picture" && shape.rotation) {
      const image = images.get(pictureKey(shape));
      if (image) {
        paintTurnedBack(context, image, shape);
      }
    } else if (shape.kind === "picture") {
      const image = images.get(pictureKey(shape));
      if (image) {
        // The part of the picture from (sx, sy), as much of it as the
        // picture holds and the rectangle takes.
        const width = Math.min(w, image.width - shape.sx);
        const height = Math.min(h, image.height - shape.sy);
        if (width > 0 && height > 0) {
          context.drawImage(image, shape.sx, shape.sy, width, height, x, y, width, height);
        }
      }
    } else if (shape.kind === "text") {
      const image = images.get(shape.image);
      if (image) {
        paintFrame(context, image, shape);
      }
    } else if (shape.kind === "plainText") {
      paintPlainText(context, shape);
    } else if (shape.kind === "outline") {
      context.strokeStyle = OUTLINE_COLOUR;
      context.lineWidth = 1;
      context.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
      context.fillStyle = OUTLINE_COLOUR;
      context.font = "11px sans-serif";
      context.textAlign = "left";
      context.textBaseline = "top";
      context.fillText(shape.label, x + 3, y + 3);
    }
  }
  context.globalAlpha = 1;
}

// How dark the screen shows, from 0 to 1, as a black layer's opacity over a
// simulation's drawing: `dim` 80 shows every colour at 80%, and a sleeping
// screen is dark. A page file's drawing has no `dim`, and shows as it is.
export function darkness(drawing) {
  if (drawing.asleep) {
    return 1;
  }
  const dim = drawing.dim ?? 100;
  return Math.min(Math.max((100 - dim) / 100, 0), 1);
}

// Paints a simulation's drawing: as `paint` does, then darkened by `darkness`.
export function paintScreen(context, drawing, images, backdrop = null) {
  paint(context, drawing, images, backdrop);
  dimScreen(context, drawing);
}

// Darkens what is painted by `darkness`.
export function dimScreen(context, drawing) {
  const dark = darkness(drawing);
  if (dark > 0) {
    context.fillStyle = `rgba(0, 0, 0, ${dark})`;
    context.fillRect(0, 0, drawing.width, drawing.height);
  }
}

// What a simulation's drawing is drawn over, as the screen draws its pages,
// given the start and entry of the last drawing painted (undefined at
// first):
//  - "black": the first drawing since the screen started, or a page with a
//    background, which covers the screen;
//  - "screen": a page without background just entered, over what the
//    screen showed;
//  - "same": the page shown, drawn again over what it was drawn over before.
export function backdropChoice(last, drawing) {
  if (!last || drawing.start !== last.start) {
    return "black";
  }
  if (drawing.entry === last.entry) {
    return "same";
  }
  return drawing.transparent ? "screen" : "black";
}

// Paints an animation's or a video's frame, its picture `image`, at
// `shape`'s x and y, cut to its w and h: the preview's, the simulator's, and
// the media viewer's (media/media-player.mjs). A frame is stored padded to
// whole blocks of 16 pixels at its right and bottom, the screen showing only
// its own size. One stored for a screen turned by `shape.rotation` degrees
// is padded, then turned (nxwright/project/media_files.py): it is turned
// back, so that its padding lies at its right and bottom again, then cut as
// an upright frame is (paintTurnedBack). The opacity the shape is painted
// at is left as paint() set it.
export function paintFrame(context, image, shape) {
  const { x, y, w, h, rotation } = shape;
  if (!rotation) {
    const width = Math.min(w, image.width);
    const height = Math.min(h, image.height);
    if (width > 0 && height > 0) {
      context.drawImage(image, 0, 0, width, height, x, y, width, height);
    }
    return;
  }
  paintTurnedBack(context, image, shape);
}

// Paints `image`, stored for a screen turned by `shape.rotation` degrees,
// turned back by as much, so that it shows upright: its top left corner at
// `shape`'s x and y, cut to its w and h. A video's frame (paintFrame), and
// an external picture's file, which the Nextion Editor's simulator showed
// so at 90, 180, and 270 degrees, whatever rotation the file was made for
// (nxwright/drawing/page_drawing.py). A frame's shape is the frame's size,
// so its padding is cut off; a file's is the component's, so its padding
// shows within it.
function paintTurnedBack(context, image, shape) {
  const { x, y, w, h, rotation } = shape;
  const across = rotation === 90 || rotation === 270;
  // The picture's size once turned back, its padding included.
  const width = across ? image.height : image.width;
  const height = across ? image.width : image.height;
  context.save();
  context.beginPath();
  context.rect(x, y, Math.min(w, width), Math.min(h, height));
  context.clip();
  context.translate(x + width / 2, y + height / 2);
  context.rotate(-rotation * Math.PI / 180);
  context.drawImage(image, -image.width / 2, -image.height / 2);
  context.restore();
}

// A text whose font cannot be drawn: in an ordinary font at its font's
// height, aligned as xcen and ycen say, cut to its rectangle.
function paintPlainText(context, shape) {
  const { x, y, w, h } = shape;
  context.save();
  context.beginPath();
  context.rect(x, y, w, h);
  context.clip();
  context.fillStyle = shape.colour;
  context.font = `${shape.size}px sans-serif`;
  context.textAlign = ["left", "center", "right"][shape.xcen] ?? "left";
  context.textBaseline = ["top", "middle", "bottom"][shape.ycen] ?? "top";
  const across = [x, x + w / 2, x + w][shape.xcen] ?? x;
  const down = [y, y + h / 2, y + h][shape.ycen] ?? y;
  context.fillText(shape.text, across, down);
  context.restore();
}

// The handles of a selected component, by the edges each moves: n, s, e, w,
// and the corners between them.
export const HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
// How far from a handle's centre, in pixels, the pointer still takes it.
const HANDLE_REACH = 4;

// Returns the centre of each handle of a rectangle, as [handle, x, y].
export function handlePoints(rect) {
  const across = { w: rect.x, "": rect.x + rect.w / 2, e: rect.x + rect.w };
  const down = { n: rect.y, "": rect.y + rect.h / 2, s: rect.y + rect.h };
  return HANDLES.map((handle) => {
    const vertical = handle.includes("n") ? "n" : handle.includes("s") ? "s" : "";
    const horizontal = handle.includes("w") ? "w" : handle.includes("e") ? "e" : "";
    return [handle, across[horizontal], down[vertical]];
  });
}

// Returns the handle of `rect` under the point (x, y), or undefined.
export function handleAt(rect, x, y) {
  const found = handlePoints(rect).find(([, hx, hy]) =>
    Math.abs(x - hx) <= HANDLE_REACH && Math.abs(y - hy) <= HANDLE_REACH);
  return found?.[0];
}

// Returns `value` on the nearest multiple of `grid`, or the nearest whole
// pixel when `grid` is 1, for none.
export function onGrid(value, grid) {
  return grid > 1 ? Math.round(value / grid) * grid : Math.round(value);
}

// Returns a rectangle {x, y, w, h} after dragging it by (dx, dy): moved, or,
// by a `handle`, resized at the edges it names. Each edge that moves lands on
// a multiple of `grid` (1 for none), and the rectangle stays at least
// LEAST_SIDE by LEAST_SIDE, the least the Editor takes.
export const LEAST_SIDE = 2;

export function dragged(rect, handle, dx, dy, grid) {
  const snap = (value) => onGrid(value, grid);
  if (!handle) {
    return { x: snap(rect.x + dx), y: snap(rect.y + dy), w: rect.w, h: rect.h };
  }
  let left = rect.x, top = rect.y, right = rect.x + rect.w, bottom = rect.y + rect.h;
  if (handle.includes("w")) left = Math.min(snap(left + dx), right - LEAST_SIDE);
  if (handle.includes("e")) right = Math.max(snap(right + dx), left + LEAST_SIDE);
  if (handle.includes("n")) top = Math.min(snap(top + dy), bottom - LEAST_SIDE);
  if (handle.includes("s")) bottom = Math.max(snap(bottom + dy), top + LEAST_SIDE);
  return { x: left, y: top, w: right - left, h: bottom - top };
}

// Returns a rectangle moved by an arrow key: one pixel, or ten with Shift.
// Returns undefined for another key.
export function nudged(rect, key, shift) {
  const step = shift ? 10 : 1;
  const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step],
                  ArrowDown: [0, step] };
  const move = moves[key];
  return move && { x: rect.x + move[0], y: rect.y + move[1], w: rect.w, h: rect.h };
}

// Returns what a press of the main button starts:
//  - "box": a box that selects what it overlaps, in place of the selection;
//  - "adding box": the same box, adding what it overlaps to the selection;
//  - "toggle": the pressed component joins the selection, or leaves it;
//  - "drag": the selected components move, or a handle resizes its component;
//  - "select": the pressed component is selected alone.
// `onPage` is whether the topmost thing pressed is the page itself,
// `onSelected` whether it is a selected component, and `onHandle` whether
// it is a handle of the one selected component. `shift` and `command` are
// whether Shift, and Ctrl or Cmd on a Mac, are held. With Shift, a box
// starts wherever the press lands, so a page covered in components can
// still be boxed.
export function pressStarts({ onPage, onSelected, onHandle, shift, command }) {
  if (shift) {
    return command ? "adding box" : "box";
  }
  if (command) {
    return onPage ? "adding box" : "toggle";
  }
  if (onHandle || onSelected) {
    return "drag";
  }
  return onPage ? "box" : "select";
}

// Returns what a box too small to be one does: the click of a press on the
// same spot, without Shift. `adding` is whether the box adds to the
// selection, `onPage` whether the press landed on the page itself, and
// `onHandle` whether it landed on a handle of the one selected component,
// where a click changes nothing. "select" selects what the press landed on
// alone, "toggle" adds it to the selection or takes it out, and "nothing"
// changes nothing.
export function clickOfSmallBox({ adding, onPage, onHandle = false }) {
  if (adding) {
    return onPage ? "nothing" : "toggle";
  }
  return onHandle ? "nothing" : "select";
}

// Components' names, written on the page as the Editor's design view writes
// them: at each component's top left corner, black on yellow when it is
// local, white on black when global, cut to the component. The page has none.
export const NAME_FONT = "11px sans-serif";
const NAME_HEIGHT = 13;
// The room left and right of a name's text.
const NAME_PADDING = 1;
export const NAME_COLOURS = {
  local: { text: "#000000", back: "#ffff00" },
  global: { text: "#ffffff", back: "#000000" },
};

// Returns the box {x, y, w, h} of a component's name, `width` pixels of
// text: at its top left corner, cut to it.
export function nameBox(component, width) {
  return { x: component.x, y: component.y,
           w: Math.min(Math.ceil(width) + 2 * NAME_PADDING, component.w),
           h: Math.min(NAME_HEIGHT, component.h) };
}

// Writes the name of each component of a drawing, the page's aside, in ID
// order, so that a name over another's is the topmost component's. The
// components are where the view shows them at `level`; the names keep their
// size, so that they stay legible at every level.
export function paintNames(context, drawing, level = 1) {
  context.save();
  context.font = NAME_FONT;
  context.textAlign = "left";
  context.textBaseline = "top";
  for (const component of drawing.components) {
    if (component.type === "page") {
      continue;
    }
    const box = nameBox(inView(component, level), context.measureText(component.name).width);
    if (box.w <= 0 || box.h <= 0) {
      continue;
    }
    const colours = component.global ? NAME_COLOURS.global : NAME_COLOURS.local;
    context.save();
    context.beginPath();
    context.rect(box.x, box.y, box.w, box.h);
    context.clip();
    context.fillStyle = colours.back;
    context.fillRect(box.x, box.y, box.w, box.h);
    context.fillStyle = colours.text;
    context.fillText(component.name, box.x + NAME_PADDING, box.y + 1);
    context.restore();
  }
  context.restore();
}

// A locked component's padlock, as the Editor's design view draws one: at
// its top right corner, inside it, at its own size at every zoom level.
const PADLOCK = { width: 9, height: 11, inset: 2, body: "#5a9e4b", edge: "#2f5f27" };

// Draws a padlock on each locked component of a drawing, where the view
// shows it at `level`.
export function paintPadlocks(context, drawing, level = 1) {
  context.save();
  for (const component of drawing.components) {
    if (!component.locked) {
      continue;
    }
    const box = inView(component, level);
    const x = box.x + box.w - PADLOCK.inset - PADLOCK.width, y = box.y + PADLOCK.inset;
    // The shackle, an arch over the body's top half, then the body.
    context.strokeStyle = PADLOCK.edge;
    context.lineWidth = 1.5;
    context.beginPath();
    context.arc(x + PADLOCK.width / 2, y + 4, 2.5, Math.PI, 0);
    context.stroke();
    context.fillStyle = PADLOCK.body;
    context.fillRect(x, y + 4, PADLOCK.width, PADLOCK.height - 4);
    context.strokeRect(x + 0.5, y + 4.5, PADLOCK.width - 1, PADLOCK.height - 5);
  }
  context.restore();
}

// Returns the names of the touch captures among `unplaced` (a drawing's
// list) that never run: all but the last, since only the last touch capture
// of a page runs, as the Editor's simulator showed.
export function idleTouchCaptures(unplaced) {
  const captures = unplaced.filter((entry) => entry.type === "touch-capture")
    .map((entry) => entry.name);
  return new Set(captures.slice(0, -1));
}

// Returns the name of the component under the point (x, y) of the page: the
// topmost, the one with the highest ID, as the screen's touch finds it; or
// undefined outside the page.
export function componentAt(drawing, x, y) {
  for (let index = drawing.components.length - 1; index >= 0; index--) {
    const component = drawing.components[index];
    if (x >= component.x && x < component.x + component.w &&
        y >= component.y && y < component.y + component.h) {
      return component.name;
    }
  }
  return undefined;
}
