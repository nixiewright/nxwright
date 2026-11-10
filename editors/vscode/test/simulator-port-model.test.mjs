// What the Simulator section lists and shows for a port
// (media/simulator-port-model.mjs). Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { EMULATOR, NONE, TCP, besideList, connectionOf, entryOfState, portOptions, serialEntry,
         serialName, startEmulatorShown, stateLine } from "../media/simulator-port-model.mjs";

test("the MCU port's list has None, the serial ports, then TCP", () => {
  assert.deepEqual(portOptions(["COM3", "COM4"], { kinds: true }), [
    { value: NONE, label: "None" },
    { value: serialEntry("COM3"), label: "COM3" },
    { value: serialEntry("COM4"), label: "COM4" },
    { value: TCP, label: "TCP" },
  ]);
});

test("the screen port's list has the serial ports alone", () => {
  assert.deepEqual(portOptions(["COM3"]), [{ value: serialEntry("COM3"), label: "COM3" }]);
});

test("a project that has an MCU emulator gets Emulator after None", () => {
  const labels = (options) => options.map((option) => option.label);
  assert.deepEqual(labels(portOptions(["COM3"], { kinds: true, emulator: true })),
                   ["None", "Emulator", "COM3", "TCP"]);
  // Emulator is also listed when it is chosen, for example by a launch
  // configuration, for a project that has no MCU emulator.
  assert.deepEqual(labels(portOptions(["COM3"], { kinds: true, chosen: EMULATOR })),
                   ["None", "Emulator", "COM3", "TCP"]);
});

test("a chosen serial port that is unplugged stays in the list", () => {
  assert.deepEqual(portOptions(["COM3"], { kinds: true, chosen: serialEntry("COM9") })
    .map((option) => option.label), ["None", "COM3", "COM9", "TCP"]);
  assert.deepEqual(portOptions(["COM3"], { kinds: true, chosen: TCP })
    .map((option) => option.label), ["None", "COM3", "TCP"]);
});

test("a serial port named like another kind keeps its own entry", () => {
  assert.notEqual(serialEntry("tcp"), TCP);
  assert.equal(serialName(serialEntry("tcp")), "tcp");
  assert.equal(serialName(TCP), undefined);
  assert.equal(serialName(NONE), undefined);
});

test("a state selects the entry of its port", () => {
  assert.equal(entryOfState({ kind: "serial", name: "COM4", baud: 9600, connected: true }),
               serialEntry("COM4"));
  assert.equal(entryOfState({ kind: "tcp", name: "127.0.0.1:7000", baud: null, connected: true }),
               TCP);
  assert.equal(entryOfState({ kind: "emulator", name: "127.0.0.1:53124", baud: null,
                              connected: true, attached: false }), EMULATOR);
  assert.equal(entryOfState({ kind: "serial", name: null, baud: 9600, connected: false }),
               undefined);
});

test("a serial port shows its rates, and TCP its address", () => {
  assert.deepEqual(besideList(serialEntry("COM4")), { rateShown: true, addressShown: false });
  assert.deepEqual(besideList(TCP), { rateShown: false, addressShown: true });
  assert.deepEqual(besideList(NONE), { rateShown: false, addressShown: false });
  assert.deepEqual(besideList(EMULATOR), { rateShown: false, addressShown: false });
});

test("what each entry connects", () => {
  assert.deepEqual(connectionOf(serialEntry("COM4"), 115200, "127.0.0.1:7000"),
                   { name: "COM4", baud: 115200 });
  assert.deepEqual(connectionOf(TCP, 115200, " 127.0.0.1:7000 "), { tcp: "127.0.0.1:7000" });
  assert.equal(connectionOf(TCP, 115200, "  "), undefined);
  assert.deepEqual(connectionOf(EMULATOR, 115200, ""), { emulator: true });
  assert.equal(connectionOf(NONE, 115200, "127.0.0.1:7000"), undefined);
  assert.equal(connectionOf("", 115200, ""), undefined);
});

test("the state's line leaves the rate out for a program over TCP", () => {
  assert.deepEqual(stateLine({ kind: "serial", name: "COM4", baud: 9600, connected: true }),
                   { text: "Connected to COM4 at 9600 bits per second.", problem: false });
  assert.deepEqual(stateLine({ kind: "tcp", name: "127.0.0.1:7000", baud: null,
                               connected: true }),
                   { text: "Connected to 127.0.0.1:7000.", problem: false });
  assert.deepEqual(stateLine({ kind: "tcp", name: "127.0.0.1:7000", baud: null,
                               connected: false, problem: "Connection refused" }),
                   { text: "127.0.0.1:7000: Connection refused", problem: true });
  assert.deepEqual(stateLine({ kind: "serial", name: null, baud: 9600, connected: false,
                               problem: null }),
                   { text: "Not connected.", problem: false });
});

test("the emulator's port says whether an emulator is connected, and where it listens", () => {
  const listening = { kind: "emulator", name: "127.0.0.1:53124", baud: null, connected: true };
  assert.deepEqual(stateLine({ ...listening, attached: false }),
                   { text: "Waiting for the MCU emulator at 127.0.0.1:53124.", problem: false });
  assert.deepEqual(stateLine({ ...listening, attached: true }),
                   { text: "The MCU emulator is connected at 127.0.0.1:53124.",
                     problem: false });
  assert.deepEqual(stateLine({ ...listening, connected: false, attached: false }),
                   { text: "Not connected.", problem: false });
});

test("the emulator can be started again while the port listens for it", () => {
  const listening = { kind: "emulator", name: "127.0.0.1:49480", baud: null, connected: true,
                      attached: true };
  assert.equal(startEmulatorShown(listening, true), true);
  assert.equal(startEmulatorShown({ ...listening, attached: false }, true), true);
  // The button is hidden when the extension cannot start the emulator, when
  // the port is not connected, or when it is another kind of port.
  assert.equal(startEmulatorShown(listening, false), false);
  assert.equal(startEmulatorShown({ ...listening, connected: false }, true), false);
  assert.equal(startEmulatorShown({ kind: "tcp", name: "127.0.0.1:7000", baud: null,
                                    connected: true }, true), false);
});
