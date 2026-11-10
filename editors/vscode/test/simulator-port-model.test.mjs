// What the Simulator section lists and shows for a port
// (media/simulator-port-model.mjs). Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { NONE, TCP, besideList, connectionOf, entryOfState, portOptions, serialEntry, serialName,
         stateLine } from "../media/simulator-port-model.mjs";

test("the MCU port's list has None, the serial ports, then TCP", () => {
  assert.deepEqual(portOptions(["COM3", "COM4"], true, undefined), [
    { value: NONE, label: "None" },
    { value: serialEntry("COM3"), label: "COM3" },
    { value: serialEntry("COM4"), label: "COM4" },
    { value: TCP, label: "TCP" },
  ]);
});

test("the screen port's list has the serial ports alone", () => {
  assert.deepEqual(portOptions(["COM3"], false, undefined),
                   [{ value: serialEntry("COM3"), label: "COM3" }]);
});

test("a chosen serial port that is unplugged stays in the list", () => {
  assert.deepEqual(portOptions(["COM3"], true, serialEntry("COM9")).map((option) => option.label),
                   ["None", "COM3", "COM9", "TCP"]);
  assert.deepEqual(portOptions(["COM3"], true, TCP).map((option) => option.label),
                   ["None", "COM3", "TCP"]);
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
  assert.equal(entryOfState({ kind: "serial", name: null, baud: 9600, connected: false }),
               undefined);
});

test("a serial port shows its rates, and TCP its address", () => {
  assert.deepEqual(besideList(serialEntry("COM4")), { rateShown: true, addressShown: false });
  assert.deepEqual(besideList(TCP), { rateShown: false, addressShown: true });
  assert.deepEqual(besideList(NONE), { rateShown: false, addressShown: false });
});

test("what each entry connects", () => {
  assert.deepEqual(connectionOf(serialEntry("COM4"), 115200, "127.0.0.1:7000"),
                   { name: "COM4", baud: 115200 });
  assert.deepEqual(connectionOf(TCP, 115200, " 127.0.0.1:7000 "), { tcp: "127.0.0.1:7000" });
  assert.equal(connectionOf(TCP, 115200, "  "), undefined);
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
