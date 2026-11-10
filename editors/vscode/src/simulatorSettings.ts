// The simulator's settings, nxwright.simulator.*, as defaults for a
// simulation: each fills in what the simulation's launch configuration leaves
// out, and the configuration's own values win. The MCU port, which the
// screen's serial line is connected to, has two more defaults. The port the
// user last chose for the project in the Simulator section comes before the
// settings' port, and the MCU emulator of a project that has one comes after
// that port. Kept apart from VS Code's API, so that Node's test runner can
// check it (test/simulator-settings.test.mjs).
import * as path from "path";

// The settings, as read from VS Code's configuration.
export interface SimulatorSettings {
  serialPort: string;
  serialBaud: number;
  sdCard0: string;
  sdCard1: string;
  logReceived: string;
  logSent: string;
  pinyinTable: string;
}

// The MCU port the user last chose in the Simulator section for a project:
// none, a serial port at a rate, a program that listens at a TCP address, or
// the port that listens for the project's MCU emulator.
export type PortChoice =
  | { kind: "none" }
  | { kind: "serial"; name: string; baud: number }
  | { kind: "tcp"; address: string }
  | { kind: "emulator" };

// What a simulation's MCU port depends on in its project: the port the user
// last chose for the project, if any, and whether the project has an MCU
// emulator.
export interface ProjectPorts {
  remembered?: PortChoice;
  hasEmulator: boolean;
}

// What the user reads in place of a name for the emulator's port, as in
// "Connect the MCU emulator".
const EMULATOR_SHOWN = "the MCU emulator";

// The MCU port of a simulation whose launch configuration gives none:
//  - `serialPort` is the value to use as the configuration's `serialPort`,
//    or undefined when the user has made no choice and the settings have
//    no port;
//  - `shown` is the port's name or address to show the user, such as
//    "COM4", or "" when the simulation has no port;
//  - `from` is where the port comes from: "choice" when the port, or None,
//    is the user's choice in the Simulator section, "settings" when it is
//    the settings' port, and "project" when it is the project's MCU
//    emulator. It is undefined when nothing gives a port.
export interface DefaultPort {
  serialPort: unknown;
  shown: string;
  from: "choice" | "settings" | "project" | undefined;
}

// Returns the MCU port of a simulation whose launch configuration gives
// none. It is the port the user last chose for the project, or else the
// settings' port, or else the project's MCU emulator, if it has one. If the
// user chose the emulator and the project no longer has one, that choice is
// skipped.
export function defaultPort(settings: SimulatorSettings, project: ProjectPorts): DefaultPort {
  const remembered = project.remembered;
  switch (remembered?.kind) {
    case "none":
      return { serialPort: "none", shown: "", from: "choice" };
    case "serial":
      return { serialPort: { name: remembered.name, baud: remembered.baud },
               shown: remembered.name, from: "choice" };
    case "tcp":
      return { serialPort: { tcp: remembered.address }, shown: remembered.address,
               from: "choice" };
    case "emulator":
      if (project.hasEmulator) {
        return { serialPort: "emulator", shown: EMULATOR_SHOWN, from: "choice" };
      }
  }
  if (settings.serialPort) {
    return { serialPort: { name: settings.serialPort, baud: settings.serialBaud },
             shown: settings.serialPort, from: "settings" };
  }
  return project.hasEmulator
    ? { serialPort: "emulator", shown: EMULATOR_SHOWN, from: "project" }
    : { serialPort: undefined, shown: "", from: undefined };
}

// Returns a source folder as a launch configuration gives it, with
// ${workspaceFolder} replaced by `workspaceFolder`.
export function sourceFolderPath(sourceFolder: string, workspaceFolder = ""): string {
  return sourceFolder.split("${workspaceFolder}").join(workspaceFolder);
}

// Returns the key under which the workspace's state keeps the MCU port
// chosen for the source folder `sourceFolder` (PortChoice). The key is the
// same however the folder is written: with either slash, and on Windows in
// either letter case. A launch configuration may write the folder with
// ${workspaceFolder}, which stands for `workspaceFolder`.
export function portChoiceKey(sourceFolder: string, platform: NodeJS.Platform,
                              workspaceFolder = ""): string {
  const folder = sourceFolderPath(sourceFolder, workspaceFolder);
  const resolved = platform === "win32"
    ? path.win32.resolve(folder).toLowerCase() : path.posix.resolve(folder);
  return `nxwright.mcuPort:${resolved}`;
}

// Returns a simulation's launch configuration, `config`, with the settings
// filling in what it leaves out. If `config` gives no MCU port, the port is
// the one that `project` and the settings give (defaultPort). Any other
// configuration, such as a test's, which names no source folder, is
// returned as it is.
export function withSimulatorSettings(
    config: Record<string, unknown>, settings: SimulatorSettings,
    project: ProjectPorts = { hasEmulator: false }): Record<string, unknown> {
  if (!config.sourceFolder) {
    return config;
  }
  const filled = { ...config };
  if (filled.serialPort === undefined) {
    const port = defaultPort(settings, project).serialPort;
    if (port !== undefined) {
      filled.serialPort = port;
    }
  }
  for (const file of ["sdCard0", "sdCard1", "pinyinTable"] as const) {
    if (filled[file] === undefined && settings[file]) {
      filled[file] = settings[file];
    }
  }
  for (const log of ["logReceived", "logSent"] as const) {
    if (filled[log] === undefined) {
      filled[log] = settings[log];
    }
  }
  return filled;
}
