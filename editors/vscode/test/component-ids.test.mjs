// The questions asked before deleting, cutting, or moving components
// (src/componentIds.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { DONT_WARN_AGAIN, deleteQuestion, moveQuestion, shiftedByDeleting }
  from "../out/componentIds.js";

const ORDER = ["t0", "b0", "b1", "n0"];

test("a deletion changes the IDs of the components after it that are not deleted", () => {
  assert.deepEqual(shiftedByDeleting(ORDER, ["b0"]), ["b1", "n0"]);
  assert.deepEqual(shiftedByDeleting(ORDER, ["b0", "n0"]), ["b1"]);
  assert.deepEqual(shiftedByDeleting(ORDER, ["n0"]), []);
  assert.deepEqual(shiftedByDeleting(ORDER, ["b1", "n0"]), []);
  assert.deepEqual(shiftedByDeleting(ORDER, ["x"]), []);
});

test("nothing is asked when no ID changes and no code uses the component's name", () => {
  assert.equal(deleteQuestion("Delete", ["n0"], [], [], true), undefined);
  // With the warning turned off, changed IDs do not cause a question either.
  assert.equal(deleteQuestion("Delete", ["b0"], [], ["b1"], false), undefined);
});

test("a deletion that changes IDs asks first, with a button that turns the warning off", () => {
  const question = deleteQuestion("Delete", ["b0"], [], ["b1", "n0"], true);
  assert.equal(question.message, "Delete b0?");
  assert.match(question.detail, /^This will change the IDs of 2 components after it on the page\./);
  assert.match(question.detail, /microcontroller/);
  assert.deepEqual(question.buttons, ["Delete", DONT_WARN_AGAIN]);
  const one = deleteQuestion("Cut", ["b0", "b1"], [], ["n0"], true);
  assert.equal(one.message, "Cut b0, b1?");
  assert.match(one.detail, /^This will change the ID of 1 component after them on the page\./);
  assert.deepEqual(one.buttons, ["Cut", DONT_WARN_AGAIN]);
});

test("a deletion asks first when code uses the component's name, with or without " +
     "the warning about IDs", () => {
  const places = ["pages/home.nx line 3"];
  const named = deleteQuestion("Delete", ["b0"], places, [], true);
  assert.equal(named.message,
               "The project will no longer build: code still uses b0 in 1 place " +
               "(pages/home.nx line 3). Delete anyway?");
  assert.equal(named.detail, undefined);
  assert.deepEqual(named.buttons, ["Delete"]);
  // Both in one dialog: the places in the message, the IDs in the detail.
  const both = deleteQuestion("Delete", ["b0"], places, ["b1"], true);
  assert.equal(both.message, named.message);
  assert.match(both.detail, /the ID of 1 component after it/);
  assert.deepEqual(both.buttons, ["Delete", DONT_WARN_AGAIN]);
  // With the warning turned off, only the question about the places remains.
  assert.deepEqual(deleteQuestion("Delete", ["b0"], places, ["b1"], false), named);
  const many = deleteQuestion("Delete", ["b0"], Array.from({ length: 7 }, (_, n) => `p${n}`),
                              [], true);
  assert.match(many.message, /in 7 places \(p0, p1, p2, p3, p4, \.\.\.\)/);
});

test("a move asks first, with a button that turns the warning off", () => {
  const question = moveQuestion(["b0"]);
  assert.equal(question.message, "Move b0?");
  assert.match(question.detail, /^This will change the IDs of components on the page\./);
  assert.deepEqual(question.buttons, ["Move", DONT_WARN_AGAIN]);
});
