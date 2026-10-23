// The language server inside VS Code: the build's errors show in a .nx file
// as it is typed, unsaved, a quick fix of one applies, and the server still
// answers once its command is set again to an equal one.
const assert = require("node:assert/strict");
const vscode = require("vscode");
const { folderFile, test, waitFor } = require("./runner.cjs");

// browsers2.nx's second line, the code of `on next.up:`.
const PAGE_CODE = ["pages", "browsers2.nx"];
const BROKEN_LINE = 1;

function errorsIn(uri) {
  return vscode.languages.getDiagnostics(uri)
    .filter((diagnostic) => diagnostic.severity === vscode.DiagnosticSeverity.Error);
}

// Waits for the file's errors to hold one whose message matches `words`,
// and returns them. Each answer of the server replaces the file's errors, so
// a late answer to an earlier edit, holding another error, is waited past.
function errorsNaming(uri, words, what) {
  return waitFor(() => errorsIn(uri).some((error) => words.test(error.message)) && errorsIn(uri),
                 what);
}

// Types a line naming a component the page lacks, waits for the build's
// error on it, then takes the line back, by undo, and waits for the error
// to go. Nothing is saved: the server reads the file as typed.
async function brokenThenMended() {
  const uri = folderFile(...PAGE_CODE);
  const editor = await vscode.window.showTextDocument(uri);
  await editor.edit((edit) => edit.insert(new vscode.Position(BROKEN_LINE, 0),
                                          '  nosuch.txt = "x"\n'));
  const errors = await errorsNaming(uri, /nosuch/, "the build's error on the line naming nosuch");
  assert.equal(errors.length, 1);
  assert.match(errors[0].message, /nosuch/);
  assert.equal(errors[0].range.start.line, BROKEN_LINE);
  await vscode.commands.executeCommand("undo");
  await waitFor(() => errorsIn(uri).length === 0, "the error to go once the line is taken back");
  assert.equal(editor.document.isDirty, false);
}

test("a line naming a component the page lacks gets the build's error, as typed", async () => {
  await brokenThenMended();
});

test("a quick fix writes a command in small letters", async () => {
  // The fix is offered only when VS Code hands the problem's data back to
  // the server with its request. It is applied, then taken back by undo
  // with the line, so the fixture stays as it was.
  const uri = folderFile(...PAGE_CODE);
  const editor = await vscode.window.showTextDocument(uri);
  await editor.edit((edit) => edit.insert(new vscode.Position(BROKEN_LINE, 0), "  CLS BLUE\n"));
  const [error] = await errorsNaming(uri, /CLS/, "the build's error on the line of CLS");
  const actions = await vscode.commands.executeCommand(
    "vscode.executeCodeActionProvider", uri, error.range, vscode.CodeActionKind.QuickFix.value);
  const fix = actions.find((action) => action.title === "Write cls in small letters");
  assert.ok(fix, `no quick fix among ${actions.map((action) => action.title)}`);
  assert.ok(await vscode.workspace.applyEdit(fix.edit));
  assert.equal(editor.document.lineAt(BROKEN_LINE).text, "  cls BLUE");
  await waitFor(() => errorsIn(uri).length === 0, "the error to go once fixed");
  // The first undo brings CLS back, whose error the server may give again
  // after the second takes the line away; the next test waits past it.
  await vscode.commands.executeCommand("undo");
  await vscode.commands.executeCommand("undo");
  await waitFor(() => !editor.document.isDirty && errorsIn(uri).length === 0,
                "the fixture as it was, without errors");
});

test("the server still answers once nxwright.command is set again, equal", async () => {
  // Whether the server is kept or started again, test/server-keeper.test.mjs
  // says; here, that it answers after. The setting goes to the user settings
  // of the test's VS Code, in .vscode-test/.
  const configuration = vscode.workspace.getConfiguration("nxwright");
  const command = configuration.get("command");
  assert.ok(command.length > 0, "run.mjs set nxwright.command");
  await configuration.update("command", [...command], vscode.ConfigurationTarget.Global);
  await brokenThenMended();
});
