// The app's name the sections show, and the file Build's dialog starts from
// (src/projectName.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { appName, projectFileName } from "../out/projectName.js";

test("the app's name, as the server gives it, or else its folder's", () => {
  assert.equal(appName({ name: "Kitchen clock" }, "/work/app"), "Kitchen clock");
  assert.equal(appName({}, "/work/app"), "app");
  assert.equal(appName(undefined, "/work/app"), "app");
  assert.equal(appName(null, "/work/app"), "app");
});

test("the file Build's dialog starts from, named after the app", () => {
  assert.equal(projectFileName("Living room"), "Living room.HMI");
  // Less what a file name cannot hold, and the dots and spaces at its end.
  assert.equal(projectFileName("Thermostat: v2 <beta>?"), "Thermostat v2 beta.HMI");
  assert.equal(projectFileName("Clock. ."), "Clock.HMI");
  // Nothing left, or a name Windows reserves, with a suffix or not: no file name.
  for (const name of ["???", "CON", "con", "Com1", "LPT9", "nul.v2"]) {
    assert.equal(projectFileName(name), undefined, name);
  }
});
