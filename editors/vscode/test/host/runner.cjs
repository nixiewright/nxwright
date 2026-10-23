// The runner of the tests inside VS Code (test/host/*.host.cjs), which
// `npm run test:host` starts (run.mjs). VS Code loads this module in the
// extension host, where `vscode` can be required, and calls its run().
//
// Each test file registers its tests with test(name, body). They run in
// order, files by name, each within a time limit. Each result is printed,
// and run() fails when one test does, which ends VS Code with an exit code
// that run.mjs reports. Node's own test runner will not do here: it runs
// each file in a process of its own, where `vscode` cannot be had.
const fs = require("node:fs");
const path = require("node:path");

// How long a test may take, in milliseconds: the first starts the language
// server, a Python process.
const TIME_LIMIT = 90000;
const tests = [];

// Registers a test: `body` is an async function, which fails by throwing.
function test(name, body) {
  tests.push({ name, body });
}

// Returns found()'s first result that is not false, null, or undefined,
// asked every 100 ms, or fails, naming `what`, after `milliseconds`.
async function waitFor(found, what, milliseconds = 60000) {
  const deadline = Date.now() + milliseconds;
  for (;;) {
    const result = await found();
    if (result !== false && result !== null && result !== undefined) {
      return result;
    }
    if (Date.now() > deadline) {
      throw new Error(`waited ${milliseconds} ms for ${what}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

// The URI of a file of the source folder VS Code opened, by its path in it.
function folderFile(...parts) {
  const vscode = require("vscode");
  return vscode.Uri.joinPath(vscode.workspace.workspaceFolders[0].uri, ...parts);
}

// Settles once `promise` does, or fails once `milliseconds` have passed.
function withinLimit(promise, milliseconds, name) {
  let timer;
  const late = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${name}: still running after ${milliseconds} ms`)),
                       milliseconds);
  });
  return Promise.race([promise, late]).finally(() => clearTimeout(timer));
}

async function run() {
  for (const file of fs.readdirSync(__dirname).filter((name) => name.endsWith(".host.cjs")).sort()) {
    require(path.join(__dirname, file));
  }
  let failed = 0;
  for (const { name, body } of tests) {
    try {
      await withinLimit(Promise.resolve().then(body), TIME_LIMIT, name);
      console.log(`ok - ${name}`);
    } catch (error) {
      failed += 1;
      console.log(`not ok - ${name}\n  ${String(error?.stack ?? error).replace(/\n/g, "\n  ")}`);
    }
  }
  console.log(`# ${tests.length - failed} passed, ${failed} failed`);
  if (failed > 0) {
    throw new Error(`${failed} of ${tests.length} tests inside VS Code failed`);
  }
}

module.exports = { folderFile, run, test, waitFor };
