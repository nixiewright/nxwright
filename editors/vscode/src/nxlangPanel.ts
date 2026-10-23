// The panel explaining the switch to nxlang, the nxwright language, and
// making it, which Switch to nxlang opens for the current project: a section
// for each thing nxlang adds, those with code from the server
// (nxwright/nxlangSamples), each with how a person writes it in strict
// Nextion beside how they write it in nxlang; what else nxlang lets you do,
// also from the server (nxwright/nxlangMoreFeatures); the lines the switch will
// rewrite (nxwright/nxlangSwitch); how the project still builds; and how to
// go back. Its page is media/nxlang-panel.mjs. A file the switch changes
// opens in VS Code's diff editor, both sides read-only.
//
// The switch is made whole, in one workspace edit one undo takes back, not
// through VS Code's Refactor Preview, which lets a file be left out: a folder
// in nxlang with lines not rewritten would build differently from the
// Editor's meaning. It is made from the files as the server gives them when
// the button is pressed, and only when they are what the panel listed. Once
// it is made, the panel offers to format the folder's code, through the
// Refactor Preview, where leaving a file out is harmless.
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { CurrentProject, NO_PROJECT_ERROR } from "./currentProject";
import { appName } from "./projectName";
import { unsavedFilesIn } from "./unsavedChanges";
import { errorText } from "./userMessages";
import { webviewPage } from "./webviewPage";

// A section of the page with code, as the server gives it.
interface Section {
  key: string;
  heading: string;
  words: string;
  strict: string;
  nxlang: string;
  after: string;
}

// The switch, as the server gives it: each file it writes, and each line of
// code it changes.
interface Switch {
  files: { path: string; text: string }[];
  changes: { file: string; line: number; before: string; after: string }[];
}

// The scheme of the files after the switch, for the diff editor.
const SWITCHED_SCHEME = "nxwright-switched";

export class NxlangPanel implements vscode.TextDocumentContentProvider {
  private panel: vscode.WebviewPanel | undefined;
  private sections: Section[] = [];
  // The switch the panel lists, for the current project, or undefined.
  private listed: Switch | undefined;
  // The files' texts after the switch, as last listed, which a diff opened
  // from the list shows, even once the switch is made.
  private switchedTexts = new Map<string, string>();

  constructor(private readonly context: vscode.ExtensionContext,
              private readonly client: () => LanguageClient | undefined,
              private readonly project: CurrentProject) {}

  register(): vscode.Disposable[] {
    return [
      vscode.workspace.registerTextDocumentContentProvider(SWITCHED_SCHEME, this),
      // Another project, or the switch made, which changes its language.
      this.project.onDidChange(() => {
        this.sendProject();
        void this.sendChanges();
      }),
    ];
  }

  // A file's text after the switch, by its path in the folder.
  provideTextDocumentContent(uri: vscode.Uri): string {
    return this.switchedTexts.get(uri.path) ?? "";
  }

  // Shows the panel for the current project, opening it when it is not open.
  show(): void {
    if (!this.project.folder) {
      void vscode.window.showErrorMessage(NO_PROJECT_ERROR);
      return;
    }
    if (this.panel) {
      this.panel.reveal();
      this.sendProject();
      void this.sendChanges();
      // Sections that could not be had, as before the language server ran.
      if (this.sections.length === 0) {
        void this.sendSamples(this.panel);
      }
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      "nxwrightNxlang", "Switch to nxlang", vscode.ViewColumn.Active, {
        enableScripts: true,
        localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media")],
      });
    this.panel = panel;
    panel.onDidDispose(() => {
      if (this.panel === panel) {
        this.panel = undefined;
      }
    });
    panel.webview.html = webviewPage(panel.webview, this.context.extensionUri, {
      script: "nxlang-panel.mjs", styles: STYLES, body: BODY });
    panel.webview.onDidReceiveMessage(async (message) => {
      if (message.type === "ready") {
        this.sendProject();
        await Promise.all([this.sendSamples(panel), this.sendChanges()]);
      } else if (message.type === "openChange" && typeof message.file === "string") {
        await this.openChange(message.file);
      } else if (message.type === "switch") {
        await this.makeSwitch();
      } else if (message.type === "format") {
        await this.format();
      }
    });
  }

  // The project's name and language, which decide the panel's last part.
  private sendProject(): void {
    void this.panel?.webview.postMessage({
      type: "project",
      name: this.project.folder && appName(this.project.info, this.project.folder.fsPath),
      language: this.project.info?.language });
  }

  private async sendSamples(panel: vscode.WebviewPanel): Promise<void> {
    const client = this.client();
    if (!client) {
      void panel.webview.postMessage({
        type: "samples", error: "the language server is not running" });
      return;
    }
    try {
      // What else nxlang lets you do: each item's code between backticks.
      // Without it, the panel shows its sections, and leaves the list out.
      const [sections, more] = await Promise.all([
        client.sendRequest<Section[]>("nxwright/nxlangSamples", {}),
        client.sendRequest<string[]>("nxwright/nxlangMoreFeatures", {}).catch(() => [])]);
      this.sections = sections;
      void panel.webview.postMessage({ type: "samples", samples: sections, more });
    } catch (error) {
      void panel.webview.postMessage({ type: "samples", error: errorText(error) });
    }
  }

  // Asks the server what the switch would write in the current project, or
  // why it would refuse. Returns it, or undefined with the reason.
  private async askSwitch(): Promise<{ answer?: Switch; error?: string }> {
    const folder = this.project.folder;
    const client = this.client();
    if (!folder || !client) {
      return { error: client ? "there is no current project"
        : "the language server is not running" };
    }
    try {
      return { answer: await client.sendRequest<Switch>("nxwright/nxlangSwitch",
                                                       { folder: folder.fsPath }) };
    } catch (error) {
      return { error: errorText(error) };
    }
  }

  // Lists the lines the switch would change, for a project in the Editor's
  // own language.
  private async sendChanges(): Promise<void> {
    if (!this.panel || this.project.info?.language !== "nextion") {
      // No switch to list, as for a project in nxlang, or one the server has
      // not answered about yet: the page offers none.
      this.listed = undefined;
      void this.panel?.webview.postMessage({ type: "changes" });
      return;
    }
    const { answer, error } = await this.askSwitch();
    this.listed = answer;
    for (const file of answer?.files ?? []) {
      this.switchedTexts.set(`/${file.path}`, file.text);
    }
    void this.panel?.webview.postMessage({ type: "changes", changes: answer?.changes, error });
  }

  // Opens a file the switch changes in the diff editor: as it is, on the
  // left; after the switch, on the right.
  private async openChange(file: string): Promise<void> {
    const folder = this.project.folder;
    if (!folder || !this.listed?.files.some((entry) => entry.path === file)) {
      return;
    }
    await vscode.commands.executeCommand(
      "vscode.diff", vscode.Uri.joinPath(folder, file),
      vscode.Uri.from({ scheme: SWITCHED_SCHEME, path: `/${file}` }),
      `${file}: as it is, and after the switch to nxlang`);
  }

  // Makes the switch, as listed: whole, after asking once more.
  private async makeSwitch(): Promise<void> {
    const folder = this.project.folder;
    if (!folder || !this.listed) {
      return;
    }
    const unsaved = unsavedFilesIn(folder);
    if (unsaved.length > 0) {
      this.note(`${unsaved.length} file(s) of the project have unsaved changes. Save or ` +
                "revert them first, as the switch will rewrite the project's files.");
      return;
    }
    const { answer, error } = await this.askSwitch();
    if (!answer || JSON.stringify(answer) !== JSON.stringify(this.listed)) {
      // The code changed since the list was made: no file is written from
      // an older text.
      await this.sendChanges();
      this.note(error ?? "Your code changed since this list was made. Check the list " +
                "again, then switch.");
      return;
    }
    const lines = answer.changes.length;
    const choice = await vscode.window.showWarningMessage(
      `Switch ${appName(this.project.info, folder.fsPath)} to nxlang?`,
      { modal: true,
        detail: `${lines} line(s) of code will get parentheses, so that they keep ` +
          "calculating the same way. There is no command to switch back." },
      "Switch");
    if (choice !== "Switch") {
      return;
    }
    const edit = new vscode.WorkspaceEdit();
    const documents: vscode.TextDocument[] = [];
    for (const file of answer.files) {
      const document = await vscode.workspace.openTextDocument(
        vscode.Uri.joinPath(folder, file.path));
      documents.push(document);
      // With LF line endings, as nxwright language writes the files.
      edit.set(document.uri, [vscode.TextEdit.replace(wholeOf(document), file.text),
                              vscode.TextEdit.setEndOfLine(vscode.EndOfLine.LF)]);
    }
    if (!(await vscode.workspace.applyEdit(edit))) {
      this.note("The switch could not be made: VS Code did not apply the changes.");
      return;
    }
    await Promise.all(documents.map((document) => document.save()));
    this.listed = undefined;
    void this.panel?.webview.postMessage({ type: "switched" });
  }

  // Offers to format each .nx file of the project, as Format Document does,
  // through nxwright's language server, which formats them, in one edit the
  // Refactor Preview shows. The files it refuses, such as one that does not
  // build, are left out, and named.
  private async format(): Promise<void> {
    const folder = this.project.folder;
    const client = this.client();
    if (!folder || !client) {
      return;
    }
    const files = await nxFilesOf(folder);
    const edit = new vscode.WorkspaceEdit();
    const refused: string[] = [];
    const changed: vscode.Uri[] = [];
    const metadata = { needsConfirmation: true, label: "Format the code in nxwright's style" };
    for (const file of files) {
      const options = { tabSize: 2, insertSpaces: true };
      try {
        const edits = await client.sendRequest<unknown[] | null>("textDocument/formatting", {
          textDocument: { uri: client.code2ProtocolConverter.asUri(file) }, options });
        const converted = await client.protocol2CodeConverter.asTextEdits(
          edits as Parameters<typeof client.protocol2CodeConverter.asTextEdits>[0]);
        for (const textEdit of converted ?? []) {
          edit.replace(file, textEdit.range, textEdit.newText, metadata);
        }
        if (converted?.length) {
          changed.push(file);
        }
      } catch (error) {
        refused.push(`${vscode.workspace.asRelativePath(file)}: ${errorText(error)}`);
      }
    }
    // Applied, or not, as when the Refactor Preview is cancelled.
    const applied = changed.length > 0 && await vscode.workspace.applyEdit(
      edit, { isRefactoring: true });
    if (applied) {
      for (const file of changed) {
        const document = vscode.workspace.textDocuments.find(
          (open) => open.uri.toString() === file.toString());
        if (document?.isDirty) {
          await document.save();
        }
      }
    }
    void this.panel?.webview.postMessage({
      type: "formatted", changed: applied ? changed.length : 0, offered: changed.length, refused });
  }

  private note(text: string): void {
    void this.panel?.webview.postMessage({ type: "note", text });
  }

}

// The .nx files in `folder` and the folders inside it, read from the disk,
// as a project outside the workspace's folders is no workspace search's.
async function nxFilesOf(folder: vscode.Uri): Promise<vscode.Uri[]> {
  const found: vscode.Uri[] = [];
  for (const [name, type] of await vscode.workspace.fs.readDirectory(folder)) {
    const entry = vscode.Uri.joinPath(folder, name);
    if (type === vscode.FileType.Directory) {
      found.push(...await nxFilesOf(entry));
    } else if (type === vscode.FileType.File && name.endsWith(".nx")) {
      found.push(entry);
    }
  }
  return found;
}

// The range of a document's whole text.
function wholeOf(document: vscode.TextDocument): vscode.Range {
  return new vscode.Range(document.positionAt(0), document.positionAt(document.getText().length));
}

const BODY = `
<h1>Switch <span class="project-name"></span> to nxlang</h1>
<p>nxlang is nxwright's version of the Nextion language. It keeps everything you know, and adds
what strict Nextion is missing: functions, the usual calculation order, constants, local
variables, and more. Your project still builds into an ordinary HMI file.</p>

<div id="sections"><p class="hint">Loading the examples...</p></div>
<div id="changes"><p class="hint">Finding the lines the switch will change...</p></div>

<div id="more" hidden>
<h2>And more</h2>
<p>nxlang also lets you:</p>
<ul id="more-list"></ul>
</div>

<h2>Building, and the Nextion Editor</h2>
<p>nxlang is compiled into strict Nextion code when you build. The HMI file still holds ordinary
Nextion code, and you keep using the Nextion Editor to compile it into a TFT file, as before. To
see what a file compiles into, use "Show this file in strict Nextion syntax" in its title
bar.</p>

<h2>Going back</h2>
<p>There is no command to switch back. Right after switching, Undo offers to take the whole
switch back. Later, you can extract the HMI file nxwright builds into a new folder, which gives
you strict Nextion code again, with some differences:</p>
<ul>
  <li>Functions become hidden components that your code clicks.</li>
  <li>Constants are replaced by their values.</li>
  <li>Local variables, and calculations, conditions, and loops that strict Nextion cannot
  write, become extra variables and several lines.</li>
</ul>

<div id="switch"></div>
<p id="note" class="note" hidden></p>
<div id="after" hidden>
  <h2>Switched</h2>
  <p><span class="project-name"></span> now uses nxlang. If you change your mind right away,
  Undo in any of the changed files offers to take the whole switch back.</p>
  <p>nxwright can also tidy your code into one consistent style, as Format Document does. VS
  Code will show you each change before applying it.</p>
  <button id="format">Format the project's code</button>
  <div id="formatted"></div>
</div>`;

const STYLES = `
  body { padding: 0 20px 24px; max-width: 60em; line-height: 1.45; }
  h1 { font-size: 1.5em; font-weight: normal; }
  h2 { font-size: 1.15em; font-weight: normal; margin-top: 1.6em; padding-bottom: 4px;
       border-bottom: 1px solid var(--vscode-panel-border, transparent); }
  code, pre {
    font-family: var(--vscode-editor-font-family); font-size: var(--vscode-editor-font-size);
  }
  .codes { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 8px 0; }
  .codes.single { grid-template-columns: 1fr; }
  .codes > div { min-width: 0; }
  .label { font-size: 0.9em; color: var(--vscode-descriptionForeground); margin-bottom: 2px; }
  pre { margin: 0; padding: 8px; overflow: auto;
        background: var(--vscode-textCodeBlock-background); }
  .file pre { max-height: 22em; }
  button { font: inherit; padding: 4px 12px; border: none; cursor: pointer;
           color: var(--vscode-button-foreground); background: var(--vscode-button-background); }
  button:hover { background: var(--vscode-button-hoverBackground); }
  button.secondary { color: var(--vscode-button-secondaryForeground);
                     background: var(--vscode-button-secondaryBackground); }
  #switch { margin-top: 24px; }
  .file { margin: 10px 0; }
  .file h3 { font-size: 1em; margin: 0 0 4px; display: flex; gap: 12px; align-items: center; }
  .note { padding: 6px 10px; border-left: 3px solid var(--vscode-editorWarning-foreground); }
  #after button { margin: 4px 0 8px; }
  .hint { color: var(--vscode-descriptionForeground); }
  .problem { color: var(--vscode-errorForeground); }`;
