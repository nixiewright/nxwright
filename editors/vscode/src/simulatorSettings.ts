// The simulator's settings, nxwright.simulator.*, as defaults for a
// simulation: each fills in what the simulation's launch configuration leaves
// out, and the configuration's own values win. Kept apart from VS Code's API,
// so that Node's test runner can check it (test/simulator-settings.test.mjs).

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

// Returns a simulation's launch configuration, `config`, with the settings
// filling in what it leaves out. Any other configuration, such as a test's,
// which names no source folder, is returned as it is.
export function withSimulatorSettings(config: Record<string, unknown>,
                                      settings: SimulatorSettings): Record<string, unknown> {
  if (!config.sourceFolder) {
    return config;
  }
  const filled = { ...config };
  if (filled.serialPort === undefined && settings.serialPort) {
    filled.serialPort = { name: settings.serialPort, baud: settings.serialBaud };
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
