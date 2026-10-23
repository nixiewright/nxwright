// "Show the Editor code": a read-only document beside a .nx file, holding the
// Editor code it compiles to, from the server's nxwright/editorCode request.
// The lines compiled from the cursor's line are highlighted.
import * as path from "path";
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { activeFile } from "./activeFile";
import { isPageFile, nxOf } from "./pages";

const EDITOR_CODE_SCHEME = "nxwright-editor-code";

// The server's reply to nxwright/editorCode.
interface EditorCode {
  page: string;
  text?: string;
  sourceLines?: number[];
  error?: string;
}

export class EditorCodeViews implements vscode.TextDocumentContentProvider {
  private readonly changed = new vscode.EventEmitter<vscode.Uri>();
  readonly onDidChange = this.changed.event;
  // By the source file's URI: the view's text, and the source line of each
  // of its lines, or -1.
  private readonly shown = new Map<string, { text: string; sourceLines: number[] }>();
  // The same, from the last time the code built.
  private readonly lastBuilt = new Map<string, { text: string; sourceLines: number[] }>();
  private readonly highlight = vscode.window.createTextEditorDecorationType({
    backgroundColor: new vscode.ThemeColor("editor.rangeHighlightBackground"),
    isWholeLine: true,
  });
  private refreshing: ReturnType<typeof setTimeout> | undefined;
  // By the source file's URI: how many requests were sent for it.
  private readonly asked = new Map<string, number>();

  constructor(private readonly getClient: () => LanguageClient | undefined) {}

  // Registers the command, the views' documents, and what keeps them current:
  // a change of a source file shown, the cursor's moves, and a view closed.
  register(context: vscode.ExtensionContext): void {
    context.subscriptions.push(
      vscode.commands.registerCommand("nxwright.showEditorCode", () => this.showActive()),
      vscode.workspace.registerTextDocumentContentProvider(EDITOR_CODE_SCHEME, this),
      vscode.workspace.onDidChangeTextDocument((event) => {
        if (event.document.uri.scheme === "file" && this.isShown(event.document.uri)) {
          this.refreshSoon();
        }
      }),
      vscode.window.onDidChangeTextEditorSelection((event) => this.showCursor(event.textEditor)),
      vscode.workspace.onDidCloseTextDocument((document) => this.close(document.uri)),
    );
  }

  provideTextDocumentContent(view: vscode.Uri): string {
    return this.shown.get(view.query)?.text ?? "";
  }

  // Shows beside the active file its Editor code: a .nx file's, or, for a
  // page's preview or .page.toml file, that of the page's own .nx file.
  private async showActive(): Promise<void> {
    const file = activeFile();
    const source = file && isPageFile(file) ? nxOf(file) : file;
    if (source?.scheme !== "file" || !source.fsPath.endsWith(".nx")) {
      void vscode.window.showErrorMessage(
        "nxwright: open a .nx file of a source folder, or a page, first.");
      return;
    }
    try {
      await vscode.workspace.fs.stat(source);
    } catch {
      void vscode.window.showErrorMessage(
        `nxwright: the page has no ${path.basename(source.fsPath)} file, so no code to show.`);
      return;
    }
    await this.open(source);
  }

  private async open(source: vscode.Uri): Promise<void> {
    await this.refresh(source);
    const document = await vscode.workspace.openTextDocument(viewOf(source));
    await vscode.window.showTextDocument(document, {
      viewColumn: vscode.ViewColumn.Beside,
      preserveFocus: true,
      preview: false,
    });
    const editor = vscode.window.activeTextEditor;
    if (editor?.document.uri.toString() === source.toString()) {
      this.showCursor(editor);
    }
  }

  // Asks the server again for each view, after the source files change. When
  // the code does not build, the view keeps the last code that did, with a note.
  refreshSoon(): void {
    if (this.refreshing) {
      clearTimeout(this.refreshing);
    }
    this.refreshing = setTimeout(() => {
      for (const source of this.shown.keys()) {
        void this.refresh(vscode.Uri.parse(source));
      }
    }, 500);
  }

  private async refresh(source: vscode.Uri): Promise<void> {
    const key = source.toString();
    // Replies may come back out of order: only the latest request's counts.
    const asked = (this.asked.get(key) ?? 0) + 1;
    this.asked.set(key, asked);
    const client = this.getClient();
    const reply = client
      ? await client
          .sendRequest<EditorCode | null>("nxwright/editorCode", {
            textDocument: { uri: key },
          })
          .catch((error): EditorCode => ({ page: "", error: String(error) }))
      : null;
    if (this.asked.get(key) !== asked) {
      return;
    }
    if (!reply) {
      this.shown.set(key, { text: "// This file is not part of a page's code.\n",
                            sourceLines: [] });
    } else if (reply.error === undefined) {
      const name = path.basename(source.fsPath);
      const title = `// ${name} in strict Nextion syntax, as page ${reply.page} has it.`;
      const built = {
        text: title + "\n" + (reply.text ?? ""),
        sourceLines: [-1, ...(reply.sourceLines ?? [])],
      };
      this.lastBuilt.set(key, built);
      this.shown.set(key, built);
    } else {
      const built = this.lastBuilt.get(key) ?? { text: "", sourceLines: [] };
      const note =
        `// The code does not build: ${reply.error.replace(/\n/g, " ")}\n` +
        "// Below is the last code that did.\n";
      this.shown.set(key, { text: note + built.text, sourceLines: [-1, -1, ...built.sourceLines] });
    }
    this.changed.fire(viewOf(source));
  }

  // Highlights, in the view of the editor's file, the lines compiled from
  // the cursor's line.
  private showCursor(editor: vscode.TextEditor): void {
    const shown = this.shown.get(editor.document.uri.toString());
    const view = vscode.window.visibleTextEditors.find(
      (visible) => visible.document.uri.toString() === viewOf(editor.document.uri).toString(),
    );
    if (!shown || !view) {
      return;
    }
    const line = editor.selection.active.line;
    const ranges = shown.sourceLines
      .map((source, index) => (source === line ? index : -1))
      .filter((index) => index >= 0 && index < view.document.lineCount)
      .map((index) => view.document.lineAt(index).range);
    view.setDecorations(this.highlight, ranges);
    if (ranges.length > 0) {
      view.revealRange(ranges[0], vscode.TextEditorRevealType.InCenterIfOutsideViewport);
    }
  }

  private isShown(source: vscode.Uri): boolean {
    return this.shown.has(source.toString());
  }

  // Forgets a closed view, so that its source is no longer asked about.
  private close(view: vscode.Uri): void {
    if (view.scheme === EDITOR_CODE_SCHEME) {
      this.shown.delete(view.query);
      this.lastBuilt.delete(view.query);
      this.asked.delete(view.query);
    }
  }
}

// The URI of the view of a source file: its path, so that the tab shows its
// name, and the source's URI as the query, so that each source has one view.
function viewOf(source: vscode.Uri): vscode.Uri {
  return vscode.Uri.from({
    scheme: EDITOR_CODE_SCHEME,
    path: source.path + " (strict Nextion syntax)",
    query: source.toString(),
  });
}
