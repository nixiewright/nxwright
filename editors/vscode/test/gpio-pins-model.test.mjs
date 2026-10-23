// The GPIO pins as the Simulator section lists them (media/gpio-pins-model.mjs).
// Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { pinRows } from "../media/gpio-pins-model.mjs";

test("each pin shows what it is and its level, and an input's level can change", () => {
  const rows = pinRows([
    { mode: 0, component: null, level: 1 },
    { mode: 1, component: "b0", level: 1 },
    { mode: 1, component: null, level: 0 },
    { mode: 2, component: null, level: 0 },
    { mode: 3, component: null, level: 1 },
    { mode: 4, component: null, level: 1 },
  ]);
  assert.deepEqual(rows.map((row) => [row.name, row.kind, row.level, row.settable]), [
    ["io0", "input", 1, true],
    ["io1", "input, bound to b0", 1, true],
    ["io2", "input", 0, true],
    ["io3", "output", 0, false],
    // A PWM output's level changes too fast to show.
    ["io4", "PWM output", null, false],
    ["io5", "open-drain output", 1, false],
  ]);
});

test("a click's tooltip says what it gives the pin, and what a bound pin then runs", () => {
  const rows = pinRows([
    { mode: 0, component: null, level: 1 },
    { mode: 1, component: "b0", level: 1 },
    { mode: 1, component: "b0", level: 0 },
    { mode: 2, component: null, level: 0 },
  ]);
  assert.deepEqual(rows.map((row) => row.title), [
    "Set io0 to 0", "Set io1 to 0, which presses b0", "Set io2 to 1, which releases b0",
    undefined,
  ]);
});
