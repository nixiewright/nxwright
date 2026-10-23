// The zoom of the page preview and the simulator's panel (media/zoom-model.mjs).
// Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { fittingLevel, inView, pagePixel, scrollToKeep, shownPart, smoothedAt, zoomedIn,
  zoomedOut }
  from "../media/zoom-model.mjs";

test("the levels step up and down, and stop at their ends", () => {
  assert.equal(zoomedIn(1), 2);
  assert.equal(zoomedIn(0.75), 1);
  assert.equal(zoomedIn(8), 8);
  assert.equal(zoomedOut(2), 1);
  assert.equal(zoomedOut(1), 0.75);
  assert.equal(zoomedOut(0.25), 0.25);
  // A level between two, such as one a fit gave, steps to its neighbours.
  assert.equal(zoomedIn(1.5), 2);
  assert.equal(zoomedOut(1.5), 1);
});

test("the level that fits is the highest that fits both ways", () => {
  assert.equal(fittingLevel(800, 480, 1700, 1000), 2);
  assert.equal(fittingLevel(800, 480, 1700, 900), 1);
  assert.equal(fittingLevel(800, 480, 700, 900), 0.75);
  assert.equal(fittingLevel(800, 480, 100, 100), 0.25);
});

test("whole multiples keep the pixels sharp; below 100 percent is smoothed", () => {
  assert.equal(smoothedAt(0.5), true);
  assert.equal(smoothedAt(1), false);
  assert.equal(smoothedAt(3), false);
});

test("the page's pixel under a point of the view, and a rectangle in the view", () => {
  assert.equal(pagePixel(13, 1), 13);
  assert.equal(pagePixel(13, 4), 3);
  assert.equal(pagePixel(13, 0.5), 26);
  assert.deepEqual(inView({ x: 2, y: 3, w: 10, h: 5 }, 3), { x: 6, y: 9, w: 30, h: 15 });
});

test("zooming about the pointer keeps the page's point under it", () => {
  // The point 40 view pixels in, at 2, is the page's 20; at 4 it is 80 in.
  assert.equal(scrollToKeep(40, 2, 4), 40);
  assert.equal(scrollToKeep(40, 2, 1), -20);
});

test("the part of the view the window shows", () => {
  // A view 1600 by 960, scrolled 300 right and 100 down, in a window 800 by 500.
  assert.deepEqual(shownPart({ left: -300, top: -100, width: 1600, height: 960 }, 800, 500),
                   { x: 300, y: 100, w: 800, h: 500 });
  // A small view, whole in the window, 8 pixels in.
  assert.deepEqual(shownPart({ left: 8, top: 33, width: 400, height: 240 }, 800, 500),
                   { x: 0, y: 0, w: 400, h: 240 });
  // A view scrolled out of sight.
  assert.deepEqual(shownPart({ left: 8, top: -500, width: 400, height: 240 }, 800, 500).h, 0);
});
