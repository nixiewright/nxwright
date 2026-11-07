// Tests the text that Switch to nxlang shows about the lines the switch will
// change, both in the panel (media/nxlang-changes.mjs) and in the
// confirmation before the switch. The confirmation's text is in
// src/nxlangSwitchText.ts, which is compiled to out/ before the tests run.
import assert from "node:assert/strict";
import { test } from "node:test";
import { changesSummary } from "../media/nxlang-changes.mjs";
import { switchConfirmationDetail } from "../out/nxlangSwitchText.js";
import { changedProjectFileDetail, nxlangExtractNotice } from "../out/projectFileText.js";

const CHANGE = { file: "pages/main.nx", line: 12, before: "n0.val=n1.val+n2.val*2",
                 after: "n0.val=(n1.val+n2.val)*2" };

test("the panel offers to expand the list of changes", () => {
  assert.equal(changesSummary([CHANGE]),
               "Expand to see the lines that will change in your project");
});

test("the panel says when the project needs no change", () => {
  assert.equal(changesSummary([]),
               "Your project does not require any changes to switch to nxlang.");
});

test("the confirmation counts the lines that will change", () => {
  assert.equal(switchConfirmationDetail(3),
               "3 line(s) of code will change, so that they keep calculating the same way. " +
               "There is no command to switch back, and you will not be able to extract " +
               "changes made in the Nextion Editor into this folder.");
});

test("the confirmation says when the project needs no change", () => {
  assert.equal(switchConfirmationDetail(0),
               "Your project does not require any changes to switch to nxlang. There is no " +
               "command to switch back, and you will not be able to extract changes made in " +
               "the Nextion Editor into this folder.");
});

test("extract on a folder in nxlang says why it stops, and what to do", () => {
  assert.equal(nxlangExtractNotice("app"),
               "nxwright: app uses nxlang, so nxwright cannot extract over it: the code the " +
               "build writes cannot turn back into nxlang. Make code changes in the source " +
               "folder. To see what the project contains, extract it into a new folder, and " +
               "compare that folder with your source folder.");
});

test("the overwrite warning in nxlang does not promise to bring the changes back", () => {
  assert.equal(changedProjectFileDetail(true, true),
               "The new file will not have those changes, and they cannot come back into the " +
               "source folder. The old file will be kept as a backup. To see those changes, " +
               "you can extract the old file into a new folder.");
  assert.equal(changedProjectFileDetail(true, false),
               "The new file will not have those changes, and they cannot come back into the " +
               "source folder. No backup will be kept. To see those changes, you can extract " +
               "the old file into a new folder.");
});

test("the overwrite warning in strict Nextion syntax offers to extract first", () => {
  assert.equal(changedProjectFileDetail(false, true),
               "The new file will not have those changes. The old file will be kept as a " +
               "backup. Extract First brings those changes into the source folder.");
  assert.equal(changedProjectFileDetail(false, false),
               "The new file will not have those changes. No backup will be kept. Extract " +
               "First brings those changes into the source folder.");
});
