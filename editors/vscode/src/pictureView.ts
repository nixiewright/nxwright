// The picture editor: a custom text editor of a source folder's SVG
// pictures, pictures/**/*.svg, the default for them. It shows the picture as
// nxwright draws it, with the defaults of app.toml's defines, and the editor
// picker switches to the SVG text and back. The language server draws it
// from the files as open in the editor (nxwright/svgPicture), and says which
// files it read: the picture is drawn again when one of them changes,
// unsaved or on disk. The webview page, media/picture-view.mjs, shows what
// this class sends it.
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { errorText } from "./userMessages";
import { webviewPage } from "./webviewPage";

// The picture editor, as package.json declares it.
const PICTURE_VIEW = "nxwright.pictureView";
// How long changes must pause before the picture is drawn again, in ms.
const PAUSE = 250;
// The files a picture may read, and app.toml, whose defines it takes.
const READ_FILES = "**/*.{svg,css,ttf,otf,png,jpg,jpeg,gif,webp,toml}";

// What the language server answers for a picture.
interface Drawn {
  picture?: string;
  width?: number;
  height?: number;
  error?: string;
  files: string[];
}

export class PictureView implements vscode.CustomTextEditorProvider {
  constructor(private readonly context: vscode.ExtensionContext,
              private readonly client: () => LanguageClient | undefined) {}

  register(): vscode.Disposable {
    return vscode.window.registerCustomEditorProvider(PICTURE_VIEW, this);
  }

  resolveCustomTextEditor(document: vscode.TextDocument, panel: vscode.WebviewPanel): void {
    panel.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media")],
    };
    panel.webview.html = webviewPage(panel.webview, this.context.extensionUri, {
      script: "picture-view.mjs", styles: STYLES, allowImages: true, body: BODY });
    // The files the picture read when last drawn, by key, its own at first.
    let files = new Set([fileKey(document.uri)]);
    // How many drawings were asked for. Only the latest answer is shown,
    // because answers to quick edits may arrive out of order.
    let asked = 0;
    let timer: NodeJS.Timeout | undefined;
    const draw = async () => {
      const turn = ++asked;
      const drawn = await this.drawn(document.uri);
      if (turn !== asked) {
        return;
      }
      files = new Set([fileKey(document.uri), ...drawn.files.map((file) =>
        fileKey(vscode.Uri.file(file)))]);
      void panel.webview.postMessage({ type: "drawn", ...drawn });
    };
    const drawSoon = (uri: vscode.Uri) => {
      if (files.has(fileKey(uri))) {
        clearTimeout(timer);
        timer = setTimeout(() => void draw(), PAUSE);
      }
    };
    const folder = vscode.workspace.getWorkspaceFolder(document.uri)?.uri
      ?? vscode.Uri.joinPath(document.uri, "..");
    const watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(folder, READ_FILES));
    const subscriptions = [
      watcher,
      watcher.onDidChange(drawSoon),
      watcher.onDidCreate(drawSoon),
      watcher.onDidDelete(drawSoon),
      vscode.workspace.onDidChangeTextDocument((event) => drawSoon(event.document.uri)),
      panel.webview.onDidReceiveMessage((message) => {
        if (message.type === "ready") {
          void draw();
        }
      }),
    ];
    panel.onDidDispose(() => {
      clearTimeout(timer);
      subscriptions.forEach((subscription) => subscription.dispose());
    });
  }

  // The picture of the SVG file `uri`, as the language server draws it, or
  // why it cannot.
  private async drawn(uri: vscode.Uri): Promise<Drawn> {
    const client = this.client();
    if (!client) {
      return { error: "the language server is not running", files: [] };
    }
    try {
      return await client.sendRequest<Drawn>("nxwright/svgPicture", { file: uri.fsPath });
    } catch (error) {
      return { error: errorText(error), files: [] };
    }
  }
}

// A file's path as compared with others: Windows ignores letter case.
function fileKey(uri: vscode.Uri): string {
  return process.platform === "win32" ? uri.fsPath.toLowerCase() : uri.fsPath;
}

const BODY = `
<p id="facts" class="hint"></p>
<div id="picture"></div>`;

// The picture is shown at its own size, and in a smaller editor it shrinks to
// fit and keeps its shape. VS Code's own styles limit the width and height of
// an image. The page also sets the picture's width and height, and together
// the two would squash it, so these styles set both back to auto.
const STYLES = `
  html, body { height: 100%; }
  body { box-sizing: border-box; margin: 0; padding: 8px 16px 16px;
         display: flex; flex-direction: column; }
  #picture { flex: 1; min-height: 0; }
  #picture img { display: block; box-sizing: border-box; width: auto; height: auto;
                 border: 1px solid var(--vscode-panel-border, transparent); }
  .hint { color: var(--vscode-descriptionForeground); }
  .problem { color: var(--vscode-errorForeground); white-space: pre-wrap; }`;
