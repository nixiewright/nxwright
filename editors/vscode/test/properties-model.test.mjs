// The Attributes section's choices, by their names (media/properties-model.mjs).
// Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { choiceEntries, listed, rowLines, valueText } from "../media/properties-model.mjs";

const SCOPE = [{ value: 0, label: "local" }, { value: 1, label: "global" }];

test("a value among the choices is selected, each choice named then numbered", () => {
  assert.deepEqual(choiceEntries({ value: 1, labels: SCOPE }), [
    { value: "0", text: "local (0)", selected: false },
    { value: "1", text: "global (1)", selected: true },
  ]);
});

test("a value that is none of the choices comes first, and stays selected", () => {
  assert.deepEqual(choiceEntries({ value: 7, labels: SCOPE }), [
    { value: "7", text: "7 (none of its choices)", selected: true },
    { value: "0", text: "local (0)", selected: false },
    { value: "1", text: "global (1)", selected: false },
  ]);
});

test("a value shown alone is named as its choice", () => {
  assert.equal(valueText({ value: 1, labels: SCOPE }), "global (1)");
  assert.equal(valueText({ value: 7, labels: SCOPE }), "7 (none of its choices)");
  assert.equal(valueText({ value: 12, labels: [] }), "12");
  assert.equal(valueText({ value: "#ff0000", labels: [] }), "#ff0000");
});

test("which attributes get a row", () => {
  const rows = (treatment) => [false, true].map((given) => listed({ treatment, given }));
  assert.deepEqual(rows("shown"), [true, true]);
  assert.deepEqual(rows("value-only"), [true, true]);
  // What the page file holds stays in sight.
  assert.deepEqual(rows("hidden"), [false, true]);
  // Whatever the page file holds.
  assert.deepEqual(rows("never-shown"), [false, false]);
});

test("a problem on the line of an attribute without a row is not kept for a row", () => {
  const attributes = [
    { name: "txt", treatment: "shown", given: true, line: 5 },
    { name: "movex", treatment: "never-shown", given: true, line: 6 },
    { name: "bco", treatment: "shown", given: false, line: 1 },
  ];
  assert.deepEqual([...rowLines(attributes)], [5]);
});
