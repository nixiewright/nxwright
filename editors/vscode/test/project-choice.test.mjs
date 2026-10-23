// Which project the side bar's sections show (src/projectChoice.ts,
// compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { currentProjectOf, ProjectTracker } from "../out/projectChoice.js";

test("the project remembered stays, while its app.toml is there", () => {
  assert.equal(currentProjectOf("c:\\a", true, ["c:\\a", "c:\\b"]), "c:\\a");
});

test("the project remembered stays, even outside the folders found", () => {
  // A file of a project opened from outside the workspace's folders.
  assert.equal(currentProjectOf("c:\\outside", true, ["c:\\a"]), "c:\\outside");
});

test("a project whose app.toml is gone is current no more", () => {
  assert.equal(currentProjectOf("c:\\a", false, ["c:\\b"]), "c:\\b");
  assert.equal(currentProjectOf("c:\\a", false, ["c:\\b", "c:\\c"]), undefined);
});

test("with none remembered, the workspace's only project is current", () => {
  assert.equal(currentProjectOf(undefined, false, ["c:\\only"]), "c:\\only");
});

test("with none remembered and several projects, none is current until one is picked", () => {
  assert.equal(currentProjectOf(undefined, false, ["c:\\a", "c:\\b"]), undefined);
});

test("with no project at all, none is current", () => {
  assert.equal(currentProjectOf(undefined, false, []), undefined);
});

// A server whose answers the test gives by hand, in any order.
function answering() {
  const pending = new Map();
  const ask = (folder) => new Promise((resolve) => pending.set(folder, resolve));
  const answer = async (folder, info) => {
    pending.get(folder)(info);
    // Lets the tracker's awaiting code run.
    await new Promise((resolve) => setImmediate(resolve));
  };
  return { ask, answer };
}

test("a project is current at once, before the server answers", async () => {
  const { ask, answer } = answering();
  let changes = 0;
  const tracker = new ProjectTracker(ask, () => changes++);
  const done = tracker.update("c:\\a");
  assert.equal(tracker.folder, "c:\\a");
  assert.equal(tracker.info, null);
  assert.equal(changes, 1);
  await answer("c:\\a", { format: 2 });
  await done;
  assert.deepEqual(tracker.info, { format: 2 });
  assert.equal(changes, 2);
});

test("an answer about a project no longer current is dropped", async () => {
  const { ask, answer } = answering();
  const tracker = new ProjectTracker(ask, () => {});
  const first = tracker.update("c:\\a");
  const second = tracker.update("c:\\b");
  await answer("c:\\b", { format: 2, language: "nxlang" });
  await answer("c:\\a", { format: 1 });
  await Promise.all([first, second]);
  assert.equal(tracker.folder, "c:\\b");
  assert.deepEqual(tracker.info, { format: 2, language: "nxlang" });
});

test("the same project and answer again tell of no change", async () => {
  const { ask, answer } = answering();
  let changes = 0;
  const tracker = new ProjectTracker(ask, () => changes++);
  const first = tracker.update("c:\\a");
  await answer("c:\\a", { format: 2 });
  await first;
  const again = tracker.update("c:\\a");
  await answer("c:\\a", { format: 2 });
  await again;
  assert.equal(changes, 2);
});

test("no project asks nothing", async () => {
  const tracker = new ProjectTracker(() => assert.fail("asked"), () => {});
  await tracker.update(undefined);
  assert.equal(tracker.folder, undefined);
  assert.equal(tracker.info, null);
});
