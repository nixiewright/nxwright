// The session that runs a project's MCU emulator beside its simulation
// (src/emulatorSession.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { emulatorConfiguration, emulatorStep, isEmulatorPort, listeningAddress }
  from "../out/emulatorSession.js";

const ADDRESS = "127.0.0.1:49480";
const FILE = "C:\\work\\thermostat\\mcu\\main.py";
const WORKSPACE = "C:\\work\\thermostat";

test("without a configuration of its own, the emulator runs in a terminal from its folder", () => {
  assert.deepEqual(emulatorConfiguration(FILE, ADDRESS, [], WORKSPACE, "win32"), {
    type: "debugpy", request: "launch", name: "MCU emulator", program: FILE,
    cwd: "C:\\work\\thermostat\\mcu", console: "integratedTerminal",
    env: { NXWRIGHT_MCU: ADDRESS },
  });
});

test("a Python launch configuration whose program is the emulator's file is used", () => {
  const own = {
    type: "debugpy", request: "launch", name: "My emulator",
    program: "${workspaceFolder}/mcu/main.py", python: "C:\\venv\\python.exe",
    args: ["--fast"], env: { SENSOR: "outdoor" },
  };
  const others = [
    { type: "nxwright", request: "launch", name: "Simulate", sourceFolder: "${workspaceFolder}" },
    { type: "debugpy", request: "launch", name: "Another", program: "${workspaceFolder}/tool.py" },
  ];
  assert.deepEqual(emulatorConfiguration(FILE, ADDRESS, [...others, own], WORKSPACE, "win32"),
                   { ...own, env: { SENSOR: "outdoor", NXWRIGHT_MCU: ADDRESS } });
});

test("the simulator's address replaces one the configuration gives", () => {
  const own = { type: "debugpy", request: "launch", name: "My emulator", program: FILE,
                env: { NXWRIGHT_MCU: "127.0.0.1:1" } };
  assert.deepEqual(emulatorConfiguration(FILE, ADDRESS, [own], WORKSPACE, "win32").env,
                   { NXWRIGHT_MCU: ADDRESS });
});

test("on Windows the program matches in either letter case and with either slash", () => {
  const own = { type: "debugpy", request: "launch", name: "My emulator",
                program: "c:/WORK/thermostat/mcu/Main.py" };
  assert.equal(emulatorConfiguration(FILE, ADDRESS, [own], WORKSPACE, "win32").name,
               "My emulator");
  assert.equal(emulatorConfiguration("/work/mcu/main.py", ADDRESS,
                                     [{ ...own, program: "/work/mcu/Main.py" }], "/work",
                                     "linux").name, "MCU emulator");
});

test("a configuration that does not launch a program with the Python debugger is not used", () => {
  for (const other of [
    { type: "debugpy", request: "attach", name: "Attach", program: FILE },
    { type: "node", request: "launch", name: "Node", program: FILE },
    { type: "debugpy", request: "launch", name: "A module", module: "emulator" },
    null, "main.py",
  ]) {
    assert.equal(emulatorConfiguration(FILE, ADDRESS, [other], WORKSPACE, "win32").name,
                 "MCU emulator");
  }
});

const listening = { kind: "emulator", name: ADDRESS, baud: null, connected: true,
                    attached: false };

test("the port listens for the emulator at its address while it is connected", () => {
  assert.equal(listeningAddress(listening), ADDRESS);
  assert.equal(listeningAddress({ ...listening, connected: false }), undefined);
  assert.equal(listeningAddress({ kind: "tcp", name: ADDRESS, baud: null, connected: true }),
               undefined);
  assert.equal(listeningAddress({ kind: "serial", name: "COM4", baud: 9600, connected: true }),
               undefined);
  assert.equal(listeningAddress(undefined), undefined);
});

test("the emulator starts once the port listens for it", () => {
  assert.equal(emulatorStep(listening, undefined), "start");
});

test("an emulator that connected or ended at the same address is not started again", () => {
  assert.equal(emulatorStep({ ...listening, attached: true }, ADDRESS), "keep");
  assert.equal(emulatorStep(listening, ADDRESS), "keep");
});

test("a port that listens at another address is a new port, and the emulator starts again", () => {
  assert.equal(emulatorStep({ ...listening, name: "127.0.0.1:50000" }, ADDRESS), "start");
});

test("the emulator stops once the port no longer listens for it", () => {
  assert.equal(emulatorStep({ ...listening, connected: false }, ADDRESS), "stop");
  assert.equal(emulatorStep({ kind: "serial", name: "COM4", baud: 9600, connected: true },
                            ADDRESS), "stop");
  assert.equal(emulatorStep(undefined, ADDRESS), "stop");
});

test("nothing happens while no emulator was started and the port does not listen for one", () => {
  assert.equal(emulatorStep({ kind: "serial", name: null, baud: 9600, connected: false },
                            undefined), "keep");
  assert.equal(emulatorStep(undefined, undefined), "keep");
});

test("a launch configuration gives the emulator's port in either form", () => {
  assert.equal(isEmulatorPort("emulator"), true);
  assert.equal(isEmulatorPort({ emulator: true }), true);
  for (const other of ["none", null, undefined, { name: "COM4", baud: 9600 },
                       { tcp: "127.0.0.1:7000" }, { emulator: false }]) {
    assert.equal(isEmulatorPort(other), false);
  }
});
