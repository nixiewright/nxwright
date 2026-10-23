// The Fonts panel: a tab for a source folder, showing its fonts, each drawn
// as a sample of a text, with a form making a new font from a typeface
// installed on the computer or a typeface file, and another adding a
// ready-made font file (media/fonts.mjs). The language server draws the
// samples and adds the fonts (font_panel.py). This passes the page's
// requests on to it, opens the file dialogs a webview cannot, and tells the
// page when the folder's fonts change.
import * as path from "path";
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { CurrentProject } from "./currentProject";
import { errorText } from "./userMessages";
import { webviewPage } from "./webviewPage";

// The server's requests the page may send, and no others.
const REQUESTS = new Set(["nxwright/fonts", "nxwright/typefaces", "nxwright/fontSample",
                          "nxwright/addFont"]);

// The files the page's file dialogs offer.
const DIALOGS: Record<string, vscode.OpenDialogOptions> = {
  typeface: {
    filters: { "Typefaces": ["ttf", "otf", "ttc"] },
    openLabel: "Draw the font from this file",
    title: "nxwright: the typeface file to draw the font from",
  },
  fontFile: {
    filters: { "Nextion fonts": ["zi"] },
    openLabel: "Add this font",
    title: "nxwright: the font file to add",
  },
};

const STYLES = `
  body { padding: 0 16px 16px; }
  h1 { font-size: 1.4em; font-weight: normal; }
  h2 { font-size: 1.1em; font-weight: normal; margin-top: 1.6em; padding-bottom: 4px;
       border-bottom: 1px solid var(--vscode-panel-border, transparent); }
  input, select, button { font: inherit; }
  input, select {
    color: var(--vscode-input-foreground); background: var(--vscode-input-background);
    border: 1px solid var(--vscode-input-border, transparent);
  }
  button {
    color: var(--vscode-button-foreground); background: var(--vscode-button-background);
    border: none; padding: 4px 10px; cursor: pointer;
  }
  button.secondary {
    color: var(--vscode-button-secondaryForeground);
    background: var(--vscode-button-secondaryBackground);
  }
  button:disabled { opacity: 0.5; cursor: default; }
  .field { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 8px 0; }
  .field > label:first-child { min-width: 7em; }
  #typefaces { width: 100%; max-width: 36em; }
  #sample-text { width: 100%; max-width: 36em; }
  .font { margin: 12px 0 20px; }
  .font-heading { display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px; }
  .sample { margin: 8px 0; overflow-x: auto; }
  .sample img { display: block; image-rendering: pixelated; }
  .hint { color: var(--vscode-descriptionForeground); }
  .problem { color: var(--vscode-errorForeground); }
  .warning { color: var(--vscode-editorWarning-foreground); }`;

const BODY = `
<h1 id="title">Fonts</h1>
<div class="field">
  <label for="sample-text">Sample text</label>
  <input id="sample-text" type="text">
</div>
<h2>The folder's fonts</h2>
<div id="fonts"></div>
<section id="new-font">
  <h2>New font</h2>
  <p id="cannot-draw" class="hint" hidden></p>
  <div class="field">
    <label for="typeface-filter">Typeface</label>
    <input id="typeface-filter" type="search" placeholder="Narrow by name">
    <button id="browse-typeface" class="secondary">Typeface file...</button>
  </div>
  <div class="field"><label></label><select id="typefaces" size="8"></select></div>
  <div class="field"><label></label><span id="typeface-file" class="hint"></span></div>
  <div class="field">
    <label for="height">Height</label>
    <input id="height" type="number" min="12" max="254" value="24"> pixels
  </div>
  <div id="characters-field" hidden>
    <div class="field">
      <label for="characters">Characters</label>
      <input id="characters" type="text" value="0-ff" spellcheck="false">
    </div>
    <div class="field"><label></label><span class="hint">Code points in hexadecimal, and
      ranges of them, such as 20-7e,400-4ff. The font holds them and the space, and the screen
      shows a character it lacks as its first.</span></div>
    <div class="field">
      <label></label>
      <label><input id="full-table" type="checkbox"> A full table</label>
    </div>
    <div class="field"><label></label><span class="hint">An entry for every code point to
      U+FFFF, at least 655 KB, whatever characters it contains. The screen shows a character it
      lacks as nothing, half the height wide.</span></div>
  </div>
  <div class="field">
    <label></label>
    <label><input id="smoothed" type="checkbox" checked> Smooth the edges</label>
  </div>
  <div class="field"><label for="new-name">Name</label><input id="new-name" type="text"></div>
  <div id="new-sample" class="sample"></div>
  <p id="new-note"></p>
  <button id="add-new" disabled>Add the font</button>
</section>
<section id="font-file">
  <h2>Add a font file</h2>
  <p class="hint">A ready-made .zi font, such as the Nextion Editor's font generator makes,
    added as it is.</p>
  <div class="field">
    <button id="browse-file" class="secondary">Choose a font file...</button>
    <span id="file-path" class="hint"></span>
  </div>
  <div class="field"><label for="file-name">Name</label><input id="file-name" type="text"></div>
  <div id="file-sample" class="sample"></div>
  <p id="file-note"></p>
  <button id="add-file" disabled>Add the font</button>
</section>
<p id="status" class="hint"></p>`;

// A message from the page: "ready", once it can take messages; or a
// question, which is answered by a "reply" with the same id.
interface PageMessage {
  type: string;
  id?: number;
  method?: string;
  params?: Record<string, unknown>;
  kind?: string;
}

export class FontPanels {
  // Each open panel, by its source folder's URI.
  private readonly panels = new Map<string, vscode.WebviewPanel>();

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly client: () => LanguageClient | undefined,
    private readonly project: CurrentProject,
  ) {}

  // Shows the panel of a source folder, opening it when it is not open;
  // with `atForm`, at its form for a new font; with `variation`, a font of
  // the folder, at the form filled from it, as its "Create a variation of
  // this font" fills it.
  async show(folder: vscode.Uri, atForm: boolean, variation?: string): Promise<void> {
    const open = this.panels.get(folder.toString());
    if (open) {
      open.reveal();
      if (variation !== undefined) {
        void open.webview.postMessage({ type: "variation", name: variation });
      } else if (atForm) {
        void open.webview.postMessage({ type: "showForm" });
      }
      return;
    }
    const name = await this.project.nameOf(folder);
    const panel = vscode.window.createWebviewPanel(
      "nxwrightFonts",
      `Fonts: ${name}`,
      vscode.ViewColumn.Active,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media")],
      },
    );
    this.panels.set(folder.toString(), panel);
    panel.onDidDispose(() => this.panels.delete(folder.toString()));
    panel.webview.onDidReceiveMessage((message: PageMessage) => {
      if (message.type === "ready") {
        void panel.webview.postMessage({
          type: "start", folder: name, atForm, variation });
      } else {
        void this.answer(panel, folder, message);
      }
    });
    panel.webview.html = webviewPage(panel.webview, this.context.extensionUri, {
      script: "fonts.mjs", styles: STYLES, body: BODY, allowImages: true });
  }

  // Tells the panel of the folder holding `uri` that its fonts may have
  // changed, when `uri` is its app.toml or a file of its fonts folder.
  changed(uri: vscode.Uri): void {
    for (const [key, panel] of this.panels) {
      const folder = vscode.Uri.parse(key);
      const relative = path.relative(folder.fsPath, uri.fsPath);
      if (relative === "app.toml" || relative.split(path.sep)[0] === "fonts") {
        void panel.webview.postMessage({ type: "changed" });
      }
    }
  }

  // Answers a question of the page: a request to the server, for the
  // folder's app.toml, or a file dialog.
  private async answer(panel: vscode.WebviewPanel, folder: vscode.Uri,
                       message: PageMessage): Promise<void> {
    let reply: { result?: unknown; error?: string };
    try {
      reply = { result: await this.result(folder, message) };
    } catch (error) {
      reply = { error: errorText(error) };
    }
    void panel.webview.postMessage({ type: "reply", id: message.id, ...reply });
  }

  private async result(folder: vscode.Uri, message: PageMessage): Promise<unknown> {
    if (message.type === "browse" && message.kind && message.kind in DIALOGS) {
      const chosen = await vscode.window.showOpenDialog({
        ...DIALOGS[message.kind], canSelectFiles: true, canSelectMany: false, defaultUri: folder,
      });
      return chosen ? chosen[0].fsPath : null;
    }
    if (message.type === "request" && message.method && REQUESTS.has(message.method)) {
      const client = this.client();
      if (!client) {
        throw new Error("nxwright's language server is not running");
      }
      const appToml = vscode.Uri.joinPath(folder, "app.toml");
      return client.sendRequest(message.method, {
        ...message.params, textDocument: { uri: appToml.toString() },
      });
    }
    throw new Error(`the Fonts panel asks nothing called ${message.type} ${message.method ?? ""}`);
  }
}
