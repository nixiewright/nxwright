// What extract does with a project holding what nxwright does not know, from
// the lines `nxwright extract --list-unknown` prints: it extracts, asks
// first, or refuses (src/unknownContent.ts, compiled to out/ before the tests
// run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { extractChoice } from "../out/unknownContent.js";

function line(what, where, sort) {
  return JSON.stringify({ what, where, sort, bytes: "00" });
}

test("a project without unknown content is extracted", () => {
  assert.deepEqual(extractChoice(""), { kind: "extract" });
});

test("content kept exactly is extracted, the command noting it", () => {
  const listed = line("a component type nxwright does not know", "block 0.pa, object 1",
    "kept exactly");
  assert.deepEqual(extractChoice(listed + "\n"), { kind: "extract" });
});

test("content that may be lost asks first, naming each", () => {
  const listed = [line("a block of a kind nxwright does not handle", "block 2.ib", "may be lost"),
    line("a manifest header byte the build writes as 79", "manifest header, byte 14",
      "may be lost")].join("\n");
  const choice = extractChoice(listed);
  assert.equal(choice.kind, "ask");
  assert.match(choice.message, /a block of a kind nxwright does not handle \(block 2\.ib\)/);
  assert.match(choice.message, /\(manifest header, byte 14\)/);
  assert.match(choice.message, /nxwright report/);
});

test("content that cannot be kept is refused, whatever else there is", () => {
  const listed = [line("a block of a kind nxwright does not handle", "block 2.ib", "may be lost"),
    line("an attribute nxwright does not know, newattr, on a page",
      "block 0.pa, object 0, attribute newattr", "cannot be kept")].join("\n");
  const choice = extractChoice(listed);
  assert.equal(choice.kind, "refuse");
  assert.match(choice.message, /newattr/);
  assert.doesNotMatch(choice.message, /2\.ib/);
});

test("a list that cannot be read is refused", () => {
  const choice = extractChoice("not json\n");
  assert.equal(choice.kind, "refuse");
  assert.match(choice.message, /could not be read/);
});
