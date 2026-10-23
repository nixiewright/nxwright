// What the Project section shows of a project (media/project-lines.mjs).
import assert from "node:assert/strict";
import { test } from "node:test";
import { projectLines } from "../media/project-lines.mjs";

const INFO = { format: 1, currentFormat: 1, language: "nextion", screen: "NX8048P070",
               size: "800 x 480", rotation: 180, encoding: "iso-8859-1" };
const PROJECT = { name: "app", path: "e:\\Projects\\thermostat\\app", info: INFO };

// A line's parts as one string: links in brackets, pencils as their command.
function written(line) {
  return line.map((part) => part.link ? `[${part.text}]`
                           : part.edit ? `<${part.edit}>` : part.text).join("");
}

test("a project in strict Nextion syntax, with no project file chosen", () => {
  const shown = projectLines(PROJECT);
  assert.deepEqual([shown.name, shown.path, shown.note],
                   ["app", "e:\\Projects\\thermostat\\app", undefined]);
  assert.deepEqual(shown.lines.map(written), [
    "NX8048P070<nxwright.changeScreen> · 800 x 480 · 180°<nxwright.changeRotation> · " +
      "iso-8859-1<nxwright.changeEncoding>",
    "Syntax: strict Nextion ([switch to nxlang])",
    "Project file: none chosen yet<nxwright.chooseProjectFile>",
  ]);
});

test("a project in nxlang has no link to switch", () => {
  const shown = projectLines({ ...PROJECT, info: { ...INFO, language: "nxlang" } });
  assert.deepEqual(shown.lines[1], [{ text: "Syntax: nxlang" }]);
});

test("a chosen project file shows by its name, its path as the tooltip", () => {
  const file = "e:\\Projects\\thermostat\\thermostat.HMI";
  const shown = projectLines({ ...PROJECT, projectFile: file });
  assert.deepEqual(shown.lines[2][0], { text: "Project file: thermostat.HMI", title: file });
});

test("an older folder shows no screen line, so nothing to change there, and a note", () => {
  const shown = projectLines({ ...PROJECT, info: { format: 1, currentFormat: 2 } });
  assert.match(shown.note, /source format 1\. Upgrade/);
  assert.deepEqual(shown.lines.map(written),
                   ["Project file: none chosen yet<nxwright.chooseProjectFile>"]);
});

test("before the server answers, the project file alone", () => {
  assert.deepEqual(projectLines({ ...PROJECT, info: null }).lines.length, 1);
});
