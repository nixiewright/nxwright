// What Paste Special asks for, onto components or for new copies, and what
// it sends once some are picked
// (src/pasteParts.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { CODE_NOT_AT_HAND, PART_CHOICES, copiedTableCount, copiesToPaste, copyChoices,
         partsToPaste } from "../out/pasteParts.js";

const choice = (part) => PART_CHOICES.find((entry) => entry.part === part);

test("the four parts, in order, by the names the server takes", () => {
  assert.deepEqual(PART_CHOICES.map((entry) => entry.part),
                   ["size", "position", "attributes", "code"]);
});

test("the parts picked, and the code only when code is picked", () => {
  assert.deepEqual(partsToPaste([choice("size"), choice("position")], ["on b0.down:\n"]),
                   { parts: ["size", "position"], code: [] });
  assert.deepEqual(partsToPaste([choice("size"), choice("code")], ["on b0.down:\n"]),
                   { parts: ["size", "code"], code: ["on b0.down:\n"] });
});

test("the components' tables the clipboard holds, counted before asking", () => {
  const table = '[[component]]\nname = "b0"\ntype = "button"\n';
  assert.equal(copiedTableCount(table), 1);
  // Lines ended as Windows ends them, and a comment after the header.
  assert.equal(copiedTableCount(table.replace(/\n/g, "\r\n") +
                                "\r\n  [[component]]  # the second\r\n"), 2);
  assert.equal(copiedTableCount("hello there"), 0);
});

test("code picked but not at hand is said, and the other parts pasted", () => {
  assert.deepEqual(partsToPaste([choice("size"), choice("code")], undefined),
                   { parts: ["size"], code: [], note: CODE_NOT_AT_HAND });
  // Code alone, not at hand: nothing is left to paste.
  assert.deepEqual(partsToPaste([choice("code")], undefined),
                   { parts: [], code: [], note: CODE_NOT_AT_HAND });
});

test("new copies are asked for their position and their code, code ticked while at hand", () => {
  const shown = (atHand) => copyChoices(atHand).map((entry) => [entry.part, entry.picked]);
  assert.deepEqual(shown(true), [["position", false], ["code", true]]);
  assert.deepEqual(shown(false), [["position", false], ["code", false]]);
});

test("new copies go in place, to the point clicked, or where Paste puts them", () => {
  const [position] = copyChoices(true);
  const point = { x: 40, y: 60 };
  assert.deepEqual(copiesToPaste([position], undefined, point).place, { inPlace: true });
  assert.deepEqual(copiesToPaste([], undefined, point).place, { at: point });
  assert.deepEqual(copiesToPaste([], undefined).place, {});
});

test("new copies bring the code only when it is ticked, said when not at hand", () => {
  const code = copyChoices(true)[1];
  assert.deepEqual(copiesToPaste([code], ["on b0.down:\n"]),
                   { place: {}, code: ["on b0.down:\n"] });
  assert.deepEqual(copiesToPaste([], ["on b0.down:\n"]), { place: {}, code: [] });
  assert.deepEqual(copiesToPaste([code], undefined),
                   { place: {}, code: [], note: CODE_NOT_AT_HAND });
});
