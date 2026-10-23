// Runs the tests inside VS Code (test/host/*.host.cjs): `npm run test:host`.
//
// The VS Code it runs them in is one installed apart from the user's own,
// which the environment variable NXWRIGHT_TEST_VSCODE names: its program,
// such as Code.exe. It is never downloaded. It gets its own user data and
// extensions folders, in this checkout's .vscode-test/, which git ignores,
// so that two checkouts' runs keep apart and the installed VS Code is only
// read, portable or not (below).
//
// Its user settings are written there before it starts. nxwright.command
// runs this checkout's nxwright, with the Python that NXWRIGHT_TEST_PYTHON
// names, or `python`, so that the extension finds it at once. Nothing
// saves files, so that the tests' edits stay unsaved.
//
// It opens tests/fixtures/files/app where it lies, and writes nothing
// there. The language server's picture cache is off (NXWRIGHT_CACHE).
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { runTests } from "@vscode/test-electron";

const here = path.dirname(fileURLToPath(import.meta.url));
const extension = path.resolve(here, "..", "..");
const nxwright = path.resolve(extension, "..", "..");
const testFolder = path.join(extension, ".vscode-test");
const userData = path.join(testFolder, "user-data");
const extensions = path.join(testFolder, "extensions");
const sourceFolder = path.join(nxwright, "tests", "fixtures", "files", "app");

const executable = process.env.NXWRIGHT_TEST_VSCODE;
if (!executable || !existsSync(executable)) {
  console.error("The tests inside VS Code need a VS Code installed apart from your own, such as "
                + "its zip unpacked in a folder of its own, and NXWRIGHT_TEST_VSCODE naming its "
                + "program (Code.exe on Windows)." + (executable ? ` ${executable} is not there.` : ""));
  process.exit(1);
}

mkdirSync(path.join(userData, "User"), { recursive: true });
mkdirSync(extensions, { recursive: true });
writeFileSync(path.join(userData, "User", "settings.json"), JSON.stringify({
  "nxwright.command": [process.env.NXWRIGHT_TEST_PYTHON || "python",
                       path.join(nxwright, "run.py")],
  "files.autoSave": "off",
  "git.enabled": false,
  "telemetry.telemetryLevel": "off",
  "update.mode": "none",
  "workbench.startupEditor": "none",
}, null, 2) + "\n");

// Run from a terminal inside VS Code, the environment holds
// ELECTRON_RUN_AS_NODE, which VS Code's own processes run with: passed on,
// it would start the test's VS Code as plain Node.
delete process.env.ELECTRON_RUN_AS_NODE;

try {
  await runTests({
    vscodeExecutablePath: executable,
    extensionDevelopmentPath: extension,
    extensionTestsPath: path.join(here, "runner.cjs"),
    launchArgs: [sourceFolder, `--user-data-dir=${userData}`, `--extensions-dir=${extensions}`,
                 "--disable-extensions"],
    // A portable VS Code, unpacked from its zip with a `data` folder beside
    // its program, keeps its user data and extensions in that folder,
    // whatever the two arguments above say. VSCODE_PORTABLE moves that
    // folder to this checkout's, whose user-data and extensions folders are
    // the same as theirs. The arguments serve a VS Code that is not
    // portable, which ignores the variable.
    extensionTestsEnv: { NXWRIGHT_CACHE: "off", VSCODE_PORTABLE: testFolder },
  });
} catch (error) {
  console.error(`The tests inside VS Code failed: ${error.message}`);
  process.exit(1);
}
