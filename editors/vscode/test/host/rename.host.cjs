// Tests renaming a component from the page preview's menu inside VS Code
// (src/pageEditing.ts), while another extension, such as one for TOML
// files, offers rename for page files.
const assert = require("node:assert/strict");
const vscode = require("vscode");
const { folderFile, test } = require("./runner.cjs");

test("a rename from the preview's menu is not stopped by another extension", async () => {
  // The other extension's provider says that nothing under the cursor can
  // be renamed. VS Code's own rename command stops at such an answer, and
  // never asks nxwright's language server.
  const other = vscode.languages.registerRenameProvider(
    { scheme: "file", pattern: "**/*.page.toml" }, {
      prepareRename() {
        throw new Error("The element can't be renamed.");
      },
      provideRenameEdits() {
        return undefined;
      },
    });
  const toml = folderFile("pages", "browsers2.page.toml");
  const code = folderFile("pages", "browsers2.nx");
  try {
    await vscode.commands.executeCommand(
      "nxwright.renameComponent", { page: toml.toString(), components: ["next"] }, "onward");
    const text = (await vscode.workspace.openTextDocument(code)).getText();
    assert.match(text, /^on onward\.up:/m);
  } finally {
    other.dispose();
    // Nothing is saved: both files go back to what is on disk.
    for (const uri of [toml, code]) {
      await vscode.window.showTextDocument(uri);
      await vscode.commands.executeCommand("workbench.action.files.revert");
    }
  }
});
