// The simulator's settings filling in a simulation's launch configuration
// (src/simulatorSettings.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { defaultPort, portChoiceKey, withSimulatorSettings } from "../out/simulatorSettings.js";

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

test("the port last chosen for the project comes before the settings' port", () => {
  const config = { type: "nxwright", sourceFolder: "app" };
  assert.deepEqual(
    withSimulatorSettings(config, settings, { kind: "serial", name: "COM7", baud: 9600 })
      .serialPort,
    { name: "COM7", baud: 9600 });
  assert.deepEqual(
    withSimulatorSettings(config, settings, { kind: "tcp", address: "127.0.0.1:7000" })
      .serialPort,
    { tcp: "127.0.0.1:7000" });
  // None chosen: the settings' port is not connected.
  assert.equal(withSimulatorSettings(config, settings, { kind: "none" }).serialPort, "none");
});

test("the configuration's own port comes before the port last chosen", () => {
  const chosen = { kind: "tcp", address: "127.0.0.1:7000" };
  const own = { sourceFolder: "app", serialPort: { name: "COM9", baud: 9600 } };
  assert.deepEqual(withSimulatorSettings(own, settings, chosen).serialPort,
                   { name: "COM9", baud: 9600 });
  // An agent's simulation started without a port gives null.
  assert.equal(withSimulatorSettings({ sourceFolder: "app", serialPort: null }, settings, chosen)
    .serialPort, null);
  assert.equal(withSimulatorSettings({ sourceFolder: "app", serialPort: "none" }, settings,
                                     chosen).serialPort, "none");
});

test("the port a simulation takes without one of its own, in words", () => {
  const empty = { ...settings, serialPort: "" };
  assert.deepEqual(defaultPort(settings),
                   { serialPort: { name: "COM4", baud: 115200 }, shown: "COM4", chosen: false });
  assert.deepEqual(defaultPort(empty), { serialPort: undefined, shown: "", chosen: false });
  assert.deepEqual(defaultPort(settings, { kind: "tcp", address: "127.0.0.1:7000" }),
                   { serialPort: { tcp: "127.0.0.1:7000" }, shown: "127.0.0.1:7000",
                     chosen: true });
  // None chosen: no port, so nothing to ask the user about.
  assert.deepEqual(defaultPort(settings, { kind: "none" }),
                   { serialPort: "none", shown: "", chosen: true });
});

test("a project's choice is kept under one key, however its folder is written", () => {
  assert.equal(portChoiceKey("C:\\Dev\\Thermostat\\app", "win32"),
               portChoiceKey("c:/dev/thermostat/app", "win32"));
  assert.notEqual(portChoiceKey("C:\\Dev\\thermostat\\app", "win32"),
                  portChoiceKey("C:\\Dev\\other\\app", "win32"));
  assert.notEqual(portChoiceKey("/home/dev/App", "linux"),
                  portChoiceKey("/home/dev/app", "linux"));
  assert.equal(portChoiceKey("/home/dev/thermostat/../thermostat/app", "linux"),
               portChoiceKey("/home/dev/thermostat/app", "linux"));
  // A launch configuration may write the folder from ${workspaceFolder}.
  assert.equal(portChoiceKey("${workspaceFolder}/app", "win32", "C:\\Dev\\thermostat"),
               portChoiceKey("C:\\Dev\\thermostat\\app", "win32"));
});
