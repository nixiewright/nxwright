// What "Go to Event..." lists, and what "Clear events" says
// (src/componentEvents.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { clearEventsQuestion, eventChoices, noEventsNote, nothingToClearNote }
  from "../out/componentEvents.js";

test("each event in order, with the file holding its code or none yet", () => {
  assert.deepEqual(eventChoices([
    { event: "down", uri: null },
    { event: "up", uri: "file:///c%3A/app/pages/lib/my%20shared.nx" },
  ]), [
    { label: "down", description: "no code yet", event: "down" },
    { label: "up", description: "my shared.nx", event: "up" },
  ]);
});

test("a type without events lists none, and says so", () => {
  assert.deepEqual(eventChoices([]), []);
  assert.equal(noEventsNote("va0"), "va0 has no events: its type has none.");
});

test("clearing several asks first, naming them; nothing to clear is said", () => {
  assert.equal(clearEventsQuestion(["b0", "t0"]),
               "Remove the code of every event of b0, t0? The components stay.");
  assert.equal(nothingToClearNote(["b0"]), "b0 has no code to clear.");
  assert.equal(nothingToClearNote(["b0", "t0"]), "None of b0, t0 has code to clear.");
});
