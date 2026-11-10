// Tests which page nxwright's side bar shows when the active editor changes
// (src/pages.ts).
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vscode = require("vscode");
const { folderFile, test } = require("./runner.cjs");

test("the side bar keeps its page while a file that pages include is active", async () => {
  // The extension treats a .nx file in a `pages` folder as a file that pages
  // include when no .page.toml file is next to it. The test makes such a
  // file in a temporary folder, because tests must not write in the source
  // folder.
  const pages = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "nxwright-side-bar-")), "pages");
  fs.mkdirSync(pages);
  const included = vscode.Uri.file(path.join(pages, "shared.nx"));
  fs.writeFileSync(included.fsPath, "function shared():\n  sys0 = 1\n");
  const toml = folderFile("pages", "browsers2.page.toml");
  const code = folderFile("pages", "browsers2.nx");
  try {
    // The side bar shows browsers2, then the included file becomes active.
    await vscode.window.showTextDocument(code);
    await vscode.window.showTextDocument(included);
    // Rename in the Components list works on the page the side bar shows, so
    // it changes browsers2 only if the side bar kept that page. The first
    // argument is the `next` component, in the form the list passes.
    await vscode.commands.executeCommand(
      "nxwright.renameComponent", { name: "next", type: "button", firstLine: 0, lastLine: 0 },
      "onward");
    const text = (await vscode.workspace.openTextDocument(code)).getText();
    assert.match(text, /^on onward\.up:/m);
  } finally {
    await vscode.window.showTextDocument(included);
    await vscode.commands.executeCommand("workbench.action.closeActiveEditor");
    // Nothing is saved: both files go back to what is on disk.
    for (const uri of [toml, code]) {
      await vscode.window.showTextDocument(uri);
      await vscode.commands.executeCommand("workbench.action.files.revert");
    }
  }
});
