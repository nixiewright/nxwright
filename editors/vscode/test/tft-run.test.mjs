// Running the toolchain's commands on TFT files with --json (src/tftRun.ts,
// compiled to out/ before the tests run): reading their JSON objects as they
// come, and what each run gives back. The commands run here are small Node
// scripts in their place.
import assert from "node:assert/strict";
import { test } from "node:test";
import { decompiledReport, JsonLines, roundTripDifferences, runJson } from "../out/tftRun.js";

// A command that runs `script` with Node.
function node(script) {
  return [process.execPath, "-e", script];
}

test("objects are read line by line, whatever the pieces they arrive in", () => {
  const read = [];
  const lines = new JsonLines((event) => read.push(event));
  lines.add('{"event": "pro');
  lines.add('gress", "sent": 4096}\n{"event": "uploaded"}\n{"event":');
  assert.deepEqual(read, [{ event: "progress", sent: 4096 }, { event: "uploaded" }]);
  lines.add(' "end"}');
  lines.end();
  assert.deepEqual(read.at(-1), { event: "end" });
});

test("a line that is not JSON is kept as words, not taken as an object", () => {
  const read = [];
  const lines = new JsonLines((event) => read.push(event));
  lines.add("Traceback (most recent call last):\n{\"event\": \"found\"}\r\n");
  lines.end();
  assert.deepEqual(read, [{ event: "found" }]);
  assert.deepEqual(lines.other, ["Traceback (most recent call last):"]);
});

test("a run gives its exit code, its objects in order, and what it wrote as errors", async () => {
  const seen = [];
  const ran = await runJson(node(
    'console.log(JSON.stringify({event: "a"})); console.error("said"); ' +
    'console.log(JSON.stringify({event: "b"})); process.exit(3)'), [], {
    onEvent: (event) => seen.push(event.event),
  });
  assert.equal(ran.code, 3);
  assert.deepEqual(ran.events.map((event) => event.event), ["a", "b"]);
  assert.deepEqual(seen, ["a", "b"]);
  assert.equal(ran.errors.trim(), "said");
  assert.equal(ran.stopped, false);
});

test("the arguments follow the command's own", async () => {
  const ran = await runJson(node("console.log(JSON.stringify({args: process.argv.slice(1)}))"),
                            ["compile", "a folder", "--json"]);
  assert.deepEqual(ran.events, [{ args: ["compile", "a folder", "--json"] }]);
});

test("a run stopped by its signal ends, and says so", async () => {
  const stop = new AbortController();
  const running = runJson(node(
    'console.log(JSON.stringify({event: "started"})); setInterval(() => {}, 1000)'), [], {
    signal: stop.signal,
    onEvent: () => stop.abort(),
  });
  const ran = await running;
  assert.equal(ran.stopped, true);
  assert.deepEqual(ran.events, [{ event: "started" }]);
});

test("a command that cannot start gives no exit code, and why", async () => {
  const ran = await runJson(["a-program-that-does-not-exist-anywhere"], []);
  assert.equal(ran.code, undefined);
  assert.match(ran.errors, /ENOENT|not found|cannot find/i);
});

test("what a run printed that is not JSON is kept apart from its errors", async () => {
  const ran = await runJson(node('console.log("text3: the text of ID 3"); console.error("said")'),
                            []);
  assert.equal(ran.errors.trim(), "said");
  assert.deepEqual(ran.printed, ["text3: the text of ID 3"]);
});

test("a decompile's warnings are shown once the folder is written", () => {
  const errors = "nxwright decompile: warning: the folder compiles into a file that differs " +
    "from a.tft:\n  page0: 1 in a.tft, 2 compiled again\n";
  assert.deepEqual(decompiledReport("a.tft", "out", errors), {
    message: "nxwright: decompiled a.tft into out, with warnings.",
    detail: "The folder compiles into a file that differs from a.tft:\n" +
      "  page0: 1 in a.tft, 2 compiled again",
  });
  // A decompile the round trip confirmed gives no warning.
  assert.deepEqual(decompiledReport("a.tft", "out", ""),
                   { message: "nxwright: decompiled a.tft into out." });
});

test("the round trip's differences are the decompile's errors, without its advice", () => {
  const errors = [
    "nxwright decompile: warning: the folder compiles into a file that differs from a.tft:",
    "  page0: 1 in a.tft, 2 compiled again",
    "nxwright decompile: there was no terminal to prompt at, so nothing was written. " +
      "Pass --continue-unconfirmed to write this folder.",
  ].join("\n") + "\n";
  assert.equal(roundTripDifferences(errors),
               "The folder compiles into a file that differs from a.tft:\n" +
               "  page0: 1 in a.tft, 2 compiled again");
  // A long list is cut, saying how many lines are left out.
  const many = "nxwright decompile: warning: the folder compiles into a file that differs " +
    "from a.tft:\n" + Array.from({ length: 30 }, (_, n) => `  page${n}: 1, 2`).join("\n");
  const shown = roundTripDifferences(many).split("\n");
  assert.equal(shown.length, 13);
  assert.equal(shown.at(-1), "And 19 more lines, in the output panel.");
});
