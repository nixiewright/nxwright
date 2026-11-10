// The simulator's settings, nxwright.simulator.*, as defaults for a
// simulation: each fills in what the simulation's launch configuration leaves
// out, and the configuration's own values win. The MCU port, which the
// screen's serial line is connected to, has one more default: the port the
// user last chose in the Simulator section for the project comes before the
// settings' port. Kept apart from VS Code's API, so that Node's test runner
// can check it (test/simulator-settings.test.mjs).
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
// none, a serial port at a rate, or a program that listens at an address,
// over TCP.
export type PortChoice =
  | { kind: "none" }
  | { kind: "serial"; name: string; baud: number }
  | { kind: "tcp"; address: string };

// The MCU port of a simulation whose launch configuration gives none:
//  - `serialPort` is the value to use as the configuration's `serialPort`,
//    or undefined when the user has made no choice and the settings have
//    no port;
//  - `shown` is the port's name or address to show the user, such as
//    "COM4", or "" when the simulation has no port;
//  - `chosen` is true when the port, or None, is the user's choice in the
//    Simulator section, and false when the port comes from the settings.
export interface DefaultPort {
  serialPort: unknown;
  shown: string;
  chosen: boolean;
}

// Returns the MCU port of a simulation whose launch configuration gives
// none: the port the user last chose for the project, `remembered`, or else
// the settings' port.
export function defaultPort(settings: SimulatorSettings, remembered?: PortChoice): DefaultPort {
  switch (remembered?.kind) {
    case "none":
      return { serialPort: "none", shown: "", chosen: true };
    case "serial":
      return { serialPort: { name: remembered.name, baud: remembered.baud },
               shown: remembered.name, chosen: true };
    case "tcp":
      return { serialPort: { tcp: remembered.address }, shown: remembered.address,
               chosen: true };
    default:
      return settings.serialPort
        ? { serialPort: { name: settings.serialPort, baud: settings.serialBaud },
            shown: settings.serialPort, chosen: false }
        : { serialPort: undefined, shown: "", chosen: false };
  }
}

// Returns the key under which the workspace's state keeps the MCU port
// chosen for the source folder `sourceFolder` (PortChoice). The key is the
// same however the folder is written: with either slash, and on Windows in
// either letter case. A launch configuration may write the folder with
// ${workspaceFolder}, which stands for `workspaceFolder`.
export function portChoiceKey(sourceFolder: string, platform: NodeJS.Platform,
                              workspaceFolder = ""): string {
  const folder = sourceFolder.split("${workspaceFolder}").join(workspaceFolder);
  const resolved = platform === "win32"
    ? path.win32.resolve(folder).toLowerCase() : path.posix.resolve(folder);
  return `nxwright.mcuPort:${resolved}`;
}

// Returns a simulation's launch configuration, `config`, with the settings
// filling in what it leaves out. If `config` gives no MCU port, the port is
// the one `remembered` gives, or else the settings' port (defaultPort). Any
// other configuration, such as a test's, which names no source folder, is
// returned as it is.
export function withSimulatorSettings(config: Record<string, unknown>,
                                      settings: SimulatorSettings,
                                      remembered?: PortChoice): Record<string, unknown> {
  if (!config.sourceFolder) {
    return config;
  }
  const filled = { ...config };
  if (filled.serialPort === undefined) {
    const port = defaultPort(settings, remembered).serialPort;
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
