// The extension's problem matcher (package.json, problemMatchers), on the
// lines that nxwright prints. Run with `npm test`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const matcher = manifest.contributes.problemMatchers.find((entry) => entry.name === "nxwright");
const pattern = new RegExp(matcher.pattern.regexp);

// Returns the file, line number, severity, and message that the matcher finds
// in `line`, or null when `line` does not match.
function read(line) {
  const found = pattern.exec(line);
  return found && [matcher.pattern.file, matcher.pattern.line, matcher.pattern.severity,
                   matcher.pattern.message].map((group) => found[group]);
}

test("a line of nxwright check, with a relative path", () => {
  assert.deepEqual(read("app\\pages\\home.nx:12: error: unknown name `speed`"),
                   ["app\\pages\\home.nx", "12", "error", "unknown name `speed`"]);
  assert.deepEqual(read("app/pages/home.page.toml:9: warning: no title"),
                   ["app/pages/home.page.toml", "9", "warning", "no title"]);
});

test("a line of a command that failed, which starts with the command's name", () => {
  assert.deepEqual(read("nxwright build: app\\pages\\home.nx:12: unknown name `speed`"),
                   ["app\\pages\\home.nx", "12", undefined, "unknown name `speed`"]);
});

test("the colon of a drive letter is not taken for the colon before the line number", () => {
  assert.deepEqual(read("C:\\projects\\app\\pages\\home.nx:12: error: unknown name `speed`"),
                   ["C:\\projects\\app\\pages\\home.nx", "12", "error", "unknown name `speed`"]);
});

test("a path with a space", () => {
  assert.deepEqual(read("C:\\My Projects\\app\\pages\\home.nx:12: error: no good"),
                   ["C:\\My Projects\\app\\pages\\home.nx", "12", "error", "no good"]);
});

test("the form an older nxwright prints", () => {
  assert.deepEqual(read("pages/home.nx line 12: error: unknown name `speed`"),
                   ["pages/home.nx", "12", "error", "unknown name `speed`"]);
});

test("a line without a place does not match", () => {
  assert.equal(read("nxwright check: 1 errors, 0 warnings"), null);
  assert.equal(read("Wrote app.HMI"), null);
});

test("a path may be relative or full", () => {
  assert.deepEqual(matcher.fileLocation, ["autoDetect", "${workspaceFolder}"]);
});
