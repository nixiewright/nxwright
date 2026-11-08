// What deleting, replacing, or renaming a resource from the Media section
// asks (src/mediaEditing.ts, compiled to out/ before the tests run), and the
// questions of adding one filled in with a resource's settings
// (src/mediaCommands.ts).
import assert from "node:assert/strict";
import { test } from "node:test";
import { deleteDialog, isPlaceholder, newNameCheck, replaceArguments, warningText }
  from "../out/mediaEditing.js";
import { animationArguments, pictureArguments, videoArguments } from "../out/mediaCommands.js";

// A report of the picture `name`, ID `id`, with `later` after it and `uses`.
function report(name, id, later, uses = [], kind = "picture", encoding = "iso-8859-1") {
  return { kind, name, id, encoding, last: later.length === 0, later, uses };
}

const use = (by, of) => ({ path: "pages/main.nx", line: 3, text: "p0.pic=2", by, of });
const actions = (dialog) => dialog.buttons.map((button) => button.action);

test("a resource used by name or by its own ID cannot be deleted", () => {
  for (const by of ["name", "number"]) {
    const dialog = deleteDialog(report("logo", 1, ["b"], [use(by, "itself"), use(by, "itself")]));
    assert.equal(dialog.error, true);
    assert.match(dialog.message, /^Cannot delete the picture logo: it is still used in 2 places\.$/);
    assert.deepEqual(actions(dialog), ["showUses"]);
  }
});

test("the last of its kind is deleted after a plain confirmation", () => {
  const dialog = deleteDialog(report("logo", 2, []));
  assert.equal(dialog.message, "Delete the picture logo?");
  assert.deepEqual(actions(dialog), ["delete"]);
});

test("IDs that would shift: an empty slot by default, or delete and shift", () => {
  const dialog = deleteDialog(report("logo", 1, ["b", "c"]));
  assert.equal(dialog.message, "Delete the picture logo?");
  assert.match(dialog.detail,
               /^Deleting the picture logo will change the IDs of pictures 2 to 3 \(b and c\)\./);
  assert.deepEqual(actions(dialog), ["keepIds", "shift"]);
  assert.match(dialog.detail, /microcontroller/);
  assert.match(dialog.detail, /Leave an Empty Slot keeps every ID/);
  assert.match(deleteDialog(report("logo", 1, ["b"])).detail,
               /^Deleting the picture logo will change the ID of picture 2 \(b\)\./);
  const many = deleteDialog(report("logo", 0, ["a", "b", "c", "d", "e", "f", "g"]));
  assert.match(many.detail, /pictures 1 to 7 \(a, b, c, d, e and 2 more\)\./);
});

test("later IDs given as numbers: no shift until they are names", () => {
  const dialog = deleteDialog(report("logo", 1, ["b"], [use("number", "later")]));
  assert.match(dialog.message, /use some of those IDs as numbers, in 1 place\.$/);
  assert.deepEqual(actions(dialog), ["keepIds", "namesForNumbers", "showUses"]);
  // Once the names were written, those left are to change by hand.
  const after = deleteDialog(report("logo", 1, ["b"], [use("number", "later")]), true);
  assert.match(after.message, /1 place could not be written as names: change them by hand\.$/);
  assert.deepEqual(actions(after), ["keepIds", "showUses"]);
  // The detail explains only the buttons the dialog offers.
  for (const offered of [dialog, after]) {
    assert.doesNotMatch(offered.detail, /Delete and Shift IDs/);
    assert.match(offered.detail, /Leave an Empty Slot keeps every ID/);
  }
  assert.match(deleteDialog(report("logo", 1, ["b"])).detail, /Delete and Shift IDs removes/);
  // A placeholder is offered neither an empty slot nor a shift, so only the risk is told.
  const placeholder = deleteDialog(report("empty-slot-1", 1, ["b"], [use("number", "later")]));
  assert.deepEqual(actions(placeholder), ["namesForNumbers", "showUses"]);
  assert.match(placeholder.detail, /^Code that computes picture IDs/);
  assert.doesNotMatch(placeholder.detail, /Empty Slot|Delete and Shift IDs/);
});

test("a placeholder is not offered another in its place", () => {
  const dialog = deleteDialog(report("empty-slot-1", 0, ["b"]));
  assert.deepEqual(actions(dialog), ["shift"]);
  assert.doesNotMatch(dialog.detail, /Empty Slot/);
  assert.equal(isPlaceholder("empty-slot-12"), true);
  assert.equal(isPlaceholder("empty-slot-0"), false);
  assert.equal(isPlaceholder("logo"), false);
});

test("a font's empty slot in a two-byte encoding says what it takes", () => {
  assert.match(warningText(report("Big", 0, ["b"], [], "font", "gb2312"), false), /135 KB/);
  assert.doesNotMatch(warningText(report("Big", 0, ["b"], [], "font"), false), /135 KB/);
});

test("a new name is checked as nxwright checks it", () => {
  assert.equal(newNameCheck("arrow", "logo", ["logo", "b"]), null);
  assert.equal(newNameCheck("icons/arrow", "logo", ["logo"]), null);
  assert.equal(newNameCheck("Logo", "logo", ["logo"]), null);
  assert.match(newNameCheck("logo", "logo", ["logo"]), /already/);
  assert.match(newNameCheck("B", "logo", ["logo", "b"]), /Another one is named b/);
  assert.match(newNameCheck("a b", "logo", ["logo"]), /letters, digits/);
  assert.match(newNameCheck("icons/Con", "logo", ["logo"]), /Con is reserved by Windows/);
  assert.match(newNameCheck("icons", "logo", ["logo", "icons/arrow"]), /clash with icons\/arrow/);
  assert.match(newNameCheck("b/c", "logo", ["logo", "b"]), /clash with b/);
});

test("adding's arguments become replacing's", () => {
  assert.deepEqual(replaceArguments(["animation", "app", "a.png", "--duration", "80"], "blink"),
                   ["replace", "app", "animation", "blink", "a.png", "--duration", "80"]);
  assert.deepEqual(replaceArguments(["picture", "app", "a.png"], "empty-slot-1", "logo"),
                   ["replace", "app", "picture", "empty-slot-1", "a.png", "--name", "logo"]);
});

// Questions answered in turn from `answers`, each question's second argument
// after its title noted in `values`: a text question's value at first.
function answering(...answers) {
  const values = [];
  const next = (title, first, second) => {
    values.push(second);
    return Promise.resolve(answers.shift());
  };
  return { values, questions: { files: next, text: next, choice: next, folder: next } };
}

test("replacing's questions are filled in with the resource's settings", async () => {
  const animation = answering(["d/a.png"], "120");
  await animationArguments("app", animation.questions, { duration: 120 });
  assert.equal(animation.values[1], "120");
  const video = answering(["d/clip.mp4"], "5", "320,240", "");
  await videoArguments("app", video.questions, { rate: 5, size: [320, 240] });
  assert.deepEqual(video.values.slice(1, 3), ["5", "320,240"]);
  const picture = answering(["d/a.png"]);
  assert.deepEqual(await pictureArguments("app", picture.questions, true),
                   ["picture", "app", "d/a.png"]);
});
