// How the extension finds the command that runs nxwright when the setting
// nxwright.command is not set (src/nxwrightCommand.ts, compiled to out/
// before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { findNxwright, programOnPath, runsCleanly } from "../out/nxwrightCommand.js";

// Means of searching, as findNxwright takes them: `onPath` lists the
// programs on PATH, `withNxwright` the Pythons that run nxwright, and
// `chosen` is the Python chosen in VS Code. Each command run is noted in
// `ran`, and each time the chosen Python is asked for, in `asked`.
function searching({ onPath = [], withNxwright = [], chosen } = {}) {
  const ran = [];
  const asked = [];
  return {
    ran,
    asked,
    means: {
      programOnPath: async (name) => (onPath.includes(name) ? `/bin/${name}` : undefined),
      runsCleanly: async (command) => {
        ran.push(command);
        const python = command.slice(0, command.indexOf("-P")).join(" ");
        return withNxwright.includes(python) && command.join(" ").endsWith("-P -m nxwright --help");
      },
      chosenPython: async () => {
        asked.push(true);
        return chosen;
      },
    },
  };
}

test("the nxwright command on PATH is run as it is, nothing else asked", async () => {
  const { ran, asked, means } = searching({ onPath: ["nxwright"], chosen: "/venv/bin/python" });
  assert.deepEqual(await findNxwright("linux", means), { command: ["nxwright"], pythons: [] });
  assert.deepEqual(ran, []);
  assert.deepEqual(asked, []);
});

test("else the Python chosen in VS Code, when it has nxwright", async () => {
  // As with nxwright installed in a virtual environment VS Code was not started from.
  const { means } = searching({ chosen: "/venv/bin/python", withNxwright: ["/venv/bin/python", "python"] });
  assert.deepEqual(await findNxwright("linux", means),
                   { command: ["/venv/bin/python", "-P", "-m", "nxwright"], pythons: [["/venv/bin/python"]] });
});

test("else the first Python by its usual names that has nxwright", async () => {
  const { ran, means } = searching({ chosen: "/venv/bin/python", withNxwright: ["python"] });
  assert.deepEqual(await findNxwright("linux", means), {
    command: ["python", "-P", "-m", "nxwright"],
    pythons: [["/venv/bin/python"], ["python3"], ["python"]],
  });
  // Each Python runs nxwright as it would be run, its help answering.
  assert.deepEqual(ran.at(-1), ["python", "-P", "-m", "nxwright", "--help"]);
});

test("the Python launcher on Windows only", async () => {
  const { means } = searching({ withNxwright: ["py -3"] });
  assert.deepEqual(await findNxwright("win32", means), {
    command: ["py", "-3", "-P", "-m", "nxwright"],
    pythons: [["python3"], ["python"], ["py", "-3"]],
  });
  assert.deepEqual(await findNxwright("darwin", searching({ withNxwright: ["py -3"] }).means),
                   { command: undefined, pythons: [["python3"], ["python"]] });
});

test("none found: no command, and the Pythons tried", async () => {
  const { means } = searching({ onPath: ["python"] });
  assert.deepEqual(await findNxwright("linux", means),
                   { command: undefined, pythons: [["python3"], ["python"]] });
});

test("a program on PATH as a process started without a shell finds it", async () => {
  const files = new Set(["/usr/bin/python3", "/home/me/.local/bin/nxwright", "C:\\Tools\\nxwright.cmd",
                         "C:\\Py\\Scripts\\nxwright.exe", "C:\\Program Files\\Py\\nxwright.com"]);
  const isProgram = async (file) => files.has(file);
  assert.equal(await programOnPath("nxwright", "/usr/bin::/home/me/.local/bin", "linux", isProgram),
               "/home/me/.local/bin/nxwright");
  assert.equal(await programOnPath("nxwright", "/usr/bin", "linux", isProgram), undefined);
  // On Windows, a .cmd is not started without a shell: only .com and .exe.
  assert.equal(await programOnPath("nxwright", "C:\\Tools;C:\\Py\\Scripts", "win32", isProgram),
               "C:\\Py\\Scripts\\nxwright.exe");
  // A folder of PATH may be quoted.
  assert.equal(await programOnPath("nxwright", "\"C:\\Program Files\\Py\";C:\\Py\\Scripts", "win32",
                                   isProgram), "C:\\Program Files\\Py\\nxwright.com");
});

test("a command runs cleanly when it exits with 0", async () => {
  assert.equal(await runsCleanly([process.execPath, "-e", ""]), true);
  assert.equal(await runsCleanly([process.execPath, "-e", "process.exit(3)"]), false);
  assert.equal(await runsCleanly(["no-such-program-nxwright-test"]), false);
});
