// The page preview: an editor of a page's .page.toml file, VS Code's kind of
// custom text editor, which draws the page in a webview, redraws as the
// folder's files change, and edits the page (media/preview.mjs says how).
// Being an editor of the page file, it shares that file's undo and redo
// with the file's text editor. The language server computes each drawing
// (nxwright/pageDrawing); the webview only paints and reports what the
// mouse and the keys do. The selected object's properties show in
// nxwright's side bar (sideBar.ts). Whether the previews write the
// components' names on the page is one choice for all of them, remembered
// between sessions (PreviewNames).
import * as path from "path";
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { activePreview, isInside } from "./activeFile";
import { PageEditing } from "./pageEditing";
import { isPageFile, Pages, PREVIEW_VIEW_TYPE, tomlOf } from "./pages";
import { PictureFile, pictureSources, webviewPage, ZOOM_STYLES } from "./webviewPage";

// The server's reply to nxwright/pageDrawing: a drawing with the files of
// its pictures, or why the page's files do not read.
interface PageDrawing {
  page: string;
  error?: string;
  pictureFiles?: Record<string, PictureFile>;
  [key: string]: unknown;
}

// The types of the files a drawing reads; the page's code plays no part.
export const DRAWN_FILE_TYPES = ["toml", "png", "jpg", "jpeg", "bmp", "gif", "zi"];
const DRAWN_FILE = new RegExp(`\\.(${DRAWN_FILE_TYPES.join("|")})$`);

// What a preview needs of the extension.
interface PreviewServices {
  context: vscode.ExtensionContext;
  client: () => LanguageClient | undefined;
  pages: Pages;
  editing: PageEditing;
}

// The key under which the extension remembers whether names are shown.
const NAMES_SHOWN = "nxwright.previewNames";

// Whether the previews write each component's name on the page; off at
// first, since the preview shows the page as the screen does.
class PreviewNames {
  private readonly changed = new vscode.EventEmitter<boolean>();
  readonly onDidChange = this.changed.event;

  constructor(private readonly memento: vscode.Memento) {}

  get shown(): boolean {
    return this.memento.get<boolean>(NAMES_SHOWN, false);
  }

  async show(shown: boolean): Promise<void> {
    await this.memento.update(NAMES_SHOWN, shown);
    this.changed.fire(shown);
  }
}

// The commands of the preview's right-click menu that arrange the selected
// components, by the name the webview knows each by (media/preview.mjs's
// arrange): aligning them with the anchor, the component selected first,
// giving them its size, and spacing them evenly.
const ARRANGEMENTS: Record<string, string> = {
  "nxwright.alignLeft": "left",
  "nxwright.alignRight": "right",
  "nxwright.alignTop": "top",
  "nxwright.alignBottom": "bottom",
  "nxwright.alignCentresAcross": "centreAcross",
  "nxwright.alignCentresDown": "centreDown",
  "nxwright.sameWidth": "sameWidth",
  "nxwright.sameHeight": "sameHeight",
  "nxwright.sameSize": "sameSize",
  "nxwright.spaceAcross": "spaceAcross",
  "nxwright.spaceDown": "spaceDown",
};

// What the preview's right-click menu passes its commands (media/preview.mjs).
interface PreviewMenuContext {
  page?: string;
  components?: string[];
}

// Opens the previews, one per page file, and passes each the events of
// the window that concern it.
export class PagePreviews implements vscode.CustomTextEditorProvider {
  private readonly open = new Set<PagePreview>();
  private readonly names: PreviewNames;

  constructor(private readonly services: PreviewServices) {
    this.names = new PreviewNames(services.context.globalState);
  }

  register(): vscode.Disposable[] {
    const { editing } = this.services;
    return [
      vscode.window.registerCustomEditorProvider(PREVIEW_VIEW_TYPE, this, {
        supportsMultipleEditorsPerDocument: false,
      }),
      // The webview knows where the selected components are: it arranges them.
      ...Object.entries(ARRANGEMENTS).map(([command, how]) =>
        vscode.commands.registerCommand(command, (context: PreviewMenuContext) =>
          this.previewOf(context)?.post({ type: "arrange", how }))),
      ...[["nxwright.bringToFront", "front"], ["nxwright.bringForward", "forward"],
          ["nxwright.sendBackward", "backward"], ["nxwright.sendToBack", "back"]].map(
        ([command, direction]) => vscode.commands.registerCommand(
          command, async (context: PreviewMenuContext) => {
            if (context.page && context.components?.length) {
              await editing.reorderComponents(vscode.Uri.parse(context.page), context.components,
                                              direction);
            }
          })),
    ];
  }

  // The open preview the right-click menu opened in.
  private previewOf(context: PreviewMenuContext): PagePreview | undefined {
    return [...this.open].find((preview) => preview.toml.toString() === context.page);
  }

  resolveCustomTextEditor(document: vscode.TextDocument, panel: vscode.WebviewPanel): void {
    const preview = new PagePreview(this.services, this.names, document, panel);
    this.open.add(preview);
    panel.onDidDispose(() => this.open.delete(preview));
  }

  // Opens beside the active editor the preview of its page, from the page's
  // .page.toml or .nx file; shows its tab when it is open already.
  async show(): Promise<void> {
    if (activePreview()) {
      return;
    }
    const uri = vscode.window.activeTextEditor?.document.uri;
    if (!uri || !isPageFile(uri)) {
      void vscode.window.showErrorMessage("nxwright: open a page's .page.toml or .nx file first.");
      return;
    }
    const toml = tomlOf(uri);
    const shown = [...this.open].find((preview) => preview.toml.toString() === toml.toString());
    if (shown) {
      shown.reveal();
      return;
    }
    await vscode.commands.executeCommand("vscode.openWith", toml, PREVIEW_VIEW_TYPE, {
      viewColumn: vscode.ViewColumn.Beside,
      preserveFocus: true,
    });
  }

  // Opens the page file of the active preview as text, beside it.
  async showText(): Promise<void> {
    const page = activePreview();
    if (!page) {
      void vscode.window.showErrorMessage("nxwright: open a page's preview first.");
      return;
    }
    await vscode.commands.executeCommand("vscode.openWith", page, "default",
                                         vscode.ViewColumn.Beside);
  }

  changed(uri: vscode.Uri): void {
    for (const preview of this.open) {
      preview.changed(uri);
    }
  }

  // The language server started, or started again. Previews VS Code
  // restored with the window asked for their drawings before it ran.
  serverStarted(): void {
    for (const preview of this.open) {
      preview.redraw();
    }
  }
}

// The preview of one page file, in its tab.
class PagePreview {
  readonly toml: vscode.Uri;
  private refreshing: ReturnType<typeof setTimeout> | undefined;
  // How many drawings were asked for: only the latest reply counts.
  private asked = 0;
  private queue: Promise<void> = Promise.resolve();
  private disposed = false;

  constructor(
    private readonly services: PreviewServices,
    private readonly names: PreviewNames,
    document: vscode.TextDocument,
    private readonly panel: vscode.WebviewPanel,
  ) {
    this.toml = document.uri;
    const { pages } = services;
    panel.webview.options = { enableScripts: true, localResourceRoots: this.resourceRoots() };
    panel.webview.html = this.html(panel.webview);
    // One message at a time: each edit is made from the text the one before it left.
    const received = panel.webview.onDidReceiveMessage((message) => {
      this.queue = this.queue.then(() => this.received(message)).catch(() => undefined);
    });
    // The page of the active preview shows in nxwright's side bar.
    const viewState = panel.onDidChangeViewState(() => {
      if (panel.active) {
        pages.show(this.toml);
      }
    });
    if (panel.active) {
      pages.show(this.toml);
    }
    const selection = pages.onDidChangeSelection((toml) => {
      if (toml.toString() === this.toml.toString()) {
        void panel.webview.postMessage({ type: "select", name: pages.selected(this.toml) });
      }
    });
    const namesShown = names.onDidChange((shown) => {
      void panel.webview.postMessage({ type: "names", shown });
    });
    panel.onDidDispose(() => {
      this.disposed = true;
      if (this.refreshing) {
        clearTimeout(this.refreshing);
      }
      received.dispose();
      viewState.dispose();
      selection.dispose();
      namesShown.dispose();
    });
  }

  reveal(): void {
    this.panel.reveal(this.panel.viewColumn, true);
  }

  post(message: unknown): void {
    void this.panel.webview.postMessage(message);
  }

  // A hidden preview asks when shown again (see changed).
  redraw(): void {
    if (this.panel.visible) {
      void this.refresh();
    }
  }

  // Redraws after a pause, once files of the page's folder that the drawing
  // reads change: page files, app.toml, pictures, and fonts. A hidden
  // preview waits: its webview starts afresh when shown, and asks then.
  changed(uri: vscode.Uri): void {
    if (this.panel.visible && DRAWN_FILE.test(uri.fsPath) && isInside(uri, this.sourceFolder())) {
      if (this.refreshing) {
        clearTimeout(this.refreshing);
      }
      this.refreshing = setTimeout(() => void this.refresh(), 300);
    }
  }

  private async received(message: { type: string; [key: string]: unknown }): Promise<void> {
    const { pages, editing } = this.services;
    const name = message.name as string;
    const names = (message.names ?? []) as string[];
    if (message.type === "ready") {
      // The webview starts afresh each time its tab shows again. It names
      // its page file to the commands of its right-click menu.
      void this.panel.webview.postMessage({ type: "page", uri: this.toml.toString() });
      void this.panel.webview.postMessage({ type: "names", shown: this.names.shown });
      void this.panel.webview.postMessage({ type: "select", name: pages.selected(this.toml) });
      await this.refresh();
    } else if (message.type === "select") {
      pages.select(this.toml, name);
    } else if (message.type === "place") {
      // A move the page file refused: the drawing goes back to what the file says.
      if (!(await editing.placeComponents(this.toml, message.places as Record<string, unknown>))) {
        await this.refresh();
      }
    } else if (message.type === "openDefaultEvent") {
      await editing.openEvent(this.toml, name);
    } else if (message.type === "goToDefinition") {
      await editing.goToDefinition(this.toml,
                                   typeof message.name === "string" ? message.name : undefined);
    } else if (message.type === "delete") {
      await editing.deleteComponents(this.toml, names);
    } else if (message.type === "copy") {
      await editing.copyComponents(this.toml, names);
    } else if (message.type === "cut") {
      await editing.cutComponents(this.toml, names);
    } else if (message.type === "paste" || message.type === "duplicate") {
      const pasted = message.type === "paste" ? await editing.pasteComponents(this.toml)
        : await editing.duplicateComponents(this.toml, names);
      if (pasted.length > 0) {
        pages.select(this.toml, pasted[0]);
      }
    } else if (message.type === "showNames") {
      await this.names.show(message.shown === true);
    }
  }

  private async refresh(): Promise<void> {
    const client = this.services.client();
    if (this.disposed || !client) {
      return;
    }
    const asked = ++this.asked;
    const reply = await client
      .sendRequest<PageDrawing | null>("nxwright/pageDrawing", {
        textDocument: { uri: this.toml.toString() },
      })
      .catch((error): PageDrawing => ({ page: "", error: String(error) }));
    if (asked !== this.asked || this.disposed || !reply) {
      return;
    }
    if (reply.error !== undefined) {
      void this.panel.webview.postMessage({ type: "error", error: reply.error });
      return;
    }
    const { pictureUris, pictureMasks } = pictureSources(this.panel.webview,
                                                         reply.pictureFiles ?? {});
    const grid = vscode.workspace.getConfiguration("nxwright").get<number>("previewGrid") ?? 1;
    void this.panel.webview.postMessage({ type: "drawing", drawing: reply, pictureUris,
                                          pictureMasks, grid });
  }

  // The source folder of the page: two folders above its file.
  private sourceFolder(): vscode.Uri {
    return vscode.Uri.file(path.dirname(path.dirname(this.toml.fsPath)));
  }

  // The webview may load only the extension's own files and the folder's pictures.
  private resourceRoots(): vscode.Uri[] {
    return [
      vscode.Uri.joinPath(this.services.context.extensionUri, "media"),
      vscode.Uri.joinPath(this.sourceFolder(), "pictures"),
    ];
  }

  private html(webview: vscode.Webview): string {
    // Text pictures come as data: URLs.
    return webviewPage(webview, this.services.context.extensionUri, {
      script: "preview.mjs",
      allowImages: true,
      styles: `
  body { padding: 8px; }
  #toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
  #toolbar label { display: flex; align-items: center; gap: 4px; user-select: none; }
  ${ZOOM_STYLES}
  #stage { position: relative; width: fit-content; }
  #page { display: block; background: #404040; outline: none; }
  #page.transparent {
    background: repeating-conic-gradient(#808080 0 25%, #b0b0b0 0 50%) 0 0 / 16px 16px;
  }
  #overlay { position: absolute; left: 0; top: 0; pointer-events: none; }
  #strip { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
  #strip[hidden] { display: none; }
  .tile {
    padding: 3px 6px; border: 1px solid var(--vscode-widget-border, #808080);
    background: var(--vscode-editorWidget-background); cursor: default; user-select: none;
  }
  .tile .name { padding: 0 1px; }
  .tile .type {
    display: block; margin-top: 2px; font-size: 11px; color: var(--vscode-descriptionForeground);
  }
  .tile.selected { border-color: #3794ff; outline: 1px solid #3794ff; }
  .tile.idle { opacity: 0.5; }
  #notes { color: var(--vscode-editorWarning-foreground); padding-left: 16px; }`,
      body: `<div id="toolbar"><label><input type="checkbox" id="names"> Names</label>
<span id="zoom" class="zoom"></span></div>
<div id="stage"><canvas id="page" tabindex="0"></canvas><canvas id="overlay"></canvas></div>
<div id="strip" hidden></div>
<ul id="notes"></ul>`,
    });
  }
}
