// Which open tab of a page file a click on a component shows it in
// (src/pageTabChoice.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { chooseTab } from "../out/pageTabChoice.js";

const text = { tab: "text", view: "text" };
const preview = { tab: "preview", view: "preview" };

test("the active tab wins when it holds the page", () => {
  assert.equal(chooseTab([text, preview], "preview", "text"), preview);
  assert.equal(chooseTab([preview, text], "text", "preview"), text);
});

test("with both open and neither active, the view focused last wins", () => {
  assert.equal(chooseTab([text, preview], undefined, "preview"), preview);
  assert.equal(chooseTab([preview, text], "other", "text"), text);
});

test("with one view open, its tab is used, whichever was focused last", () => {
  assert.equal(chooseTab([text], undefined, "preview"), text);
  assert.equal(chooseTab([preview], undefined, "text"), preview);
});

test("with both open and none focused yet, the first tab is used", () => {
  assert.equal(chooseTab([text, preview], undefined, undefined), text);
});

test("with no tab open, there is none to use", () => {
  assert.equal(chooseTab([], undefined, "preview"), undefined);
});
