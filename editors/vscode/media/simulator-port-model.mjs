// What the Simulator section (simulator-controls.mjs) lists and shows for a
// port: the MCU port, which the screen's serial line is connected to, and
// the screen port, which a real screen is on.
//
// The MCU port is one of several kinds. Its list has an entry for each:
//  - None;
//  - Emulator, if the project has an MCU emulator;
//  - each serial port of the computer;
//  - TCP, for a program that listens at an address.
// The screen port is always a serial port.
//
// An entry is the value of one of the list's options. A serial port's entry
// is "serial:" followed by the port's name, so that a port the system calls
// "tcp" or "none" is not taken for the TCP or None entry.

// The entry for no port, the entry for a program over TCP, and the entry for
// the port that listens for the project's MCU emulator.
export const NONE = "none";
export const TCP = "tcp";
export const EMULATOR = "emulator";
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
// the serial ports and TCP after them. If `emulator` is true too, because
// the project has an MCU emulator, Emulator follows None. `chosen` is the
// entry to select. It is listed even when it is not offered. That can be a
// serial port not among `ports`, such as an unplugged one that the launch
// configuration gives, or Emulator when the project has no MCU emulator.
export function portOptions(ports, { kinds = false, emulator = false, chosen } = {}) {
  const names = [...ports];
  const chosenName = serialName(chosen);
  if (chosenName && !names.includes(chosenName)) {
    names.push(chosenName);
  }
  const serial = names.map((name) => ({ value: serialEntry(name), label: name }));
  if (!kinds) {
    return serial;
  }
  return [{ value: NONE, label: "None" },
          ...(emulator || chosen === EMULATOR ? [{ value: EMULATOR, label: "Emulator" }] : []),
          ...serial, { value: TCP, label: "TCP" }];
}

// Returns the entry of the port whose state is `state`, as the debug
// adapter sends it (nxwright/debug_adapter/serial_port.py), or undefined
// when no port was chosen yet.
export function entryOfState(state) {
  if (state.kind === TCP || state.kind === EMULATOR) {
    return state.kind;
  }
  return state.name ? serialEntry(state.name) : undefined;
}

// Returns what shows beside the list while `entry` is selected: the list of
// rates for a serial port (`rateShown`), or the field for the address of a
// program over TCP (`addressShown`). None and Emulator have neither.
export function besideList(entry) {
  return { rateShown: serialName(entry) !== undefined, addressShown: entry === TCP };
}

// Returns the port to connect for the entry selected, with the rate and the
// address beside it: { name, baud } for a serial port, { tcp } for a program
// at an address, or { emulator: true } for the port that listens for the MCU
// emulator. Returns undefined when there is nothing to connect: for None,
// and for TCP while the address is empty.
export function connectionOf(entry, baud, address) {
  const name = serialName(entry);
  if (name) {
    return { name, baud };
  }
  if (entry === EMULATOR) {
    return { emulator: true };
  }
  const trimmed = (address ?? "").trim();
  return entry === TCP && trimmed ? { tcp: trimmed } : undefined;
}

// Returns whether the button that starts the MCU emulator again shows. It
// shows while the port listens for the emulator, if the extension can start
// the emulator (`canStart`).
export function startEmulatorShown(state, canStart) {
  return canStart === true && state.kind === EMULATOR && state.connected === true;
}

// Returns the line that shows the port's state, and whether the line reports
// a problem. A connected port's line gives its rate, unless the port has
// none, such as a program over TCP. The emulator's port is connected from
// the moment it listens, so its line shows whether an emulator is connected
// to it, and where it listens.
export function stateLine(state) {
  if (state.connected && state.kind === EMULATOR) {
    return { text: state.attached ? `The MCU emulator is connected at ${state.name}.`
      : `Waiting for the MCU emulator at ${state.name}.`, problem: false };
  }
  if (state.connected) {
    const rate = state.baud ? ` at ${state.baud} bits per second` : "";
    return { text: `Connected to ${state.name}${rate}.`, problem: false };
  }
  if (state.problem) {
    return { text: `${state.name}: ${state.problem}`, problem: true };
  }
  return { text: "Not connected.", problem: false };
}
