// The font viewer: a read-only custom editor of font files (.zi), the
// default for them. It shows a sample of a text drawn in the font, which a
// box gives, and the font's height, encoding, smoothing, characters, and
// rotation, as the Fonts panel lists a font; for a font of a source folder,
// "Create a variation of this font" opens the folder's Fonts panel at its
// form filled from it. The language server reads the font and draws the
// sample (nxwright/fontFile); the page draws what it sends
// (media/font-viewer.mjs), and asks again when the file changes on disk or
// the theme changes.
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { FontPanels } from "./fontPanel";
import { errorText } from "./userMessages";
import { webviewPage } from "./webviewPage";

// The font viewer, as package.json declares it.
const FONT_VIEWER = "nxwright.fontViewer";

export class FontViewer implements vscode.CustomReadonlyEditorProvider {
  constructor(private readonly context: vscode.ExtensionContext,
              private readonly client: () => LanguageClient | undefined,
              private readonly fontPanels: FontPanels) {}

  register(): vscode.Disposable {
    return vscode.window.registerCustomEditorProvider(FONT_VIEWER, this);
  }

  openCustomDocument(uri: vscode.Uri): vscode.CustomDocument {
    return { uri, dispose: () => undefined };
  }

  resolveCustomEditor(document: vscode.CustomDocument, panel: vscode.WebviewPanel): void {
    panel.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media")],
    };
    panel.webview.html = webviewPage(panel.webview, this.context.extensionUri, {
      script: "font-viewer.mjs", styles: STYLES, allowImages: true, body: BODY });
    // The font's source folder, once the server has said which.
    let folder: string | undefined;
    // A font file written again, as when the Fonts panel adds a font of its name.
    const watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(vscode.Uri.joinPath(document.uri, ".."),
                                 document.uri.path.split("/").pop()!));
    watcher.onDidChange(() => void panel.webview.postMessage({ type: "fileChanged" }));
    watcher.onDidCreate(() => void panel.webview.postMessage({ type: "fileChanged" }));
    panel.onDidDispose(() => watcher.dispose());
    panel.webview.onDidReceiveMessage(async (message) => {
      if (message.type === "details") {
        const client = this.client();
        if (!client) {
          void panel.webview.postMessage({
            type: "details", asked: message.asked, error: "the language server is not running" });
          return;
        }
        try {
          const details = await client.sendRequest<{ folder: string | null }>(
            "nxwright/fontFile",
            { file: document.uri.fsPath, text: message.text, colour: message.colour });
          folder = details.folder ?? undefined;
          void panel.webview.postMessage({ type: "details", asked: message.asked, details });
        } catch (error) {
          void panel.webview.postMessage({ type: "details", asked: message.asked,
                                           error: errorText(error) });
        }
      } else if (message.type === "variation" && folder !== undefined) {
        void this.fontPanels.show(vscode.Uri.file(folder), true, message.name);
      }
    });
  }
}

const BODY = `
<h1 id="name"></h1>
<p id="facts" class="hint"></p>
<label for="text">Sample text</label>
<input id="text" autocomplete="off">
<div id="sample"></div>
<div id="variation" hidden>
  <button id="vary"></button>
</div>`;

// The styles of the viewer: the sample on a band of the editor's background.
const STYLES = `
  body { padding: 0 16px 16px; }
  h1 { font-size: 1.4em; font-weight: normal; margin-bottom: 4px; }
  label { display: block; margin-top: 12px; }
  input, button { font: inherit; }
  input {
    width: 100%; max-width: 40em; box-sizing: border-box;
    color: var(--vscode-input-foreground); background: var(--vscode-input-background);
    border: 1px solid var(--vscode-input-border, transparent);
  }
  #sample { margin: 12px 0; padding: 8px; overflow: auto;
            border: 1px solid var(--vscode-panel-border, transparent); }
  #sample img { image-rendering: pixelated; }
  button {
    padding: 4px 10px; border: none; cursor: pointer;
    color: var(--vscode-button-foreground); background: var(--vscode-button-background);
  }
  button:hover { background: var(--vscode-button-hoverBackground); }
  .hint { color: var(--vscode-descriptionForeground); }
  .problem { color: var(--vscode-errorForeground); }`;
