// How the extension finds the command that runs nxwright when the setting
// nxwright.command is not set. The `nxwright` program that `pip install`
// gives may not be on the PATH VS Code sees. On Windows, `pip install --user`
// and the Microsoft Store's Python put it in a folder often missing from
// PATH. nxwright may also be installed in a virtual environment VS Code was
// not started from. A Python that has nxwright runs it as `python -m nxwright`.
//
// That command takes -P, which keeps the current folder out of the module
// search path. Otherwise a folder named nxwright where the command runs,
// such as a copy of nxwright's repository, would hide the nxwright
// installed. Pythons older than 3.11, which nxwright does not run on, refuse
// -P, so they are not chosen.

import { execFile } from "child_process";
import * as fs from "fs";
import * as path from "path";

// How long a Python may take to show nxwright's help, in milliseconds.
const PROBE_TIMEOUT = 10000;

// What a search found: the command that runs nxwright, or undefined for
// none, and the Pythons tried, in order, each as the command that starts it.
export interface NxwrightSearch {
  command: string[] | undefined;
  pythons: string[][];
}

// What a search uses: the program `name` on PATH (programOnPath), whether a
// command runs cleanly (runsCleanly), and the path of the Python chosen in
// VS Code, if any.
export interface SearchMeans {
  programOnPath: (name: string) => Promise<string | undefined>;
  runsCleanly: (command: string[]) => Promise<boolean>;
  chosenPython: () => Promise<string | undefined>;
}

// Returns the command that runs nxwright on `platform`: the nxwright program
// on PATH, as the setting's default names it; else `-P -m nxwright` with the
// first Python that runs it, as running its --help shows. The Python chosen
// in VS Code comes first, asked for only then, then the usual names, and on
// Windows the Python launcher.
export async function findNxwright(platform: NodeJS.Platform,
                                   means: SearchMeans): Promise<NxwrightSearch> {
  if ((await means.programOnPath("nxwright")) !== undefined) {
    return { command: ["nxwright"], pythons: [] };
  }
  const chosen = await means.chosenPython();
  const usual = platform === "win32" ? [["python3"], ["python"], ["py", "-3"]]
    : [["python3"], ["python"]];
  const pythons = chosen === undefined ? usual : [[chosen], ...usual];
  for (const [index, python] of pythons.entries()) {
    const command = [...python, "-P", "-m", "nxwright"];
    if (await means.runsCleanly([...command, "--help"])) {
      return { command, pythons: pythons.slice(0, index + 1) };
    }
  }
  return { command: undefined, pythons };
}

// Returns the program `name` as a process started without a shell finds it
// on the PATH `searched`, or undefined. On Windows, that is name.com or
// name.exe, as Node's child processes look for no other. Elsewhere, it is an
// executable file named `name`. `isProgram` says whether a file is one.
export async function programOnPath(name: string, searched: string, platform: NodeJS.Platform,
                                    isProgram = isExecutableFile): Promise<string | undefined> {
  const windows = platform === "win32";
  const paths = windows ? path.win32 : path.posix;
  const folders = searched.split(windows ? ";" : ":")
    .map((folder) => folder.replace(/^"(.*)"$/, "$1"))
    .filter((folder) => folder !== "");
  for (const folder of folders) {
    for (const file of windows ? [`${name}.com`, `${name}.exe`] : [name]) {
      const found = paths.join(folder, file);
      if (await isProgram(found)) {
        return found;
      }
    }
  }
  return undefined;
}

// Whether `file` is a file this process may run.
async function isExecutableFile(file: string): Promise<boolean> {
  try {
    // On Windows, X_OK checks only that the file exists.
    await fs.promises.access(file, fs.constants.X_OK);
  } catch {
    return false;
  }
  // X_OK allows a folder too. An app execution alias, as Windows keeps in
  // WindowsApps for Pythons it installs, runs, though stat cannot read it.
  const stats = await fs.promises.stat(file).catch(() => undefined);
  return stats === undefined || !stats.isDirectory();
}

// Whether `command` runs, and exits with 0 within PROBE_TIMEOUT.
export function runsCleanly(command: string[]): Promise<boolean> {
  return new Promise((resolve) => {
    execFile(command[0], command.slice(1), { timeout: PROBE_TIMEOUT, windowsHide: true },
             (error) => resolve(error === null));
  });
}
