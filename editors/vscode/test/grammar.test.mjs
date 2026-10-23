// The .nx grammar's rules (syntaxes/nxwright.tmLanguage.json), each rule's
// pattern tried on lines as a regular expression, as VS Code tries it.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const grammar = JSON.parse(readFileSync(
  new URL("../syntaxes/nxwright.tmLanguage.json", import.meta.url), "utf8"));

function rule(name) {
  assert.ok(grammar.patterns.some((pattern) => pattern.include === `#${name}`),
            `the grammar uses its rule ${name}`);
  return new RegExp(grammar.repository[name].match);
}

test("a goto's word and the label it jumps to are highlighted", () => {
  const found = rule("goto").exec("  goto again");
  assert.deepEqual([found[1], found[2]], ["goto", "again"]);
  assert.match("goto", rule("keyword"));
});

test("a label line is a label, with a comment after it or not", () => {
  for (const [line, label] of [["again:", "again"], ["  again:", "again"],
                               ["again:  // the loop's top", "again"], ["_turn2:", "_turn2"]]) {
    assert.equal(rule("label").exec(line)?.[1], label, line);
  }
});

test("no keyword ending a line is a label", () => {
  // A grammar cannot share a pattern between rules, so the label rule names
  // the keywords again: each one the keyword rule knows must be among them.
  const keywords = /\\b\(([^)]*)\)/.exec(grammar.repository.keyword.match)[1].split("|");
  assert.ok(keywords.includes("goto") && keywords.includes("else"));
  for (const keyword of keywords) {
    assert.equal(rule("label").exec(`${keyword}:`), null, keyword);
  }
});

test("lines of nxlang that end in a colon are not labels", () => {
  // Nor is a label with code after it, which the Editor does not take.
  for (const line of ["else:", "  default:", "case 3:", "on b0.down:", "again: sys0=1",
                      "if(sys0==1):"]) {
    assert.equal(rule("label").exec(line), null, line);
  }
});

test("sys0 to sys2 are program.nx's variables, not coloured as system variables", () => {
  // The Editor's new project declares them in its program (editor_limits.py).
  assert.match("dim", rule("system-variable"));
  for (const name of ["sys0", "sys1", "sys2"]) {
    assert.doesNotMatch(name, rule("system-variable"), name);
  }
});

test("a macro's heading in macros.nx, its name holding spaces too", () => {
  for (const [line, name] of [["macro my name:", "my name"], ["macro c565_rgb:", "c565_rgb"]]) {
    const found = rule("macro-heading").exec(line);
    assert.deepEqual([found?.[1], found?.[2]], ["macro", name], line);
  }
  // Indented, it is code; a name must start with a letter or an underscore.
  // Nor is a heading with spaces after its colon, which the build refuses.
  for (const line of ["  macro x:", "macro :", "macro 9lives:", "macros x:", "macro x:  "]) {
    assert.equal(rule("macro-heading").exec(line), null, line);
  }
});

test("an event's heading, with nothing after its colon, as the build takes it", () => {
  assert.equal(rule("heading").exec("on b0.down:")?.[2], "b0");
  assert.equal(rule("heading").exec("on b0.down:  "), null);
});
