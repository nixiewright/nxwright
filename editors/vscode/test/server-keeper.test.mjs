// The language server's starts and stops, and the searches for the command
// that runs nxwright, kept in order (src/serverKeeper.ts, compiled to out/
// before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { ServerKeeper } from "../out/serverKeeper.js";

const FOUND = { command: ["nxwright"], pythons: [] };
const OTHER = { command: ["python", "-P", "-m", "nxwright"], pythons: [["python"]] };
const NONE = { command: undefined, pythons: [["python3"], ["python"]] };

// Steps that record what the keeper does, in `done`, and how many servers
// run at most at once, in `most`. Each search answers the next of `answers`:
// at once, or, after `hold()`, once `release()` opens the gate, whether the
// search began before or after it opened.
function recordingSteps(...answers) {
  const steps = { done: [], running: 0, most: 0, gate: undefined };
  steps.hold = () => {
    steps.gate = new Promise((resolve) => { steps.release = resolve; });
  };
  steps.search = () => {
    steps.done.push("search");
    const answer = answers.shift();
    return steps.gate ? steps.gate.then(() => answer) : Promise.resolve(answer);
  };
  steps.start = async (found) => {
    steps.done.push(found.command ? `start ${found.command.join(" ")}` : "start none");
    if (found.command) {
      steps.running += 1;
      steps.most = Math.max(steps.most, steps.running);
    }
  };
  steps.stop = async () => {
    steps.done.push("stop");
    steps.running = Math.max(steps.running - 1, 0);
  };
  return steps;
}

test("a start takes the latest search, and never searches again", async () => {
  const steps = recordingSteps(FOUND);
  const keeper = new ServerKeeper(steps);
  await keeper.start();
  assert.deepEqual(steps.done, ["search", "start nxwright"]);
});

test("searching again restarts the server only when the command changed", async () => {
  const steps = recordingSteps(FOUND, FOUND, OTHER);
  const keeper = new ServerKeeper(steps);
  await keeper.start();
  await keeper.searchAgain();
  assert.deepEqual(steps.done, ["search", "start nxwright", "search"]);
  await keeper.searchAgain();
  assert.deepEqual(steps.done.slice(3), ["search", "stop", "start python -P -m nxwright"]);
  assert.equal(steps.running, 1);
});

test("a search started while the first start waits ends with one server", async () => {
  // The first search asks for the interpreter chosen in VS Code, whose
  // extension may say, meanwhile, that it chose one.
  const steps = recordingSteps(FOUND, OTHER);
  steps.hold();
  const keeper = new ServerKeeper(steps);
  const starting = keeper.start();
  const again = keeper.searchAgain();
  steps.release();
  await Promise.all([starting, again]);
  assert.deepEqual(steps.done, ["search", "start nxwright", "search", "stop",
                                "start python -P -m nxwright"]);
  assert.equal(steps.most, 1);
});

test("a command run when nxwright was not found searches again", async () => {
  const steps = recordingSteps(NONE, FOUND);
  const keeper = new ServerKeeper(steps);
  await keeper.start();
  assert.deepEqual(await keeper.forCommand(), FOUND);
  // Found since, it starts the server too.
  assert.deepEqual(steps.done, ["search", "start none", "search", "stop", "start nxwright"]);
});

test("a command run when nxwright is still not found gives the Pythons tried", async () => {
  const steps = recordingSteps(NONE, NONE);
  const keeper = new ServerKeeper(steps);
  await keeper.start();
  assert.deepEqual(await keeper.forCommand(), NONE);
  assert.deepEqual(steps.done, ["search", "start none", "search"]);
});

test("a command run while the first start still waits: both end, with one server", async () => {
  // The command's search again queues behind the start; the start does not
  // search again, so neither waits for the other for ever.
  const steps = recordingSteps(NONE, FOUND);
  steps.hold();
  const keeper = new ServerKeeper(steps);
  const starting = keeper.start();
  const command = keeper.forCommand();
  steps.release();
  await starting;
  assert.deepEqual(await command, FOUND);
  assert.deepEqual(steps.done, ["search", "start none", "search", "stop", "start nxwright"]);
  assert.equal(steps.most, 1);
});

test("closing drops a restart still queued, so that no server starts after the stop", async () => {
  const steps = recordingSteps(FOUND, OTHER);
  const keeper = new ServerKeeper(steps);
  await keeper.start();
  steps.hold();
  const again = keeper.searchAgain();
  // The restart's search has begun, and waits.
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(steps.done, ["search", "start nxwright", "search"]);
  // VS Code closes meanwhile: the extension closes the keeper, then stops
  // the server.
  keeper.close();
  await steps.stop();
  steps.release();
  await again;
  assert.deepEqual(steps.done, ["search", "start nxwright", "search", "stop"]);
  assert.equal(steps.running, 0);
});

// Makes `steps`' start wait, once called, until the function it returns is
// called: a language client that takes a while to start.
function slowStart(steps) {
  const start = steps.start;
  let finish;
  steps.start = (found) => new Promise((resolve) => {
    finish = () => start(found).then(resolve);
  });
  return () => finish();
}

test("closing while the first start is under way stops that server once started", async () => {
  // deactivate's own stop finds no server yet, as a client counts only once
  // started: the keeper stops it, and close() resolves after, for VS Code
  // to wait on.
  const steps = recordingSteps(FOUND);
  const finish = slowStart(steps);
  const keeper = new ServerKeeper(steps);
  const starting = keeper.start();
  await new Promise((resolve) => setImmediate(resolve));
  const closing = keeper.close();
  finish();
  await closing;
  assert.deepEqual(steps.done, ["search", "start nxwright", "stop"]);
  assert.equal(steps.running, 0);
  await starting;
});

test("closing while a restart's start is under way stops that server once started", async () => {
  const steps = recordingSteps(FOUND, OTHER);
  const keeper = new ServerKeeper(steps);
  await keeper.start();
  const finish = slowStart(steps);
  const again = keeper.searchAgain();
  await new Promise((resolve) => setImmediate(resolve));
  const closing = keeper.close();
  finish();
  await closing;
  assert.deepEqual(steps.done, ["search", "start nxwright", "search", "stop",
                                "start python -P -m nxwright", "stop"]);
  assert.equal(steps.running, 0);
  await again;
});

test("nothing starts or stops once close() has resolved", async () => {
  // The restart's search closes the keeper as the restart, past its stop,
  // reads the search's finding for its start: the narrowest moment.
  const steps = recordingSteps(FOUND);
  const keeper = new ServerKeeper(steps);
  await keeper.start();
  let read = 0;
  let doneAtClose;
  steps.search = () => {
    steps.done.push("search");
    return {
      then(resolve, reject) {
        read += 1;
        if (read === 2) {
          keeper.close().then(() => { doneAtClose = [...steps.done]; });
        }
        return Promise.resolve(OTHER).then(resolve, reject);
      },
    };
  };
  await keeper.searchAgain();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(steps.done, doneAtClose);
  assert.equal(steps.running, 0);
});

test("close() resolves even when stopping a server started meanwhile fails", async () => {
  // deactivate goes on to its own stop: the failure stays with the start.
  const steps = recordingSteps(FOUND);
  const finish = slowStart(steps);
  steps.stop = async () => { throw new Error("the client would not stop"); };
  const keeper = new ServerKeeper(steps);
  const starting = keeper.start();
  await new Promise((resolve) => setImmediate(resolve));
  const closing = keeper.close();
  finish();
  await closing;
  await assert.rejects(starting, /would not stop/);
});

test("closing with nothing under way resolves at once", async () => {
  const keeper = new ServerKeeper(recordingSteps(FOUND));
  await keeper.close();
});

test("closing during a restart's stop starts no server after it", async () => {
  const steps = recordingSteps(FOUND, OTHER);
  const keeper = new ServerKeeper(steps);
  await keeper.start();
  // The restart's stop takes a while; VS Code closes meanwhile.
  const stop = steps.stop;
  let stopped;
  steps.stop = () => new Promise((resolve) => { stopped = () => stop().then(resolve); });
  const again = keeper.searchAgain();
  await new Promise((resolve) => setImmediate(resolve));
  keeper.close();
  stopped();
  await again;
  assert.deepEqual(steps.done, ["search", "start nxwright", "search", "stop"]);
  assert.equal(steps.running, 0);
});
