// The debugging session that runs a project's MCU emulator beside its
// simulation (simulator.ts). The emulator is a Python program, so it runs
// through the Python debugger, as a child of the simulation's session. This
// file has the session's launch configuration, and the rule for when the
// session starts and stops. It is kept apart from VS Code's API, so that
// Node's test runner can check it (test/emulator-session.test.mjs).
import * as path from "path";

// The extension that has the Python debugger, and the type of its launch
// configurations.
export const PYTHON_DEBUGGER_EXTENSION = "ms-python.debugpy";
const PYTHON_DEBUGGER_TYPE = "debugpy";
// The environment variable that gives an emulator the address to connect to
// (nxwright/mcu.py).
export const ADDRESS_VARIABLE = "NXWRIGHT_MCU";

// A launch configuration of the Python debugger that runs an emulator.
export interface EmulatorConfiguration {
  type: string;
  request: string;
  name: string;
  program: string;
  env: Record<string, unknown>;
  [key: string]: unknown;
}

// Returns the launch configuration that runs the emulator whose file is
// `file`. `address` is where the simulator listens for the emulator, and
// goes into the configuration's environment.
//
// `existing` lists the launch configurations of the workspace folder
// `workspaceFolder`. If one of them launches the Python debugger with the
// emulator's file as its `program`, the emulator runs with that
// configuration, so that the user can give the emulator an interpreter,
// arguments, or environment of their own. The `program` may contain
// ${workspaceFolder}. Without a configuration of the user's, the emulator
// runs in a terminal, from its own folder, with the interpreter the Python
// debugger picks.
export function emulatorConfiguration(
    file: string, address: string, existing: unknown[], workspaceFolder: string | undefined,
    platform: NodeJS.Platform): EmulatorConfiguration {
  const paths = platform === "win32" ? path.win32 : path.posix;
  // On Windows, paths that differ only in letter case are one file.
  const key = (name: string) => {
    const resolved = paths.resolve(workspaceFolder ?? "", name);
    return platform === "win32" ? resolved.toLowerCase() : resolved;
  };
  const own = existing.find((entry): entry is EmulatorConfiguration => {
    if (typeof entry !== "object" || entry === null) {
      return false;
    }
    const { type, request, program } = entry as Record<string, unknown>;
    return type === PYTHON_DEBUGGER_TYPE && request === "launch" && typeof program === "string"
      && key(program.split("${workspaceFolder}").join(workspaceFolder ?? "")) === key(file);
  });
  if (own) {
    const env = typeof own.env === "object" && own.env !== null ? own.env : {};
    return { ...own, env: { ...env, [ADDRESS_VARIABLE]: address } };
  }
  return {
    type: PYTHON_DEBUGGER_TYPE,
    request: "launch",
    name: "MCU emulator",
    program: file,
    cwd: paths.dirname(file),
    console: "integratedTerminal",
    env: { [ADDRESS_VARIABLE]: address },
  };
}

// The part of the MCU port's state that decides what happens to the
// emulator's session (PortState in simulator.ts).
interface EmulatorPortState {
  kind: string;
  name: string | null;
  connected: boolean;
}

// Returns the address at which the port whose state is `state` listens for
// the emulator, or undefined when it does not listen for one.
export function listeningAddress(state: EmulatorPortState | undefined): string | undefined {
  return state?.kind === "emulator" && state.connected && state.name ? state.name : undefined;
}

// Returns what to do with the emulator's session now that the MCU port's
// state is `state`. `startedFor` is the address the emulator was last
// started for, or undefined if it was not started, or was stopped since.
//  - "start": the port listens at an address the emulator was not started
//    for. Any session left from another address ends, and a new one starts.
//  - "stop": the port no longer listens for the emulator, so its session
//    ends.
//  - "keep": nothing changes. An emulator that ended at the same address is
//    not started again, so the user can end it and leave the port waiting.
export function emulatorStep(state: EmulatorPortState | undefined,
                             startedFor: string | undefined): "start" | "stop" | "keep" {
  const address = listeningAddress(state);
  if (address === undefined) {
    return startedFor === undefined ? "keep" : "stop";
  }
  return address === startedFor ? "keep" : "start";
}

// Whether `serialPort`, as a launch configuration gives it, is the port that
// listens for the project's MCU emulator.
export function isEmulatorPort(serialPort: unknown): boolean {
  return serialPort === "emulator"
    || (typeof serialPort === "object" && serialPort !== null
        && (serialPort as { emulator?: unknown }).emulator === true);
}
