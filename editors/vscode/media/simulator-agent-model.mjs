// The Simulator section's line saying that an agent drives the simulation
// (simulator-controls.mjs), shown while the simulation running was started
// through the agent channel, or an agent has acted on it
// (src/agentChannelServer.ts). While no serial port is connected, a button
// connects the one the Simulator settings name. Connecting it, with the agent
// in view, allows the agent to act on the simulation with the port.

// Returns what the line shows, from what the extension sends: whether an
// agent drives the simulation (`driven`), the Simulator settings' port and
// rate (`port`, "" for none, and `baud`), and whether a port is connected.
// `shown` is whether the line shows; `note`, its words; `button`, when
// given, the button's label and the port it connects.
export function agentLine({ driven, port, baud, connected }) {
  if (!driven) {
    return { shown: false };
  }
  const note = "An agent drives this simulation through MCP.";
  if (connected) {
    return { shown: true, note, button: undefined };
  }
  if (!port) {
    return { shown: true, button: undefined,
             note: `${note} To connect a serial port, choose one in the list below.` };
  }
  return { shown: true, note, button: { label: `Connect ${port}`, name: port, baud } };
}
