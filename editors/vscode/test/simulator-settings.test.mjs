// The simulator's settings filling in a simulation's launch configuration
// (src/simulatorSettings.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { withSimulatorSettings } from "../out/simulatorSettings.js";

const settings = {
  serialPort: "COM4", serialBaud: 115200, sdCard0: "${workspaceFolder}/card", sdCard1: "",
  logReceived: "text", logSent: "hex", pinyinTable: "",
};

test("the settings fill in what a simulation's configuration leaves out", () => {
  assert.deepEqual(withSimulatorSettings({ type: "nxwright", sourceFolder: "app" }, settings), {
    type: "nxwright", sourceFolder: "app", serialPort: { name: "COM4", baud: 115200 },
    sdCard0: "${workspaceFolder}/card", logReceived: "text", logSent: "hex",
  });
});

test("the configuration's own values win", () => {
  const config = {
    type: "nxwright", sourceFolder: "app", serialPort: { name: "COM9", baud: 9600 },
    sdCard0: "C:/cards/first", sdCard1: "C:/cards/second", logSent: "both",
  };
  assert.deepEqual(withSimulatorSettings(config, settings), { ...config, logReceived: "text" });
});

test("settings left empty fill in no port and no card", () => {
  const empty = { ...settings, serialPort: "", sdCard0: "" };
  assert.deepEqual(withSimulatorSettings({ sourceFolder: "app" }, empty),
                   { sourceFolder: "app", logReceived: "text", logSent: "hex" });
});

test("the pinyin table's setting fills in what the configuration leaves out", () => {
  const table = { ...settings, pinyinTable: "C:/Program Files (x86)/Nextion Editor/input.bin" };
  assert.equal(withSimulatorSettings({ sourceFolder: "app" }, table).pinyinTable,
               table.pinyinTable);
  assert.equal(withSimulatorSettings({ sourceFolder: "app", pinyinTable: "app.tft" }, table)
    .pinyinTable, "app.tft");
});

test("a test's configuration is left as it is", () => {
  const config = { type: "nxwright", testFolder: "tests", test: "test_x.Case.test_y" };
  assert.equal(withSimulatorSettings(config, settings), config);
});
