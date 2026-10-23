// The language server's answers inside VS Code, asked through VS Code's own
// commands, as its editor asks for them: completion, a hover, and a rename.
const assert = require("node:assert/strict");
const vscode = require("vscode");
const { folderFile, test, waitFor } = require("./runner.cjs");

// browsers2.nx: `on next.up:`, then `  page selects`.
const PAGE_CODE = ["pages", "browsers2.nx"];
// Inside `next`, a button of the page.
const NEXT = new vscode.Position(0, 3);
// The start of `selects`.
const SELECTS = new vscode.Position(1, 7);

async function pageCode() {
  const uri = folderFile(...PAGE_CODE);
  await vscode.window.showTextDocument(uri);
  return uri;
}

test("completion offers the page's components", async () => {
  // `picked` is a component of the page that the file does not name, so
  // only the server can offer it, not VS Code's words of the file.
  const uri = await pageCode();
  await waitFor(async () => {
    const list = await vscode.commands.executeCommand(
      "vscode.executeCompletionItemProvider", uri, SELECTS);
    return list.items.some((item) => (item.label.label ?? item.label) === "picked");
  }, "the page's component picked among the completions");
});

test("a hover shows a component's table", async () => {
  const uri = await pageCode();
  const hovers = await waitFor(async () => {
    const found = await vscode.commands.executeCommand("vscode.executeHoverProvider", uri, NEXT);
    return found.length > 0 && found;
  }, "the hover of next");
  const text = hovers[0].contents.map((part) => part.value ?? part).join("\n");
  assert.match(text, /type = "button"/);
});

test("a rename renames a component in its code and its page file", async () => {
  // The edit is asked for, not applied: the fixture stays as it is.
  const uri = await pageCode();
  const edit = await vscode.commands.executeCommand(
    "vscode.executeDocumentRenameProvider", uri, NEXT, "onward");
  const files = edit.entries().map(([file]) => file.path.split("/").pop()).sort();
  assert.deepEqual(files, ["browsers2.nx", "browsers2.page.toml"]);
});
