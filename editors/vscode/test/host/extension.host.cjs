// The extension inside VS Code: it activates on a source folder, registers
// every command its package.json declares, and gives .nx files its own
// defaults for their encoding.
const assert = require("node:assert/strict");
const vscode = require("vscode");
const { test, waitFor } = require("./runner.cjs");

const EXTENSION = "nxwright.nxwright-language";

test("the extension activates on the source folder VS Code opened", async () => {
  // Its activation event is a folder holding an app.toml: nothing here
  // activates it by hand.
  const extension = vscode.extensions.getExtension(EXTENSION);
  assert.ok(extension, `${EXTENSION} is loaded`);
  await waitFor(() => extension.isActive, "the extension to activate", 30000);
});

test("every command package.json declares is registered", async () => {
  const declared = vscode.extensions.getExtension(EXTENSION).packageJSON.contributes.commands
    .map((entry) => entry.command);
  const registered = new Set(await vscode.commands.getCommands(true));
  assert.ok(declared.length > 0);
  assert.deepEqual(declared.filter((command) => !registered.has(command)), []);
});

test(".nx files are saved in UTF-8 and their encoding never guessed", () => {
  // VS Code's own defaults are the same, so only the nxwright language's
  // defaults tell that the extension sets them. A language's value wins
  // over the user's own setting for every file.
  const nxFiles = vscode.workspace.getConfiguration("files", { languageId: "nxwright" });
  assert.equal(nxFiles.inspect("encoding").defaultLanguageValue, "utf8");
  assert.equal(nxFiles.inspect("autoGuessEncoding").defaultLanguageValue, false);
});
