// What setting a component's `key` in the properties panel does
// (src/keyBinding.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { keyChange, makeKeyChange } from "../out/keyBinding.js";

const binding = { keyboard: "keyboard", present: false, local: false, chinese: false,
                  fonts: [] };

test("a keyboard the folder lacks is added", () => {
  assert.deepEqual(keyChange("t0", 1, binding),
                   { question: null, values: { key: 1 }, keyboard: "keyboard", note: null });
});

test("a keyboard the folder has is not added again", () => {
  assert.equal(keyChange("t0", 1, { ...binding, present: true }).keyboard, null);
});

test("a component of local scope is made global, once confirmed", () => {
  const change = keyChange("t0", 2, { ...binding, keyboard: "keypad", local: true });
  assert.match(change.question, /global scope\. Make t0 global\?/);
  assert.deepEqual(change.values, { key: 2, vscope: 1 });
});

test("Chinese input outside a gb2312 folder adds nothing, and says why", () => {
  const change = keyChange("t0", 4, { ...binding, keyboard: null, chinese: true });
  assert.equal(change.keyboard, null);
  assert.match(change.note, /only works in a gb2312 project/);
});

test("Chinese input in a gb2312 folder adds the Chinese keyboard", () => {
  const change = keyChange("t0", 4, { ...binding, keyboard: "chinese-input", chinese: true });
  assert.equal(change.keyboard, "chinese-input");
  assert.equal(change.note, null);
});

test("no keyboard: only the key is set", () => {
  assert.deepEqual(keyChange("t0", 255, { ...binding, keyboard: null }),
                   { question: null, values: { key: 255 }, keyboard: null, note: null });
});

// The steps VS Code would take, as a list of what was done; each answers as
// `answers` says, or yes.
function steps(answers = {}) {
  const done = [];
  return {
    done,
    appTomlUnsaved: () => { done.push("check app.toml"); return answers.unsaved ?? false; },
    confirm: async () => { done.push("ask"); return answers.confirm ?? true; },
    addKeyboard: async (keyboard) => { done.push(`add ${keyboard}`); return answers.add ?? true; },
    setAttributes: async (values) => { done.push(values); return answers.set ?? true; },
    tell: () => { done.push("tell"); },
  };
}

test("a confirmed change adds the keyboard, then sets the key and the scope", async () => {
  const taken = steps();
  const change = keyChange("t0", 1, { ...binding, local: true });
  assert.equal(await makeKeyChange(change, taken), true);
  assert.deepEqual(taken.done, ["check app.toml", "ask", "add keyboard", { key: 1, vscope: 1 }]);
});

test("a refused question changes nothing", async () => {
  const taken = steps({ confirm: false });
  assert.equal(await makeKeyChange(keyChange("t0", 1, { ...binding, local: true }), taken), false);
  assert.deepEqual(taken.done, ["check app.toml", "ask"]);
});

test("unsaved changes to app.toml change nothing", async () => {
  const taken = steps({ unsaved: true });
  assert.equal(await makeKeyChange(keyChange("t0", 1, binding), taken), false);
  assert.deepEqual(taken.done, ["check app.toml"]);
});

test("a keyboard that cannot be added leaves the key as it was", async () => {
  const taken = steps({ add: false });
  assert.equal(await makeKeyChange(keyChange("t0", 1, binding), taken), false);
  assert.deepEqual(taken.done, ["check app.toml", "add keyboard"]);
});

test("a keyboard the folder has: only the key is set, whatever app.toml", async () => {
  const taken = steps({ unsaved: true });
  assert.equal(await makeKeyChange(keyChange("t0", 1, { ...binding, present: true }), taken),
               true);
  assert.deepEqual(taken.done, [{ key: 1 }]);
});

test("Chinese input sets the key, then says why no page is added", async () => {
  const taken = steps();
  const change = keyChange("t0", 4, { keyboard: null, present: false, local: false,
                                      chinese: true });
  assert.equal(await makeKeyChange(change, taken), true);
  assert.deepEqual(taken.done, [{ key: 4 }, "tell"]);
});
