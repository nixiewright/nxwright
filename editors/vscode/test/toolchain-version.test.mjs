// The oldest toolchain the extension works with, and its warning for an older
// one (src/toolchainVersion.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { isOlder, toolchainWarning, warnerOnce } from "../out/toolchainVersion.js";

test("versions compare by their dotted numbers, one by one", () => {
  assert.equal(isOlder("0.1.0", "0.2.0"), true);
  assert.equal(isOlder("0.9.0", "0.10.0"), true);
  assert.equal(isOlder("0.2.0", "0.2.0"), false);
  assert.equal(isOlder("1.0.0", "0.9.9"), false);
  // A missing number counts as 0.
  assert.equal(isOlder("0.1", "0.1.0"), false);
  assert.equal(isOlder("0.1", "0.1.1"), true);
  // Text that is not a version is not older, so that nothing is warned of by mistake.
  assert.equal(isOlder("unknown", "0.1.0"), false);
  assert.equal(isOlder("0.1.0rc1", "0.2.0"), false);
});

test("an older toolchain is warned of, with both versions", () => {
  assert.equal(toolchainWarning("0.1.0", "0.3.0"),
               "nxwright: this extension needs nxwright 0.3.0 or later, and the one installed is " +
               "0.1.0. To update it, run git pull in your copy of nxwright, then pip install . there.");
  assert.equal(toolchainWarning("0.3.0", "0.3.0"), undefined);
  // A source copy that is not installed reports no version, and is not checked.
  assert.equal(toolchainWarning(undefined, "0.3.0"), undefined);
});

test("the warning shows once, however often the server starts", () => {
  const shown = [];
  const warn = warnerOnce((warning) => shown.push(warning), "0.3.0");
  warn("0.3.0");
  warn("0.1.0");
  warn("0.1.0");
  assert.equal(shown.length, 1);
});
