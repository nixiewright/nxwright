// Tests Delete, of the Pages and Media sections, inside VS Code
// (src/mediaActions.ts). A real `nxwright remove` would delete from the
// source folder the tests share, so nxwright's command is
// stand_in_nxwright.py while they run (stand_in.cjs): it answers `remove`
// without deleting anything. The tests give the answer to Delete's question,
// so that nothing prompts. Delete runs `remove` as a task, so the tests read
// its runs from the stand-in's default log.
const assert = require("node:assert/strict");
const vscode = require("vscode");
const { test, waitFor } = require("./runner.cjs");
const { withStandIn } = require("./stand_in.cjs");

test("Delete runs remove once, and looks for uses only when its setting is on", async () => {
  await withStandIn(async (work, runs, taskRuns) => {
    const folder = vscode.workspace.workspaceFolders[0].uri.fsPath;
    // browsers is the first of three pages, so Delete offers to shift the
    // IDs after it. Delete has nothing to ask about until the extension has
    // read the project's lists again, through the stand-in.
    await waitFor(async () => {
      await vscode.commands.executeCommand("nxwright.deletePage", { name: "browsers" }, "shift");
      return taskRuns("remove").length > 0;
    }, "Delete to run remove, once the project's lists are read");
    // textFile is the last picture, so no ID changes.
    await vscode.commands.executeCommand("nxwright.deleteResource",
                                         { list: "pictures", name: "textFile" }, "delete");
    assert.deepEqual(taskRuns("remove").slice(-2), [[folder, "page", "browsers"],
                                                    [folder, "picture", "textFile"]]);
    const settings = vscode.workspace.getConfiguration("nxwright");
    await settings.update("checks.delete", true, vscode.ConfigurationTarget.Global);
    try {
      await vscode.commands.executeCommand("nxwright.deletePage", { name: "browsers" },
                                           "keepIds");
    } finally {
      await settings.update("checks.delete", undefined, vscode.ConfigurationTarget.Global);
    }
    assert.deepEqual(taskRuns("remove").at(-1),
                     [folder, "page", "browsers", "--keep-ids", "--checked"]);
  });
});
