// The Simulator section's line saying an agent drives the simulation
// (media/simulator-agent-model.mjs). Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { agentLine } from "../media/simulator-agent-model.mjs";

const SAYS = "An agent drives this simulation through MCP.";

test("no line while no agent drives the simulation", () => {
  assert.equal(agentLine({ driven: false, port: "COM4", baud: 9600, connected: false }).shown,
               false);
});

test("a button connects the port the Simulator settings name, while none is", () => {
  assert.deepEqual(agentLine({ driven: true, port: "COM4", baud: 115200, connected: false }),
                   { shown: true, note: SAYS,
                     button: { label: "Connect COM4", name: "COM4", baud: 115200 } });
});

test("with no port named, the line says where to choose one", () => {
  assert.deepEqual(agentLine({ driven: true, port: "", baud: 9600, connected: false }),
                   { shown: true, button: undefined,
                     note: `${SAYS} To connect a serial port, choose one in the list below.` });
});

test("with a port connected, no button", () => {
  assert.deepEqual(agentLine({ driven: true, port: "COM4", baud: 9600, connected: true }),
                   { shown: true, note: SAYS, button: undefined });
});
