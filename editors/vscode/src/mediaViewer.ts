// The media viewers: read-only custom editors that play an animation
// (.gmov), a video (.video), or a sound of a source folder (sounds/*.wav),
// each the default for its files. An animation or a video plays its frames
// at their timing (media/media-player.mjs), which the language server reads
// (nxwright/mediaFrames), again when its files change on disk; an
// animation in GmovMaker's form plays the screen's form beside it. A sound
// plays in the webview's own audio player.
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { errorText } from "./userMessages";
import { webviewPage } from "./webviewPage";

// The viewers, as package.json declares them.
const FRAMES_VIEWERS = ["nxwright.animationViewer", "nxwright.videoViewer"];
const SOUND_VIEWER = "nxwright.soundViewer";

export class MediaViewers {
  constructor(private readonly context: vscode.ExtensionContext,
              private readonly client: () => LanguageClient | undefined) {}

  register(): vscode.Disposable[] {
    const open = (uri: vscode.Uri): vscode.CustomDocument => ({ uri, dispose: () => undefined });
    return [
      ...FRAMES_VIEWERS.map((viewType) => vscode.window.registerCustomEditorProvider(viewType, {
        openCustomDocument: open,
        resolveCustomEditor: (document, panel) => this.showFrames(document.uri, panel),
      })),
      vscode.window.registerCustomEditorProvider(SOUND_VIEWER, {
        openCustomDocument: open,
        resolveCustomEditor: (document, panel) => this.showSound(document.uri, panel),
      }),
    ];
  }

  // A player of an animation's or a video's frames.
  private showFrames(file: vscode.Uri, panel: vscode.WebviewPanel): void {
    panel.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media")],
    };
    panel.webview.html = webviewPage(panel.webview, this.context.extensionUri, {
      script: "media-player.mjs", styles: STYLES, allowImages: true, body: FRAMES_BODY });
    const send = async () => {
      const client = this.client();
      if (!client) {
        void panel.webview.postMessage({
          type: "frames", error: "the language server is not running" });
        return;
      }
      try {
        const frames = await client.sendRequest("nxwright/mediaFrames", { file: file.fsPath });
        void panel.webview.postMessage({ type: "frames", frames });
      } catch (error) {
        void panel.webview.postMessage({ type: "frames", error: errorText(error) });
      }
    };
    panel.webview.onDidReceiveMessage((message) => {
      if (message.type === "ready") {
        void send();
      }
    });
    // The file written again, as by GmovMaker, or, for an animation in
    // GmovMaker's form, the screen's form beside it, which holds its frames.
    const name = file.path.split("/").pop() ?? "";
    const lower = name.toLowerCase();
    const watched = lower.endsWith(".gmov") && !lower.endsWith(".screen.gmov")
      ? `{${name},${name.slice(0, -".gmov".length)}.screen.gmov}` : name;
    const watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(vscode.Uri.joinPath(file, ".."), watched));
    watcher.onDidChange(() => void send());
    watcher.onDidCreate(() => void send());
    panel.onDidDispose(() => watcher.dispose());
  }

  // The webview's own audio player, playing the sound file from its folder.
  private showSound(file: vscode.Uri, panel: vscode.WebviewPanel): void {
    const folder = vscode.Uri.joinPath(file, "..");
    panel.webview.options = { localResourceRoots: [folder] };
    const source = panel.webview.asWebviewUri(file).toString();
    const name = file.path.split("/").pop() ?? "";
    panel.webview.html = webviewPage(panel.webview, this.context.extensionUri, {
      styles: STYLES, allowMedia: true,
      body: `<h1>${escaped(name)}</h1>
<audio controls src="${escaped(source)}"></audio>`,
    });
  }
}

// `text` with the characters HTML gives a meaning to written as entities.
function escaped(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const FRAMES_BODY = `
<p id="facts" class="hint"></p>
<canvas id="screen" hidden></canvas>
<div id="controls" hidden>
  <button id="play"></button>
  <input id="frame" type="range" min="0" value="0" title="The frame shown">
  <span id="position" class="hint"></span>
</div>`;

// The styles of the viewers: the frames at their own size, their pixels
// sharp, on the screen's black.
const STYLES = `
  body { padding: 8px 16px 16px; }
  h1 { font-size: 1.4em; font-weight: normal; }
  canvas { display: block; margin: 8px 0; background: #000; image-rendering: pixelated; }
  canvas[hidden], #controls[hidden] { display: none; }
  #controls { display: flex; align-items: center; gap: 8px; }
  #frame { flex: 1; max-width: 30em; }
  button {
    min-width: 5em; padding: 4px 10px; border: none; cursor: pointer; font: inherit;
    color: var(--vscode-button-foreground); background: var(--vscode-button-background);
  }
  button:hover { background: var(--vscode-button-hoverBackground); }
  .hint { color: var(--vscode-descriptionForeground); }
  .problem { color: var(--vscode-errorForeground); }`;
