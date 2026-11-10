// The webviews' painter of a waveform's channel (media/wave-painter.mjs),
// against the cases nxwright's own painter is checked against too
// (tests/fixtures/wave-painter/cases.json, which tests/test_wave_painting.py
// keeps as what Python paints). Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  wavePixels, waveRgba, wavesBelongTo, withWaves,
} from "../media/wave-painter.mjs";

const CASES = JSON.parse(readFileSync(fileURLToPath(
  new URL("../../../tests/fixtures/wave-painter/cases.json", import.meta.url)), "utf8"));

test("the painter gives the pixels nxwright's own painter gives, case by case", () => {
  assert.ok(CASES.length >= 20);
  for (const [place, { width, height, points, dis, dir, pixels }] of CASES.entries()) {
    assert.deepEqual(wavePixels(width, height, points, dis, dir), pixels,
                     `case ${place + 1}: ${width} by ${height}, dis ${dis}, dir ${dir}`);
  }
});

test("a wave shape's picture has its pixels in its colour, and the rest clear", () => {
  const shape = { x: 9, y: 9, w: 4, h: 5, colour: "#ff8000", points: [0, 4, 2], dis: 100, dir: 1 };
  const rgba = waveRgba(shape);
  assert.equal(rgba.length, 4 * 5 * 4);
  const painted = [];
  for (let row = 0; row < 5; row += 1) {
    for (let column = 0; column < 4; column += 1) {
      const pixel = [...rgba.slice((row * 4 + column) * 4, (row * 4 + column) * 4 + 4)];
      if (pixel[3] !== 0) {
        assert.deepEqual(pixel, [255, 128, 0, 255]);
        painted.push([column, row]);
      }
    }
  }
  const expected = wavePixels(4, 5, [0, 4, 2], 100, 1);
  assert.deepEqual(painted.sort(), [...expected].sort());
});

test("new points take the place of a waveform's channels in a drawing", () => {
  const wave = (component, colour, points) => ({ component, kind: "wave", colour, points });
  const shapes = [
    { component: "page0", kind: "colour" },
    { component: "chart", kind: "colour" },
    wave("chart", "#ff0000", [1]), wave("chart", "#00ff00", []),
    { component: "t0", kind: "text" },
    wave("scope", "#0000ff", [9]),
  ];
  const fresh = [wave("chart", "#ff0000", [1, 2]), wave("chart", "#00ff00", [7])];
  const made = withWaves(shapes, [
    { component: "chart", shapes: fresh },
    // A waveform the drawing does not show, as one hidden, is left out.
    { component: "hidden", shapes: [wave("hidden", "#ffffff", [3])] },
  ]);
  assert.deepEqual(made, [shapes[0], shapes[1], ...fresh, shapes[4], shapes[5]]);
  // The drawing's own shapes are left as they were.
  assert.deepEqual(shapes[2].points, [1]);
});

test("new points belong to the drawing of the same start, entry, and page", () => {
  const drawing = { start: 2, entry: 5, page: "day", shapes: [] };
  assert.equal(wavesBelongTo(drawing, { start: 2, entry: 5, page: "day" }), true);
  // Points sent after a start again, or after the page was entered again or
  // changed, wait for their own drawing.
  assert.equal(wavesBelongTo(drawing, { start: 3, entry: 5, page: "day" }), false);
  assert.equal(wavesBelongTo(drawing, { start: 2, entry: 6, page: "day" }), false);
  assert.equal(wavesBelongTo(drawing, { start: 2, entry: 5, page: "home" }), false);
  // Nothing is painted before the first drawing.
  assert.equal(wavesBelongTo(undefined, { start: 2, entry: 5, page: "day" }), false);
});

test("a shape without room has no pixels", () => {
  assert.equal(waveRgba({ w: 0, h: 5, colour: "#ffffff", points: [1], dis: 100, dir: 0 }).length, 0);
});
