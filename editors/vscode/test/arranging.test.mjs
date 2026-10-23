// Arranging several components of the page preview (media/arranging.mjs).
// Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { aligned, arrangement, boxBetween, groupMembers, lockedAmong, movedBy,
  movedTogether, movingNames, overlappingBox, sameSize, spacedEvenly }
  from "../media/arranging.mjs";

const anchor = { name: "a", x: 100, y: 50, w: 80, h: 40 };
const other = { name: "b", x: 10, y: 200, w: 31, h: 11 };

test("aligned with the anchor's edges and centres", () => {
  const at = (how) => aligned(anchor, [other], how)[0];
  assert.deepEqual([at("left").x, at("right").x, at("top").y, at("bottom").y], [100, 149, 50, 79]);
  // (80 - 31) / 2 is 24.5: the pixel to the left; (40 - 11) / 2 is 14.5.
  assert.deepEqual([at("centreAcross").x, at("centreDown").y], [124, 64]);
  // Only the coordinate aligned moves.
  assert.deepEqual(at("left"), { ...other, x: 100 });
});

test("the anchor's width, height, or both", () => {
  assert.deepEqual(sameSize(anchor, [other], "width")[0], { ...other, w: 80 });
  assert.deepEqual(sameSize(anchor, [other], "height")[0], { ...other, h: 40 });
  assert.deepEqual(sameSize(anchor, [other], "both")[0], { ...other, w: 80, h: 40 });
});

test("spaced evenly between the first and the last", () => {
  const rects = [
    { name: "c", x: 100, y: 0, w: 10, h: 5 },
    { name: "a", x: 0, y: 0, w: 10, h: 5 },
    { name: "d", x: 130, y: 0, w: 20, h: 5 },
    { name: "b", x: 15, y: 0, w: 10, h: 5 },
  ];
  // From 10 to 130, 20 pixels of components between: 100 free over 3 gaps,
  // 34, 33, and 33.
  const spaced = spacedEvenly(rects, true);
  assert.deepEqual(spaced.map((rect) => [rect.name, rect.x]),
                   [["c", 87], ["a", 0], ["d", 130], ["b", 44]]);
  // Down, the same rule on y; two are left as they are.
  assert.deepEqual(spacedEvenly(rects.slice(0, 2), true), rects.slice(0, 2));
  const column = rects.map((rect) => ({ ...rect, x: 0, y: rect.x, w: 5, h: rect.w }));
  assert.deepEqual(spacedEvenly(column, false).map((rect) => rect.y), [87, 0, 130, 44]);
});

test("the components a box overlaps, the page aside", () => {
  const components = [
    { name: "page0", type: "page", x: 0, y: 0, w: 800, h: 480 },
    { name: "in", type: "text", x: 10, y: 10, w: 20, h: 20 },
    { name: "across", type: "text", x: 25, y: 10, w: 20, h: 20 },
    // Against the screen's left edge, which no box can start beyond.
    { name: "edge", type: "text", x: 0, y: 40, w: 20, h: 20 },
    // Touching the first box's right side, without overlapping it.
    { name: "beside", type: "text", x: 40, y: 10, w: 20, h: 20 },
  ];
  assert.deepEqual(overlappingBox(components, boxBetween(40, 35, 5, 5)), ["in", "across"]);
  assert.deepEqual(overlappingBox(components, boxBetween(5, 45, 30, 50)), ["edge"]);
  // A box with no width selects what it crosses.
  assert.deepEqual(overlappingBox(components, boxBetween(35, 0, 35, 50)), ["across"]);
  assert.deepEqual(overlappingBox(components, boxBetween(0, 0, 800, 480)),
                   ["in", "across", "edge", "beside"]);
});

test("moved by a step", () => {
  assert.deepEqual(movedBy(other, 5, -3), { ...other, x: 15, y: 197 });
});

test("a locked component stays where it is, in each arrangement and move", () => {
  const locked = new Set(["b"]);
  const third = { name: "c", x: 300, y: 7, w: 20, h: 9 };
  // The locked one is left out; a locked anchor's edges still count.
  assert.deepEqual(arrangement([anchor, other, third], "left", locked), [{ ...third, x: 100 }]);
  assert.deepEqual(arrangement([other, anchor], "top", locked), [{ ...anchor, y: 200 }]);
  assert.deepEqual(arrangement([anchor, other, third], "sameSize", locked),
                   [{ ...third, w: 80, h: 40 }]);
  assert.deepEqual(movedTogether([anchor, other, third], 5, 1, locked).map((rect) => rect.name),
                   ["a", "c"]);
  assert.deepEqual(movedTogether([anchor], 5, 1, new Set(["a"])), []);
});

test("spacing keeps a locked component as it keeps the first and the last", () => {
  const row = [["a", 0], ["b", 20], ["l", 50], ["c", 70], ["d", 100]]
    .map(([name, x]) => ({ name, x, y: 0, w: 10, h: 5 }));
  // From 10 to 50, b's 10: 30 free over two gaps, b at 25; then c at 75.
  assert.deepEqual(arrangement(row, "spaceAcross", new Set(["l"])).map((rect) => [rect.name, rect.x]),
                   [["a", 0], ["b", 25], ["c", 75], ["d", 100]]);
});

// A drawing's components in groups (component_groups.py): a and b share
// (1, 0); e's (1, 5) is another group; c is alone in its own; d is in none.
const grouped = [
  { name: "page", type: "page" }, { name: "a", group: "1/0" }, { name: "b", group: "1/0" },
  { name: "c", group: "3/4" }, { name: "d" }, { name: "e", group: "1/5", locked: true },
  { name: "f", group: "1/5" },
];

test("a move takes along the other members of the moved components' groups, each once", () => {
  assert.deepEqual(movingNames(grouped, ["a"]), ["a", "b"]);
  assert.deepEqual(movingNames(grouped, ["b", "d"]), ["b", "d", "a"]);
  // A member selected already moves once, in the selection's order.
  assert.deepEqual(movingNames(grouped, ["b", "a"]), ["b", "a"]);
  assert.deepEqual(movingNames(grouped, ["d", "c"]), ["d", "c"]);
  assert.deepEqual(movingNames(grouped, ["f"]), ["f", "e"]);
});

test("a locked member of a moving group stays where it is, selected or not", () => {
  assert.deepEqual([...lockedAmong(grouped, movingNames(grouped, ["f"]))], ["e"]);
  assert.deepEqual([...lockedAmong(grouped, ["e", "a"])], ["e"]);
  const rects = movingNames(grouped, ["f"]).map((name) => ({ name, x: 0, y: 0, w: 5, h: 5 }));
  assert.deepEqual(movedTogether(rects, 3, 0, lockedAmong(grouped, ["f", "e"]))
    .map((rect) => [rect.name, rect.x]), [["f", 3]]);
});

test("the members the overlay tints: every member of the selected components' groups", () => {
  assert.deepEqual(groupMembers(grouped, ["a", "d"]), ["a", "b"]);
  assert.deepEqual(groupMembers(grouped, ["f", "c"]), ["c", "e", "f"]);
  assert.deepEqual(groupMembers(grouped, ["d"]), []);
});
