// Tests the text that Switch to nxlang shows about the lines the switch will
// change, both in the panel (media/nxlang-changes.mjs) and in the
// confirmation before the switch. The confirmation's text is in
// src/nxlangSwitchText.ts, which is compiled to out/ before the tests run.
import assert from "node:assert/strict";
import { test } from "node:test";
import { changesSummary } from "../media/nxlang-changes.mjs";
import { switchConfirmationDetail } from "../out/nxlangSwitchText.js";

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
               "There is no command to switch back.");
});

test("the confirmation says when the project needs no change", () => {
  assert.equal(switchConfirmationDetail(0),
               "Your project does not require any changes to switch to nxlang. There is no " +
               "command to switch back.");
});
