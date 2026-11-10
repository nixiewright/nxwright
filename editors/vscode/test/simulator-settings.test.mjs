// The simulator's settings filling in a simulation's launch configuration
// (src/simulatorSettings.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { emulatorStep } from "../out/emulatorSession.js";
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

// Returns a project for which the port `remembered` was last chosen. The
// project has an MCU emulator only if `hasEmulator` is true.
const chose = (remembered, hasEmulator = false) => ({ remembered, hasEmulator });

test("the port last chosen for the project comes before the settings' port", () => {
  const config = { type: "nxwright", sourceFolder: "app" };
  assert.deepEqual(
    withSimulatorSettings(config, settings, chose({ kind: "serial", name: "COM7", baud: 9600 }))
      .serialPort,
    { name: "COM7", baud: 9600 });
  assert.deepEqual(
    withSimulatorSettings(config, settings, chose({ kind: "tcp", address: "127.0.0.1:7000" }))
      .serialPort,
    { tcp: "127.0.0.1:7000" });
  // None chosen: the settings' port is not connected.
  assert.equal(withSimulatorSettings(config, settings, chose({ kind: "none" })).serialPort,
               "none");
});

test("the project's MCU emulator comes after the settings' port", () => {
  const config = { type: "nxwright", sourceFolder: "app" };
  const empty = { ...settings, serialPort: "" };
  assert.equal(withSimulatorSettings(config, empty, chose(undefined, true)).serialPort,
               "emulator");
  assert.deepEqual(withSimulatorSettings(config, settings, chose(undefined, true)).serialPort,
                   { name: "COM4", baud: 115200 });
  // Chosen in the section, the emulator comes before the settings' port.
  assert.equal(withSimulatorSettings(config, settings, chose({ kind: "emulator" }, true))
    .serialPort, "emulator");
  // If the user chose the emulator and the project no longer has one, that
  // choice is skipped.
  assert.deepEqual(withSimulatorSettings(config, settings, chose({ kind: "emulator" }))
    .serialPort, { name: "COM4", baud: 115200 });
  assert.equal(withSimulatorSettings(config, empty, chose({ kind: "emulator" })).serialPort,
               undefined);
  // None chosen: the simulation starts without a port, even though the
  // project has an MCU emulator.
  assert.equal(withSimulatorSettings(config, empty, chose({ kind: "none" }, true)).serialPort,
               "none");
});

test("the configuration's own port comes before the port last chosen", () => {
  const chosen = chose({ kind: "tcp", address: "127.0.0.1:7000" });
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
  assert.deepEqual(defaultPort(settings, chose(undefined)),
                   { serialPort: { name: "COM4", baud: 115200 }, shown: "COM4",
                     from: "settings" });
  assert.deepEqual(defaultPort(empty, chose(undefined)),
                   { serialPort: undefined, shown: "", from: undefined });
  assert.deepEqual(defaultPort(settings, chose({ kind: "tcp", address: "127.0.0.1:7000" })),
                   { serialPort: { tcp: "127.0.0.1:7000" }, shown: "127.0.0.1:7000",
                     from: "choice" });
  // None chosen: no port, so nothing to ask the user about.
  assert.deepEqual(defaultPort(settings, chose({ kind: "none" })),
                   { serialPort: "none", shown: "", from: "choice" });
  assert.deepEqual(defaultPort(empty, chose(undefined, true)),
                   { serialPort: "emulator", shown: "the MCU emulator", from: "project" });
  assert.deepEqual(defaultPort(settings, chose({ kind: "emulator" }, true)),
                   { serialPort: "emulator", shown: "the MCU emulator", from: "choice" });
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

test("the app does not wait for an emulator that the extension will not start", () => {
  const config = { type: "nxwright", sourceFolder: "app", serialPort: "emulator" };
  // The project has no emulator, or the Python debugger is missing.
  assert.equal(withSimulatorSettings(config, settings).emulatorWait, 0);
  assert.equal(withSimulatorSettings(config, settings, { hasEmulator: true }).emulatorWait, 0);
  assert.equal(withSimulatorSettings({ ...config, serialPort: { emulator: true } }, settings)
    .emulatorWait, 0);
  // The emulator's port may come from the project, not from the configuration.
  const empty = { ...settings, serialPort: "" };
  assert.equal(withSimulatorSettings({ sourceFolder: "app" }, empty, { hasEmulator: true })
    .emulatorWait, 0);
  // The configuration's own wait stays.
  assert.equal(withSimulatorSettings({ ...config, emulatorWait: 30 }, settings).emulatorWait, 30);
});

test("the app's wait is left to the project when the extension starts the emulator", () => {
  const starts = { hasEmulator: true, startsEmulator: true };
  const config = { type: "nxwright", sourceFolder: "app", serialPort: "emulator" };
  assert.equal("emulatorWait" in withSimulatorSettings(config, settings, starts), false);
  assert.equal(withSimulatorSettings({ ...config, emulatorWait: 0 }, settings, starts)
    .emulatorWait, 0);
});

test("a simulation an agent starts without a port starts no emulator", () => {
  // The agent channel gives such a simulation a serialPort of null.
  const starts = { hasEmulator: true, startsEmulator: true };
  const empty = { ...settings, serialPort: "" };
  const filled = withSimulatorSettings({ sourceFolder: "app", serialPort: null }, empty, starts);
  assert.equal(filled.serialPort, null);
  assert.equal("emulatorWait" in filled, false);
  // The adapter then reports a port that is not connected.
  assert.equal(emulatorStep({ kind: "serial", name: null, baud: 9600, connected: false },
                            undefined), "keep");
});

test("a simulation with another port gets no wait for the emulator", () => {
  assert.equal("emulatorWait" in withSimulatorSettings({ sourceFolder: "app" }, settings), false);
  assert.equal("emulatorWait" in withSimulatorSettings(
    { sourceFolder: "app", serialPort: "none" }, settings, { hasEmulator: true }), false);
});
