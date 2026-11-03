// Tests the Extract command inside VS Code, on a project file that contains
// a block nxwright does not handle. write_unknown_project.py writes that file.
// The tests pass the command its source folder, its project file, and whether
// to go on past content the next build may lose, so that the command does not
// prompt. unknown-content.test.mjs tests the prompts themselves. Each test
// extracts into a new folder in the temporary folder, not into a fixture.
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vscode = require("vscode");
const { test } = require("./runner.cjs");

// The project file that both tests use. It is written only once.
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
