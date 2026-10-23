// The commands that act on the active file's source folder, run with a page
// preview in front. A preview is a custom editor, which leaves no text
// editor active, so the commands take its page file instead.
const assert = require("node:assert/strict");
const vscode = require("vscode");
const { folderFile, test, waitFor } = require("./runner.cjs");

// Opens a page file in its page preview, and waits until its tab is in front.
async function previewInFront() {
  const uri = folderFile("pages", "browsers2.page.toml");
  await vscode.commands.executeCommand("vscode.open", uri);
  await waitFor(() => {
    const input = vscode.window.tabGroups.activeTabGroup.activeTab?.input;
    return input instanceof vscode.TabInputCustom && input.uri.toString() === uri.toString();
  }, "the page preview in front");
  assert.equal(vscode.window.activeTextEditor, undefined);
}

// The simulator's panel's tab, or undefined while none is open.
function simulatorTab() {
  return vscode.window.tabGroups.all.flatMap((group) => group.tabs)
    .find((tab) => tab.input instanceof vscode.TabInputWebview
          && tab.input.viewType.endsWith("nxwrightSimulator"));
}

test("the Fonts panel opens with a page preview in front", async () => {
  await previewInFront();
  await vscode.commands.executeCommand("nxwright.fonts");
  const tab = await waitFor(() => vscode.window.tabGroups.all.flatMap((group) => group.tabs)
    .find((tab) => tab.input instanceof vscode.TabInputWebview
          && tab.input.viewType.endsWith("nxwrightFonts")), "the Fonts panel", 10000);
  await vscode.window.tabGroups.close(tab);
});

test("Show Editor code shows the page's code with a page preview in front", async () => {
  await previewInFront();
  await vscode.commands.executeCommand("nxwright.showEditorCode");
  const page = folderFile("pages", "browsers2.nx").toString();
  const view = await waitFor(() => vscode.workspace.textDocuments.find(
    (document) => document.uri.scheme === "nxwright-editor-code" && document.uri.query === page),
                             "the Editor code of browsers2.nx", 10000);
  assert.ok(view.getText().length > 0);
});

test("Simulate starts with a page preview in front", async () => {
  await previewInFront();
  let session;
  const listening = vscode.debug.onDidStartDebugSession((started) => {
    session = started;
  });
  try {
    await vscode.commands.executeCommand("nxwright.simulate");
    await waitFor(() => session, "the simulation", 10000);
    assert.equal(vscode.Uri.file(session.configuration.sourceFolder).toString(),
                 folderFile().toString());
  } finally {
    listening.dispose();
    // A simulation left running would carry on into the later tests.
    if (session) {
      await vscode.debug.stopDebugging(session);
    }
  }
});

test("Simulate this page starts on the page its button is above, not the one in front", async () => {
  // The button of an editor in another group than the active one is given
  // that editor's file.
  await previewInFront();
  let session;
  const listening = vscode.debug.onDidStartDebugSession((started) => {
    session = started;
  });
  try {
    await vscode.commands.executeCommand("nxwright.simulateThisPage",
                                         folderFile("pages", "selects.page.toml"));
    await waitFor(() => session, "the simulation", 10000);
    assert.equal(vscode.Uri.file(session.configuration.sourceFolder).toString(),
                 folderFile().toString());
    assert.equal(session.configuration.page, "selects");
  } finally {
    listening.dispose();
    if (session) {
      await vscode.debug.stopDebugging(session);
    }
  }
});

test("the simulator's panel, closed, opens again on the page shown while the simulation runs",
     async () => {
  await previewInFront();
  let session;
  let ended = false;
  const listening = [
    vscode.debug.onDidStartDebugSession((started) => {
      session = started;
    }),
    vscode.debug.onDidTerminateDebugSession((stopped) => {
      ended ||= stopped === session;
    }),
  ];
  try {
    await vscode.commands.executeCommand("nxwright.simulate");
    await waitFor(() => session, "the simulation", 10000);
    // Its title names the page once the simulation has drawn it.
    const tab = await waitFor(() => simulatorTab()?.label.startsWith("Simulator: ")
                                && simulatorTab(), "the simulator's panel showing a page", 30000);
    await vscode.window.tabGroups.close(tab);
    assert.equal(simulatorTab(), undefined);
    await vscode.commands.executeCommand("nxwright.showSimulator");
    // The panel opened again shows the page at once, from the last drawing.
    await waitFor(() => simulatorTab()?.label.startsWith("Simulator: "),
                  "the simulator's panel opened again, showing the page", 10000);
    assert.equal(ended, false);
  } finally {
    listening.forEach((listener) => listener.dispose());
    if (session) {
      await vscode.debug.stopDebugging(session);
    }
  }
});
