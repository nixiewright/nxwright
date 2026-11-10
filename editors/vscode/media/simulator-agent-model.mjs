// The Simulator section's line saying that an agent drives the simulation
// (simulator-controls.mjs), shown while the simulation running was started
// through the agent channel, or an agent has acted on it
// (src/agentChannelServer.ts). A simulation an agent starts has no MCU port.
// So while none is connected, a button connects the port that a simulation
// of the project would start with: the one last chosen for it in the
// section, or else the Simulator settings' port, or else the port of the
// project's MCU emulator. The line tells the user that an agent drives the
// simulation, so connecting the port from it counts as the user's permission
// for the agent to act with the port connected.

// Returns what the line shows, from what the extension sends:
//  - `driven`: whether an agent drives the simulation;
//  - `port`: the port the button connects, or null for none. Its `shown`
//    is the text that shows the port, such as "COM4" or "127.0.0.1:7000".
//    Its `connection` is what connects the port: { name, baud } for a
//    serial port, { tcp } for a program at an address, or { emulator: true }
//    for the port that listens for the project's MCU emulator;
//  - `connected`: whether a port is connected.
// In the result, `shown` is whether the line shows, and `note` is its
// text. `button`, when given, has the button's label and its connection.
export function agentLine({ driven, port, connected }) {
  if (!driven) {
    return { shown: false };
  }
  const note = "An agent drives this simulation through MCP.";
  if (connected) {
    return { shown: true, note, button: undefined };
  }
  if (!port) {
    return { shown: true, button: undefined,
             note: `${note} To connect an MCU port, choose one in the list below.` };
  }
  return { shown: true, note,
           button: { label: `Connect ${port.shown}`, connection: port.connection } };
}
