// What the Project section shows of a project (media/project-lines.mjs).
import assert from "node:assert/strict";
import { test } from "node:test";
import { projectLines } from "../media/project-lines.mjs";

const INFO = { format: 1, currentFormat: 1, language: "nextion", screen: "NX8048P070",
               size: "800 x 480", rotation: 180, encoding: "iso-8859-1" };
const PROJECT = { name: "app", path: "e:\\Projects\\thermostat\\app", info: INFO };

// A line's parts as one string: links in brackets, pencils as their command,
// the link button as {on} or {off}.
function written(line) {
  return line.map((part) => part.link ? `[${part.text}]`
                           : part.edit ? `<${part.edit}>`
                           : part.toggle ? `{${part.on ? "on" : "off"}}` : part.text).join("");
}

// A step of the chain as one string: its button, then its parts.
function step(shown) {
  const { text, command, disabledTitle } = shown.button;
  return `[${text}: ${disabledTitle ? `disabled, ${disabledTitle}` : command}] ` +
    written(shown.parts);
}

const PROJECT_FILE = "e:\\Projects\\thermostat\\thermostat.HMI";
const TFT_FILE = "e:\\Projects\\thermostat\\thermostat.tft";

test("a project in strict Nextion syntax, with no file chosen", () => {
  const shown = projectLines(PROJECT);
  assert.deepEqual([shown.name, shown.path, shown.note],
                   ["app", "e:\\Projects\\thermostat\\app", undefined]);
  assert.deepEqual(shown.lines.map(written), [
    "NX8048P070<nxwright.changeScreen> · 800 x 480 · 180°<nxwright.changeRotation> · " +
      "iso-8859-1<nxwright.changeEncoding>",
    "Syntax: strict Nextion ([switch to nxlang])",
  ]);
  // With no project file, there is nothing to build, so Build HMI is disabled.
  assert.deepEqual(shown.steps.map(step), [
    "[Build HMI: disabled, Choose a project file first] " +
      "no project file<nxwright.chooseProjectFile>",
    "[Compile TFT: nxwright.compile] no TFT file<nxwright.chooseTftFile>",
    "[Upload TFT: nxwright.upload] no screen<nxwright.chooseScreen>",
  ]);
  // A disabled button has no command for a click to run.
  assert.equal(shown.steps[0].button.command, undefined);
});

test("a project in nxlang has no link to switch", () => {
  const shown = projectLines({ ...PROJECT, info: { ...INFO, language: "nxlang" } });
  assert.deepEqual(shown.lines[1], [{ text: "Syntax: nxlang" }]);
});

test("chosen files show by their names, their paths as the tooltips", () => {
  const shown = projectLines({ ...PROJECT, projectFile: PROJECT_FILE, tftFile: TFT_FILE,
                               linked: true });
  assert.deepEqual(shown.steps.map(step), [
    "[Build HMI: nxwright.build] thermostat.HMI<nxwright.chooseProjectFile>{on}",
    "[Compile TFT: nxwright.compile] thermostat.tft<nxwright.chooseTftFile>",
    "[Upload TFT: nxwright.upload] no screen<nxwright.chooseScreen>",
  ]);
  assert.deepEqual(shown.steps[0].parts[0], { text: "thermostat.HMI", title: PROJECT_FILE });
  assert.deepEqual(shown.steps[1].parts[0], { text: "thermostat.tft", title: TFT_FILE });
  assert.deepEqual(shown.steps.map((each) => each.button?.glyph),
                   ["build", "compile", "upload"]);
});

test("the link button says whether Compile also writes the project file", () => {
  const linked = projectLines({ ...PROJECT, projectFile: PROJECT_FILE, linked: true });
  assert.deepEqual(linked.steps[0].parts[2], {
    toggle: "nxwright.toggleProjectFileLink", on: true,
    title: "Compile also writes thermostat.HMI. Click to leave it as it is.",
  });
  const apart = projectLines({ ...PROJECT, projectFile: PROJECT_FILE, linked: false });
  assert.deepEqual(apart.steps[0].parts[2], {
    toggle: "nxwright.toggleProjectFileLink", on: false,
    title: "Compile leaves thermostat.HMI as it is. Click to have Compile write it too.",
  });
});

test("an older folder shows no screen line, so nothing to change there, and a note", () => {
  const shown = projectLines({ ...PROJECT, info: { format: 1, currentFormat: 2 } });
  assert.match(shown.note, /source format 1\. Upgrade/);
  assert.deepEqual(shown.lines, []);
  assert.equal(shown.steps.length, 3);
});

test("before the server answers, the chain alone", () => {
  const shown = projectLines({ ...PROJECT, info: null });
  assert.deepEqual([shown.lines.length, shown.steps.length], [0, 3]);
});

test("the screen shows by its port and upload rate, the model it answered as the tooltip", () => {
  const shown = projectLines({ ...PROJECT, screen: { port: "COM5", rate: 921600,
                                                     model: "NX8048P070_011C" } });
  assert.equal(step(shown.steps[2]),
               "[Upload TFT: nxwright.upload] COM5 · 921600<nxwright.chooseScreen>");
  assert.deepEqual(shown.steps[2].parts[0], {
    text: "COM5 · 921600", title: "The screen on COM5 last answered as NX8048P070_011C" });
  // Before any screen answered, the port and rate alone.
  const unseen = projectLines({ ...PROJECT, screen: { port: "COM5", rate: 115200 } });
  assert.deepEqual(unseen.steps[2].parts[0], { text: "COM5 · 115200" });
});
