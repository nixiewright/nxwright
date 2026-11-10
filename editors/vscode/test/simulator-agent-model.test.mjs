// The Simulator section's line saying an agent drives the simulation
// (media/simulator-agent-model.mjs). Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { agentLine } from "../media/simulator-agent-model.mjs";

const SAYS = "An agent drives this simulation through MCP.";
const SERIAL = { shown: "COM4", connection: { name: "COM4", baud: 115200 } };
const PROGRAM = { shown: "127.0.0.1:7000", connection: { tcp: "127.0.0.1:7000" } };

test("no line while no agent drives the simulation", () => {
  assert.equal(agentLine({ driven: false, port: SERIAL, connected: false }).shown, false);
});

test("a button connects the port a simulation of the project starts with, while none is", () => {
  assert.deepEqual(agentLine({ driven: true, port: SERIAL, connected: false }),
                   { shown: true, note: SAYS,
                     button: { label: "Connect COM4",
                               connection: { name: "COM4", baud: 115200 } } });
  assert.deepEqual(agentLine({ driven: true, port: PROGRAM, connected: false }),
                   { shown: true, note: SAYS,
                     button: { label: "Connect 127.0.0.1:7000",
                               connection: { tcp: "127.0.0.1:7000" } } });
});

test("with no port to connect, the line says where to choose one", () => {
  assert.deepEqual(agentLine({ driven: true, port: null, connected: false }),
                   { shown: true, button: undefined,
                     note: `${SAYS} To connect an MCU port, choose one in the list below.` });
});

test("with a port connected, no button", () => {
  assert.deepEqual(agentLine({ driven: true, port: SERIAL, connected: true }),
                   { shown: true, note: SAYS, button: undefined });
});
