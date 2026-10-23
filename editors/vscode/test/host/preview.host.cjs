// The page preview inside VS Code: a page file opens in it, the custom
// editor package.json declares for pages/*.page.toml.
const assert = require("node:assert/strict");
const vscode = require("vscode");
const { folderFile, test, waitFor } = require("./runner.cjs");

test("a page file opens in the page preview", async () => {
  const uri = folderFile("pages", "browsers2.page.toml");
  await vscode.commands.executeCommand("vscode.open", uri);
  const input = await waitFor(() => {
    const tab = vscode.window.tabGroups.activeTabGroup.activeTab;
    return tab?.input instanceof vscode.TabInputCustom
      && tab.input.uri.toString() === uri.toString() && tab.input;
  }, "the page file's tab");
  assert.equal(input.viewType, "nxwright.pagePreview");
});

// Waits until a text editor of `uri` is in front, its cursor on `line`.
function textAt(uri, line, what) {
  return waitFor(() => {
    const editor = vscode.window.activeTextEditor;
    return editor?.document.uri.toString() === uri.toString()
      && editor.selection.active.line === line && editor;
  }, what, 10000);
}

test("Go to Definition opens the page file as text, at the object's table", async () => {
  const uri = folderFile("pages", "browsers2.page.toml");
  const page = uri.toString();
  await vscode.commands.executeCommand("vscode.open", uri);
  await waitFor(() => vscode.window.tabGroups.activeTabGroup.activeTab?.input
    instanceof vscode.TabInputCustom, "the page preview in front");
  // As the preview's right-click menu passes it: on a component, then on
  // the page alone. browsers2's `[page]` is on line 1, custom's
  // `[[component]]` on line 25, and barNever's on line 45.
  await vscode.commands.executeCommand("nxwright.goToDefinition",
                                       { page, component: "custom", components: ["custom"] });
  await textAt(uri, 24, "custom's table");
  await vscode.commands.executeCommand("nxwright.goToDefinition", { page, components: [] });
  await textAt(uri, 0, "the page's table");
  // As the Components list passes it.
  await vscode.commands.executeCommand("nxwright.goToDefinition",
                                       { name: "barNever", type: "file-browser", firstLine: 44,
                                         lastLine: 52 });
  await textAt(uri, 44, "barNever's table");
  await vscode.commands.executeCommand("nxwright.goToDefinition",
                                       { name: "browsers2", type: "page", firstLine: 0,
                                         lastLine: 9 });
  await textAt(uri, 0, "the page's table, from the Components list");
  // Lines added above, not saved, move the table: its line is the edited one.
  const editor = vscode.window.activeTextEditor;
  await editor.edit((edit) => edit.insert(new vscode.Position(0, 0), "# one\n# two\n"));
  await vscode.commands.executeCommand("nxwright.goToDefinition",
                                       { page, component: "custom", components: ["custom"] });
  await textAt(uri, 26, "custom's table, moved down by the unsaved lines");
  await vscode.commands.executeCommand("workbench.action.files.revert");
  assert.equal(editor.document.isDirty, false);
});
