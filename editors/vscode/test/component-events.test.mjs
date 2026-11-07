// What "Clear events" says (src/componentEvents.ts, compiled to out/ before
// the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { clearEventsQuestion, nothingToClearNote } from "../out/componentEvents.js";

test("clearing several asks first, naming them; nothing to clear is said", () => {
  assert.equal(clearEventsQuestion(["b0", "t0"]),
               "Remove the code of every event of b0, t0? The components stay.");
  assert.equal(nothingToClearNote(["b0"]), "b0 has no code to clear.");
  assert.equal(nothingToClearNote(["b0", "t0"]), "None of b0, t0 has code to clear.");
});
