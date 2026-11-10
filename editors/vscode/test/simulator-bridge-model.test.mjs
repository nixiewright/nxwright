// Which controls the Simulator section shows and enables, depending on
// whether the MCU port is joined to a real screen
// (media/simulator-bridge-model.mjs). Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { bridgeControls } from "../media/simulator-bridge-model.mjs";

const PORTS = { mcuConnected: true, screenConnected: true, finding: false, simulator: null };

test("Goes to shows only while both ports are connected", () => {
  assert.equal(bridgeControls({ ...PORTS, bridged: false }).choiceShown, true);
  assert.equal(bridgeControls({ ...PORTS, bridged: false, mcuConnected: false }).choiceShown,
               false);
  assert.equal(bridgeControls({ ...PORTS, bridged: false, screenConnected: false }).choiceShown,
               false);
});

test("while the ports are not joined, everything is offered", () => {
  assert.deepEqual(bridgeControls({ ...PORTS, bridged: false }),
                   { choiceShown: true, choice: "simulator", typingDisabled: false,
                     listsDisabled: false, findDisabled: false });
});

test("while the ports are joined, typing, the lists, and Find are disabled", () => {
  assert.deepEqual(bridgeControls({ ...PORTS, bridged: true }),
                   { choiceShown: true, choice: "screen", typingDisabled: true,
                     listsDisabled: true, findDisabled: true });
});

test("Goes to shows which side answers while both take the MCU's bytes", () => {
  assert.equal(bridgeControls({ ...PORTS, bridged: true, simulator: "listens" }).choice,
               "both-screen");
  assert.equal(bridgeControls({ ...PORTS, bridged: true, simulator: "answers" }).choice,
               "both-simulator");
});

test("Find is disabled while it looks", () => {
  assert.equal(bridgeControls({ ...PORTS, bridged: false, finding: true }).findDisabled, true);
});
