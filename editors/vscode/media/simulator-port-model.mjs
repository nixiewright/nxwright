// What the Simulator section (simulator-controls.mjs) lists and shows for a
// port: the MCU port, which the screen's serial line is connected to, and
// the screen port, which a real screen is on.
//
// The MCU port is one of several kinds. Its list has an entry for each: None,
// each serial port of the computer, and TCP, for a program that listens at
// an address. The screen port is always a serial port.
//
// An entry is the value of one of the list's options. A serial port's entry
// is "serial:" followed by the port's name, so that a port the system calls
// "tcp" or "none" is not taken for the TCP or None entry.

// The entry for no port, and the entry for a program over TCP.
export const NONE = "none";
export const TCP = "tcp";
const SERIAL = "serial:";

// Returns the entry of the serial port `name`.
export function serialEntry(name) {
  return SERIAL + name;
}

// Returns the name of the serial port that `entry` is for, or undefined when
// it is for another kind of port.
export function serialName(entry) {
  return typeof entry === "string" && entry.startsWith(SERIAL)
    ? entry.slice(SERIAL.length) : undefined;
}

// Returns the list's options, one for each of the computer's serial ports,
// `ports`. Each option has a `value`, which is its entry, and a `label`.
// For the MCU port, `kinds` is true, and the options also have None before
// the serial ports and TCP after them. `chosen`, the entry to select, is
// listed even when it is a serial port not among `ports`, such as one the
// launch configuration gives that is unplugged.
export function portOptions(ports, kinds, chosen) {
  const names = [...ports];
  const chosenName = serialName(chosen);
  if (chosenName && !names.includes(chosenName)) {
    names.push(chosenName);
  }
  const serial = names.map((name) => ({ value: serialEntry(name), label: name }));
  return kinds
    ? [{ value: NONE, label: "None" }, ...serial, { value: TCP, label: "TCP" }]
    : serial;
}

// Returns the entry of the port whose state is `state`, as the debug
// adapter sends it (nxwright/debug_adapter/serial_port.py), or undefined
// when no port was chosen yet.
export function entryOfState(state) {
  if (state.kind === TCP) {
    return TCP;
  }
  return state.name ? serialEntry(state.name) : undefined;
}

// Returns what shows beside the list while `entry` is selected: the list of
// rates for a serial port (`rateShown`), or the field for the address of a
// program over TCP (`addressShown`). None has neither.
export function besideList(entry) {
  return { rateShown: serialName(entry) !== undefined, addressShown: entry === TCP };
}

// Returns the port to connect for the entry selected, with the rate and the
// address beside it: { name, baud } for a serial port, or { tcp } for a
// program at an address. Returns undefined when there is nothing to connect:
// for None, and for TCP while the address is empty.
export function connectionOf(entry, baud, address) {
  const name = serialName(entry);
  if (name) {
    return { name, baud };
  }
  const trimmed = (address ?? "").trim();
  return entry === TCP && trimmed ? { tcp: trimmed } : undefined;
}

// Returns the line that says the port's state, and whether it reports a
// problem. A program over TCP has no rate.
export function stateLine(state) {
  if (state.connected) {
    const rate = state.baud ? ` at ${state.baud} bits per second` : "";
    return { text: `Connected to ${state.name}${rate}.`, problem: false };
  }
  if (state.problem) {
    return { text: `${state.name}: ${state.problem}`, problem: true };
  }
  return { text: "Not connected.", problem: false };
}
