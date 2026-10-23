// The page preview's painting (media/preview-model.mjs), on a fake canvas
// context that records what is painted. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { backdropChoice, clickOfSmallBox, componentAt, darkness, dragged, handleAt,
  idleTouchCaptures, imageSources, NAME_COLOURS, nameBox, nudged, onGrid, paint, paintNames,
  paintPadlocks, paintScreen, pressStarts, screenColours, withMask }
  from "../media/preview-model.mjs";

// A 2D context that records each call that paints, with its arguments.
function recordingContext() {
  const calls = [];
  const context = {};
  for (const name of ["clearRect", "fillRect", "drawImage", "strokeRect", "fillText", "save",
                      "restore", "beginPath", "rect", "clip", "translate", "rotate"]) {
    context[name] = (...args) => calls.push([name, ...args]);
  }
  return { context, calls };
}

const drawing = {
  width: 100,
  height: 60,
  shapes: [
    { component: "page", kind: "colour", x: 0, y: 0, w: 100, h: 60, colour: "#ffffff" },
    { component: "photo", kind: "picture", x: 10, y: 5, w: 30, h: 30, picture: "logo",
      sx: 10, sy: 5 },
    { component: "title", kind: "text", x: 20, y: 10, w: 50, h: 20, image: "data:image/png;x" },
    { component: "zone", kind: "outline", x: 0, y: 40, w: 100, h: 20, label: "zone" },
  ],
  components: [
    { name: "page", type: "page", x: 0, y: 0, w: 100, h: 60 },
    { name: "title", type: "text", x: 20, y: 10, w: 50, h: 20 },
    { name: "zone", type: "hotspot", x: 0, y: 40, w: 100, h: 20 },
  ],
  notes: [],
};

test("each image a drawing needs, by its key, and how it loads", () => {
  assert.deepEqual(imageSources(drawing, { logo: "uri:logo" }),
                   [["logo", "uri:logo", "picture", undefined],
                    ["data:image/png;x", "data:image/png;x", "text", undefined]]);
});

test("a picture's colours become the screen's 16-bit ones, as the Editor shows them", () => {
  // Seen in the Editor's simulator: each colour cut to 5 bits of red, 6 of
  // green, and 5 of blue, then widened by repeating its top bits.
  const pixels = new Uint8ClampedArray([232, 231, 239, 255, 226, 226, 233, 128,
                                        160, 110, 0, 255, 255, 255, 255, 0]);
  screenColours(pixels);
  assert.deepEqual([...pixels], [239, 231, 239, 255, 231, 227, 239, 128,
                                 165, 109, 0, 255, 255, 255, 255, 0]);
});

test("on a screen that keeps no alpha, a picture's transparent share shows white", () => {
  // Seen in the Editor's simulator on an Enhanced screen: red half
  // transparent showed (255, 125, 123), and fully transparent white; the
  // build stores them so (screen_copy.py, stored_pixels).
  const pixels = new Uint8ClampedArray([255, 0, 0, 128, 255, 0, 0, 0, 255, 0, 0, 255]);
  screenColours(pixels, true);
  assert.deepEqual([...pixels], [255, 125, 123, 255, 255, 255, 255, 255, 255, 0, 0, 255]);
});

test("a drawing's pictures by how they load: kept apart when stored without alpha", () => {
  const opaque = { shapes: [
    { kind: "picture", picture: "logo", x: 0, y: 0, w: 1, h: 1, sx: 0, sy: 0, opaque: true },
    { kind: "picture", picture: "/card/splash", x: 0, y: 0, w: 1, h: 1, sx: 0, sy: 0,
      card: true }] };
  assert.deepEqual(imageSources(opaque, { logo: "uri:logo", "/card/splash": "uri:splash" }),
                   [["logo#opaque", "uri:logo", "opaque", undefined],
                    ["/card/splash", "uri:splash", "card", undefined]]);
});

test("a card's picture loads as it is, with its mask when it has one", () => {
  // A .xi file's JPEG picture and its transparency come apart, as data URLs.
  const cards = { shapes: [
    { kind: "picture", picture: "/card/a.xi", x: 0, y: 0, w: 1, h: 1, sx: 0, sy: 0, card: true },
    { kind: "picture", picture: "/card/b.png", x: 0, y: 0, w: 1, h: 1, sx: 0, sy: 0,
      card: true }] };
  assert.deepEqual(imageSources(cards, { "/card/a.xi": "data:image/jpeg;a",
                                         "/card/b.png": "uri:b" },
                                { "/card/a.xi": "data:image/png;mask" }),
                   [["/card/a.xi", "data:image/jpeg;a", "card", "data:image/png;mask"],
                    ["/card/b.png", "uri:b", "card", undefined]]);
});

test("a mask gives a picture its alpha, its colours as they are", () => {
  const pixels = new Uint8ClampedArray([200, 100, 50, 255, 1, 2, 3, 255]);
  withMask(pixels, new Uint8ClampedArray([255, 255, 255, 126, 255, 255, 255, 0]));
  assert.deepEqual([...pixels], [200, 100, 50, 126, 1, 2, 3, 0]);
});

test("shapes are painted in order, a text picture at its place", () => {
  const { context, calls } = recordingContext();
  const images = new Map([["logo", { width: 25, height: 100 }],
                          ["data:image/png;x", { width: 50, height: 20 }]]);
  paint(context, drawing, images);
  const painted = calls.map((call) => call[0]).filter((name) => name !== "fillText");
  assert.deepEqual(painted, ["clearRect", "fillRect", "drawImage", "drawImage", "strokeRect"]);
  // The picture from its pixel (10, 5), cut where the picture ends: 25 - 10 wide.
  assert.deepEqual(calls[2], ["drawImage", images.get("logo"), 10, 5, 15, 30, 10, 5, 15, 30]);
  assert.deepEqual(calls[3], ["drawImage", images.get("data:image/png;x"), 0, 0, 50, 20,
                              20, 10, 50, 20]);
});

test("a shape marked with an aph is painted that opaque, and the next as it is", () => {
  // As the Editor's simulator blends a translucent component, part by part:
  // its background, then its text over it, each at aph out of 127.
  const { context, calls } = recordingContext();
  context.globalAlpha = 1;
  const drawn = [];
  for (const name of ["fillRect", "drawImage"]) {
    context[name] = () => drawn.push([name, context.globalAlpha]);
  }
  const images = new Map([["data:image/png;w", { width: 50, height: 20 }]]);
  paint(context, { width: 100, height: 60, notes: [], components: [], shapes: [
    { component: "page", kind: "colour", x: 0, y: 0, w: 100, h: 60, colour: "#000000" },
    { component: "t0", kind: "colour", x: 10, y: 10, w: 50, h: 20, colour: "#ff0000", aph: 64 },
    { component: "t0", kind: "text", x: 10, y: 10, w: 50, h: 20, image: "data:image/png;w",
      aph: 64 },
    { component: "t1", kind: "colour", x: 10, y: 40, w: 50, h: 20, colour: "#ff0000" },
  ] }, images);
  assert.deepEqual(drawn, [["fillRect", 1], ["fillRect", 64 / 127], ["drawImage", 64 / 127],
                           ["fillRect", 1]]);
  assert.equal(context.globalAlpha, 1);
  assert.deepEqual(calls.map((call) => call[0]), ["clearRect"]);
});

test("an image larger than its shape is cut to it", () => {
  // An animation's frame of 80 by 60, which the Editor stores as a JPEG of
  // 80 by 64, padded with black to whole blocks of 16: the screen shows 60
  // rows of it.
  const { context, calls } = recordingContext();
  const frame = { width: 80, height: 64 };
  paint(context, { width: 100, height: 100, notes: [], components: [], shapes: [
    { component: "gm0", kind: "text", x: 20, y: 20, w: 80, h: 60, image: "data:image/jpeg;x" },
  ] }, new Map([["data:image/jpeg;x", frame]]));
  assert.deepEqual(calls[1], ["drawImage", frame, 0, 0, 80, 60, 20, 20, 80, 60]);
});

test("an animation's or a video's turned frame is turned back, then cut to its size", () => {
  // A frame 72 by 40, padded to 80 by 48 and stored for a screen turned 90
  // or 270 degrees, is a picture of 48 by 80. Turned back, its padding lies
  // at its right and bottom, as an upright frame's, and is cut off.
  const turned = (rotation) => ({ width: 200, height: 200, notes: [], components: [], shapes: [
    { component: "gm0", kind: "text", x: 20, y: 30, w: 72, h: 40, image: "frame", rotation }] });
  const across = { width: 48, height: 80 };
  const along = { width: 80, height: 48 };
  for (const [rotation, image, offset] of [[90, across, [-24, -40]], [180, along, [-40, -24]],
                                           [270, across, [-24, -40]]]) {
    const { context, calls } = recordingContext();
    paint(context, turned(rotation), new Map([["frame", image]]));
    assert.deepEqual(calls.slice(1), [["save"], ["beginPath"], ["rect", 20, 30, 72, 40], ["clip"],
                                      ["translate", 60, 54], ["rotate", -rotation * Math.PI / 180],
                                      ["drawImage", image, ...offset], ["restore"]]);
  }
});

test("a translucent component's turned frame is painted as opaque as its aph", () => {
  // The turn changes the canvas's state within a save and a restore, and
  // leaves the opacity paint() set for the shape alone.
  const { context } = recordingContext();
  const drawn = [];
  context.drawImage = () => drawn.push(context.globalAlpha);
  const frame = { width: 48, height: 80 };
  paint(context, { width: 200, height: 200, notes: [], components: [], shapes: [
    { component: "gm0", kind: "text", x: 20, y: 30, w: 72, h: 40, image: "frame", rotation: 90,
      aph: 64 },
    { component: "gm1", kind: "text", x: 20, y: 90, w: 72, h: 40, image: "frame", rotation: 90 },
  ] }, new Map([["frame", frame]]));
  assert.deepEqual(drawn, [64 / 127, 1]);
  assert.equal(context.globalAlpha, 1);
});

test("an external picture turned back by the screen's rotation, from the top left", () => {
  // As the Nextion Editor's simulator showed at 90, 180, and 270 degrees:
  // the file's pixels as stored, turned back by the screen's rotation, the
  // turned picture's top left corner at the component's, cut at its right
  // and bottom.
  const turned = (rotation) => ({ width: 100, height: 60, shapes: [
    { component: "splash", kind: "picture", x: 10, y: 5, w: 40, h: 30, picture: "file",
      sx: 0, sy: 0, rotation }] });
  const turnedBack = (rotation, image, clip, centre, from) => [
    ["save"], ["beginPath"], ["rect", 10, 5, ...clip], ["clip"], ["translate", ...centre],
    ["rotate", -rotation * Math.PI / 180], ["drawImage", image, ...from], ["restore"]];
  // Smaller than the component: all of it.
  let { context, calls } = recordingContext();
  const small = { width: 30, height: 20 };
  paint(context, turned(180), new Map([["file", small]]));
  assert.deepEqual(calls.slice(1), turnedBack(180, small, [30, 20], [25, 15], [-15, -10]));
  // Larger: cut at the component's right and bottom.
  ({ context, calls } = recordingContext());
  const large = { width: 50, height: 50 };
  paint(context, turned(90), new Map([["file", large]]));
  assert.deepEqual(calls.slice(1), turnedBack(90, large, [40, 30], [35, 30], [-25, -25]));
  // Turned a quarter, a picture 20 by 25 shows 25 by 20.
  ({ context, calls } = recordingContext());
  const narrow = { width: 20, height: 25 };
  paint(context, turned(270), new Map([["file", narrow]]));
  assert.deepEqual(calls.slice(1), turnedBack(270, narrow, [25, 20], [22.5, 15], [-10, -12.5]));
});

test("a picture not loaded is left out", () => {
  const { context, calls } = recordingContext();
  paint(context, drawing, new Map());
  assert.equal(calls.filter((call) => call[0] === "drawImage").length, 0);
});

test("the component under the pointer is the topmost", () => {
  assert.equal(componentAt(drawing, 30, 15), "title");
  assert.equal(componentAt(drawing, 5, 45), "zone");
  assert.equal(componentAt(drawing, 5, 5), "page");
  assert.equal(componentAt(drawing, 150, 5), undefined);
});

const box = { x: 20, y: 30, w: 40, h: 50 };

test("a drag moves a component, snapped to the grid", () => {
  assert.deepEqual(dragged(box, undefined, 7, -4, 1), { x: 27, y: 26, w: 40, h: 50 });
  assert.deepEqual(dragged(box, undefined, 7, -4, 10), { x: 30, y: 30, w: 40, h: 50 });
});

test("a point lands on the grid, or on a whole pixel without one", () => {
  // Where the right-click menu adds a component.
  assert.equal(onGrid(13.6, 1), 14);
  assert.equal(onGrid(13.6, 10), 10);
  assert.equal(onGrid(15, 10), 20);
});

test("a handle resizes at the edges it names", () => {
  assert.deepEqual(dragged(box, "se", 5, 6, 1), { x: 20, y: 30, w: 45, h: 56 });
  assert.deepEqual(dragged(box, "nw", 5, 6, 1), { x: 25, y: 36, w: 35, h: 44 });
  assert.deepEqual(dragged(box, "e", 3, 99, 1), { x: 20, y: 30, w: 43, h: 50 });
  // Edges that move land on the grid; those that do not stay where they are.
  assert.deepEqual(dragged(box, "se", 3, 3, 8), { x: 20, y: 30, w: 44, h: 50 });
});

test("a resize never goes below 2 by 2, the least the Editor takes", () => {
  assert.deepEqual(dragged(box, "w", 100, 0, 1), { x: 58, y: 30, w: 2, h: 50 });
  assert.deepEqual(dragged(box, "n", 0, 100, 1), { x: 20, y: 78, w: 40, h: 2 });
});

test("the handle under the pointer", () => {
  assert.equal(handleAt(box, 20, 30), "nw");
  assert.equal(handleAt(box, 62, 54), "e");
  assert.equal(handleAt(box, 40, 55), undefined);
});

test("arrow keys move by one pixel, or ten with Shift", () => {
  assert.deepEqual(nudged(box, "ArrowLeft", false), { x: 19, y: 30, w: 40, h: 50 });
  assert.deepEqual(nudged(box, "ArrowDown", true), { x: 20, y: 40, w: 40, h: 50 });
  assert.equal(nudged(box, "Enter", false), undefined);
});

test("a press draws a box from the page, and from anywhere with Shift", () => {
  const pressOn = (place, keys = {}) => pressStarts({
    onPage: place === "page", onSelected: place === "selected" || place === "handle",
    onHandle: place === "handle", shift: false, command: false, ...keys });
  assert.equal(pressOn("page"), "box");
  assert.equal(pressOn("component"), "select");
  // A selected component moves, locked or not: a locked one has no handle.
  assert.equal(pressOn("selected"), "drag");
  assert.equal(pressOn("handle"), "drag");
  assert.equal(pressOn("page", { command: true }), "adding box");
  assert.equal(pressOn("component", { command: true }), "toggle");
  assert.equal(pressOn("selected", { command: true }), "toggle");
  for (const place of ["page", "component", "selected", "handle"]) {
    assert.equal(pressOn(place, { shift: true }), "box", place);
    assert.equal(pressOn(place, { shift: true, command: true }), "adding box", place);
  }
});

test("a box too small to be one is a click on what the press landed on", () => {
  assert.equal(clickOfSmallBox({ adding: false, onPage: true }), "select");
  assert.equal(clickOfSmallBox({ adding: false, onPage: false }), "select");
  assert.equal(clickOfSmallBox({ adding: true, onPage: false }), "toggle");
  assert.equal(clickOfSmallBox({ adding: true, onPage: true }), "nothing");
  // A click on a handle, half outside its component, changes nothing.
  assert.equal(clickOfSmallBox({ adding: false, onPage: true, onHandle: true }), "nothing");
  assert.equal(clickOfSmallBox({ adding: false, onPage: false, onHandle: true }), "nothing");
});

test("a simulation's screen, dimmed and asleep", () => {
  assert.equal(darkness({}), 0);
  assert.equal(darkness({ dim: 80 }), 0.2);
  assert.equal(darkness({ dim: 80, asleep: true }), 1);
  const { context, calls } = recordingContext();
  paintScreen(context, { width: 100, height: 50, shapes: [], dim: 50 }, new Map());
  assert.deepEqual(calls.at(-1), ["fillRect", 0, 0, 100, 50]);
  assert.equal(context.fillStyle, "rgba(0, 0, 0, 0.5)");
});

test("what a simulation's drawing is drawn over", () => {
  const page = (start, entry, transparent) => ({ start, entry, transparent });
  const cases = [
    // The first drawing, even of a page without background: black.
    [undefined, page(1, 1, true), "black"],
    // The page shown, drawn again: over what it was drawn over.
    [{ start: 1, entry: 1 }, page(1, 1, true), "same"],
    // A page without background entered: over the screen; then another.
    [{ start: 1, entry: 1 }, page(1, 2, true), "screen"],
    [{ start: 1, entry: 2 }, page(1, 3, true), "screen"],
    // A page with a background covers the screen.
    [{ start: 1, entry: 3 }, page(1, 4, false), "black"],
    // Started again: black, whatever the page.
    [{ start: 1, entry: 4 }, page(2, 5, true), "black"],
  ];
  for (const [last, drawing, expected] of cases) {
    assert.equal(backdropChoice(last, drawing), expected, JSON.stringify([last, drawing]));
  }
});

test("a page without background is painted over its backdrop", () => {
  const { context, calls } = recordingContext();
  const backdrop = { width: 100, height: 60 };
  paint(context, { width: 100, height: 60, shapes: [] }, new Map(), backdrop);
  assert.deepEqual(calls, [["clearRect", 0, 0, 100, 60], ["drawImage", backdrop, 0, 0]]);
});

test("a backdrop shape shows its part of the backdrop again, or black without one", () => {
  const shape = { component: "page", kind: "backdrop", x: 10, y: 5, w: 30, h: 20 };
  const drawing = { width: 100, height: 60, shapes: [shape] };
  const backdrop = { width: 100, height: 60 };
  const kept = recordingContext();
  paint(kept.context, drawing, new Map(), backdrop);
  assert.deepEqual(kept.calls, [["clearRect", 0, 0, 100, 60], ["drawImage", backdrop, 0, 0],
                                ["drawImage", backdrop, 10, 5, 30, 20, 10, 5, 30, 20]]);
  // After a start, the panel keeps no screen: a page without background
  // is drawn over black.
  const none = recordingContext();
  paint(none.context, drawing, new Map());
  assert.deepEqual(none.calls, [["clearRect", 0, 0, 100, 60], ["fillRect", 10, 5, 30, 20]]);
  assert.equal(none.context.fillStyle, "#000000");
});

test("a name sits at its component's top left corner, cut to it", () => {
  assert.deepEqual(nameBox({ x: 20, y: 10, w: 50, h: 20 }, 24.3), { x: 20, y: 10, w: 27, h: 13 });
  // A component smaller than its name, as the Editor showed a 20 by 10 text's.
  assert.deepEqual(nameBox({ x: 20, y: 10, w: 20, h: 10 }, 24.3), { x: 20, y: 10, w: 20, h: 10 });
});

test("names are written in their scope's colours, the page's aside", () => {
  const { context, calls } = recordingContext();
  context.measureText = (text) => ({ width: 6 * text.length });
  const named = { components: [
    { name: "page", type: "page", x: 0, y: 0, w: 100, h: 60, global: false },
    { name: "title", type: "text", x: 20, y: 10, w: 50, h: 20, global: false },
    { name: "zone", type: "hotspot", x: 0, y: 40, w: 100, h: 20, global: true },
  ] };
  const fills = [];
  Object.defineProperty(context, "fillStyle", { set: (colour) => fills.push(colour) });
  paintNames(context, named);
  assert.deepEqual(calls.filter((call) => call[0] === "fillText"),
                   [["fillText", "title", 21, 11], ["fillText", "zone", 1, 41]]);
  assert.deepEqual(calls.filter((call) => call[0] === "fillRect"),
                   [["fillRect", 20, 10, 32, 13], ["fillRect", 0, 40, 26, 13]]);
  assert.deepEqual(fills, [NAME_COLOURS.local.back, NAME_COLOURS.local.text,
                           NAME_COLOURS.global.back, NAME_COLOURS.global.text]);
});

test("zoomed, names stand where the view shows their components, at their own size", () => {
  const { context, calls } = recordingContext();
  context.measureText = (text) => ({ width: 6 * text.length });
  paintNames(context, { components: [
    { name: "title", type: "text", x: 20, y: 10, w: 50, h: 20, global: false }] }, 2);
  assert.deepEqual(calls.filter((call) => call[0] === "fillRect"), [["fillRect", 40, 20, 32, 13]]);
});

test("a padlock at a locked component's top right corner, at its own size", () => {
  const { context, calls } = recordingContext();
  context.arc = (...args) => calls.push(["arc", ...args]);
  context.stroke = () => calls.push(["stroke"]);
  const locked = { components: [
    { name: "page", type: "page", x: 0, y: 0, w: 100, h: 60 },
    { name: "held", type: "text", x: 20, y: 10, w: 50, h: 20, locked: true },
    { name: "free", type: "text", x: 0, y: 40, w: 50, h: 20, locked: false }] };
  paintPadlocks(context, locked, 2);
  // At 200 percent, the component's view runs from x 40 to 140: the
  // padlock's 9 pixels end 2 inside its right edge, 2 below its top.
  assert.deepEqual(calls.filter((call) => call[0] === "fillRect"), [["fillRect", 129, 26, 9, 7]]);
  assert.equal(calls.filter((call) => call[0] === "arc").length, 1);
});

test("only the last touch capture of a page runs", () => {
  const unplaced = [{ name: "tc0", type: "touch-capture" }, { name: "tm0", type: "timer" },
                    { name: "tc1", type: "touch-capture" }, { name: "tc2", type: "touch-capture" }];
  assert.deepEqual([...idleTouchCaptures(unplaced)], ["tc0", "tc1"]);
  assert.deepEqual([...idleTouchCaptures(unplaced.slice(0, 2))], []);
  assert.deepEqual([...idleTouchCaptures([])], []);
});
