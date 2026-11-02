// Extract inside VS Code, of a project file that contains a block nxwright
// does not handle (write_unknown_project.py). The command is given its
// source folder, project file, and answer as arguments, so that it asks
// nothing; the questions themselves are tested apart (unknown-content.test.mjs).
// The source folder is a new one in the temporary folder, not the fixture.
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vscode = require("vscode");
const { test } = require("./runner.cjs");

// The project file, written once for both tests.
let project;

function unknownProject() {
  if (project === undefined) {
    const work = fs.mkdtempSync(path.join(os.tmpdir(), "nxwright-extract-"));
    project = path.join(work, "unknown.HMI");
    const [python] = vscode.workspace.getConfiguration("nxwright").get("command");
    const nxwright = path.resolve(__dirname, "..", "..", "..", "..");
    execFileSync(python, [path.join(__dirname, "write_unknown_project.py"), project],
                 { env: { ...process.env, PYTHONPATH: nxwright } });
  }
  return project;
}

test("extract does not go on past content the next build may lose, unless told to", async () => {
  const folder = path.join(path.dirname(unknownProject()), "stopped");
  const code = await vscode.commands.executeCommand(
    "nxwright.extract", { folder, project: unknownProject(), goOnPastUnknown: false });
  assert.equal(code, undefined);
  assert.equal(fs.existsSync(folder), false);
});

test("extract goes on past content the next build may lose, when told to", async () => {
  const folder = path.join(path.dirname(unknownProject()), "extracted");
  const code = await vscode.commands.executeCommand(
    "nxwright.extract", { folder, project: unknownProject(), goOnPastUnknown: true });
  assert.equal(code, 0);
  assert.ok(fs.existsSync(path.join(folder, "app.toml")));
});
