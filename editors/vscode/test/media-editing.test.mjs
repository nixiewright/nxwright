// What deleting, replacing, or renaming a resource from the Media section
// asks (src/mediaEditing.ts, compiled to out/ before the tests run), and the
// questions of adding one filled in with a resource's settings
// (src/mediaCommands.ts).
import assert from "node:assert/strict";
import { test } from "node:test";
import { deleteDialog, deleteTarget, isPlaceholder, newNameCheck, removeArguments,
         renameArguments, replaceArguments, warningText } from "../out/mediaEditing.js";
import { animationArguments, pictureArguments, videoArguments } from "../out/mediaCommands.js";

// What Delete deletes: the picture `name`, ID `id`, with `later` after it.
function target(name, id, later, kind = "picture", encoding = "iso-8859-1") {
  return { kind, name, id, later, encoding };
}

const actions = (dialog) => dialog.buttons.map((button) => button.action);

test("what Delete deletes is read from the names of its list", () => {
  assert.deepEqual(deleteTarget("picture", "b", ["a", "b", "c"], "utf-8"),
                   { kind: "picture", name: "b", id: 1, later: ["c"], encoding: "utf-8" });
  assert.deepEqual(deleteTarget("page", "c", ["a", "b", "c"], undefined).later, []);
  // A name the list no longer has.
  assert.equal(deleteTarget("picture", "d", ["a", "b", "c"], "utf-8"), undefined);
});

test("the last of its kind is deleted after a plain confirmation", () => {
  const dialog = deleteDialog(target("logo", 2, []));
  assert.equal(dialog.message, "Delete the picture logo?");
  assert.equal(dialog.detail, "");
  assert.deepEqual(actions(dialog), ["delete"]);
});

test("IDs that would shift: an empty slot by default, a shift, or names for the numbers", () => {
  const dialog = deleteDialog(target("logo", 1, ["b", "c"]));
  assert.equal(dialog.message, "Delete the picture logo?");
  assert.match(dialog.detail,
               /^Deleting the picture logo will change the IDs of pictures 2 to 3 \(b and c\)\./);
  assert.deepEqual(actions(dialog), ["keepIds", "shift", "namesForNumbers"]);
  assert.match(dialog.detail, /microcontroller/);
  assert.match(dialog.detail, /Leave an Empty Slot keeps every ID/);
  assert.match(dialog.detail, /Delete and Shift IDs removes/);
  assert.match(dialog.detail, /Replace Numbers with Names first replaces/);
  assert.match(deleteDialog(target("logo", 1, ["b"])).detail,
               /^Deleting the picture logo will change the ID of picture 2 \(b\)\./);
  const many = deleteDialog(target("logo", 0, ["a", "b", "c", "d", "e", "f", "g"]));
  assert.match(many.detail, /pictures 1 to 7 \(a, b, c, d, e and 2 more\)\./);
});

test("once the numbers were written as names, the question no longer offers it", () => {
  const after = deleteDialog(target("logo", 1, ["b"]), true);
  assert.deepEqual(actions(after), ["keepIds", "shift"]);
  // The detail explains only the buttons the question offers.
  assert.doesNotMatch(after.detail, /Replace Numbers with Names/);
  assert.match(after.detail, /Leave an Empty Slot keeps every ID/);
});

test("a placeholder is not offered another in its place", () => {
  const dialog = deleteDialog(target("empty-slot-1", 0, ["b"]));
  assert.deepEqual(actions(dialog), ["shift", "namesForNumbers"]);
  assert.doesNotMatch(dialog.detail, /Empty Slot/);
  assert.equal(isPlaceholder("empty-slot-12"), true);
  assert.equal(isPlaceholder("empty-slot-0"), false);
  assert.equal(isPlaceholder("logo"), false);
  // An empty slot page's name has underscores, so that code can use it.
  assert.equal(isPlaceholder("empty_slot_3", "page"), true);
  assert.equal(isPlaceholder("empty-slot-3", "page"), false);
});

test("a page's empty slot is a blank page, reused by renaming it", () => {
  const dialog = deleteDialog(target("settings", 1, ["about"], "page"));
  assert.match(dialog.detail, /^Deleting the page settings will change the ID of page 2 \(about\)/);
  assert.match(dialog.detail, /a blank page takes settings's place, and you can reuse it by renaming it/);
  assert.deepEqual(actions(dialog), ["keepIds", "shift", "namesForNumbers"]);
  // An empty slot page is not offered another in its place.
  assert.deepEqual(actions(deleteDialog(target("empty_slot_1", 1, ["about"], "page"))),
                   ["shift", "namesForNumbers"]);
});

test("a font's empty slot in a two-byte encoding says what it takes", () => {
  assert.match(warningText(target("Big", 0, ["b"], "font", "gb2312"), false, true), /135 KB/);
  assert.doesNotMatch(warningText(target("Big", 0, ["b"], "font"), false, true), /135 KB/);
  // A folder without device settings has no encoding.
  assert.doesNotMatch(warningText(target("Big", 0, ["b"], "font", undefined), false, true),
                      /135 KB/);
});

test("the command that deletes: an empty slot, and the check, only when asked for", () => {
  const logo = target("logo", 1, ["b"]);
  assert.deepEqual(removeArguments("app", logo, false, false),
                   ["remove", "app", "picture", "logo"]);
  assert.deepEqual(removeArguments("app", logo, true, false),
                   ["remove", "app", "picture", "logo", "--keep-ids"]);
  assert.deepEqual(removeArguments("app", logo, false, true),
                   ["remove", "app", "picture", "logo", "--checked"]);
  assert.deepEqual(removeArguments("app", target("settings", 1, [], "page"), true, true),
                   ["remove", "app", "page", "settings", "--keep-ids", "--checked"]);
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
  assert.deepEqual(replaceArguments(["animation", "app", "a.png", "--duration", "80"], "blink",
                                    undefined, false),
                   ["replace", "app", "animation", "blink", "a.png", "--duration", "80"]);
  assert.deepEqual(replaceArguments(["picture", "app", "a.png"], "empty-slot-1", "logo", false),
                   ["replace", "app", "picture", "empty-slot-1", "a.png", "--name", "logo"]);
});

test("replacing and renaming are checked only when asked for", () => {
  assert.deepEqual(replaceArguments(["picture", "app", "a.png"], "empty-slot-1", "logo", true),
                   ["replace", "app", "picture", "empty-slot-1", "a.png", "--name", "logo",
                    "--checked"]);
  // Without a new name, the resource keeps its name, so there are no uses to look for.
  assert.deepEqual(replaceArguments(["picture", "app", "a.png"], "logo", undefined, true),
                   ["replace", "app", "picture", "logo", "a.png"]);
  assert.deepEqual(renameArguments("app", "picture", "a", "logo", false),
                   ["rename", "app", "picture", "a", "logo"]);
  assert.deepEqual(renameArguments("app", "sound", "beep", "chime", true),
                   ["rename", "app", "sound", "beep", "chime", "--checked"]);
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
