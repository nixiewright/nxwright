// The page nxwright's side bar shows, its objects, and the object selected
// on each page. The page previews, the side bar's sections, and the text
// editors of the page files share them: a selection made in one shows in
// the others.
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";

// The custom editor's id of the page preview, as package.json declares it.
export const PREVIEW_VIEW_TYPE = "nxwright.pagePreview";

// A page's own files: pages/<name>.page.toml and pages/<name>.nx.
const PAGE_FILE = /[\\/]pages[\\/][^\\/]+\.(page\.toml|nx)$/;

export function isPageFile(uri: vscode.Uri): boolean {
  return uri.scheme === "file" && PAGE_FILE.test(uri.fsPath);
}

// The .page.toml file of a page's .page.toml or .nx file.
export function tomlOf(pageFile: vscode.Uri): vscode.Uri {
  return vscode.Uri.file(pageFile.fsPath.replace(/\.nx$/, ".page.toml"));
}

// The .nx file of a page's .page.toml or .nx file.
export function nxOf(pageFile: vscode.Uri): vscode.Uri {
  return vscode.Uri.file(pageFile.fsPath.replace(/\.page\.toml$/, ".nx"));
}

// An object of a page, as the server's nxwright/pageObjects lists it.
export interface PageObject {
  name: string;
  type: string;
  // The lines of its table in the page file.
  firstLine: number;
  lastLine: number;
}

export class Pages {
  // The .page.toml file of the page shown.
  private shownToml: vscode.Uri | undefined;
  private shownObjects: PageObject[] = [];
  // By page file: the name of the object selected.
  private readonly selections = new Map<string, string>();
  private readonly pageChanged = new vscode.EventEmitter<void>();
  private readonly selectionChanged = new vscode.EventEmitter<vscode.Uri>();
  private refreshing: ReturnType<typeof setTimeout> | undefined;
  // How many lists of objects were asked for: only the latest reply counts.
  private asked = 0;

  // The page shown changed, or its objects did.
  readonly onDidChangePage = this.pageChanged.event;
  // The selection of a page changed: its .page.toml file.
  readonly onDidChangeSelection = this.selectionChanged.event;

  constructor(private readonly client: () => LanguageClient | undefined) {}

  get shown(): vscode.Uri | undefined {
    return this.shownToml;
  }

  get objects(): readonly PageObject[] {
    return this.shownObjects;
  }

  // An editor of a page's file became active: its page shows.
  show(pageFile: vscode.Uri): void {
    const toml = tomlOf(pageFile);
    if (toml.toString() !== this.shownToml?.toString()) {
      this.shownToml = toml;
      this.shownObjects = [];
      this.pageChanged.fire();
      void this.readObjects();
    }
  }

  // Tabs opened or closed: once no tab holds the shown page's files, its
  // preview included, the page is no longer shown.
  tabsChanged(): void {
    const shown = this.shownToml;
    if (!shown) {
      return;
    }
    const files = [shown.toString(),
                   shown.with({ path: shown.path.replace(/\.page\.toml$/, ".nx") }).toString()];
    const held = vscode.window.tabGroups.all.flatMap((group) => group.tabs).some((tab) =>
      (tab.input instanceof vscode.TabInputText || tab.input instanceof vscode.TabInputCustom) &&
      files.includes(tab.input.uri.toString()));
    if (!held) {
      this.shownToml = undefined;
      this.shownObjects = [];
      this.pageChanged.fire();
    }
  }

  selected(toml: vscode.Uri): string | undefined {
    return this.selections.get(toml.toString());
  }

  select(toml: vscode.Uri, name: string | undefined): void {
    const key = toml.toString();
    if (this.selections.get(key) === name) {
      return;
    }
    if (name === undefined) {
      this.selections.delete(key);
    } else {
      this.selections.set(key, name);
    }
    this.selectionChanged.fire(toml);
  }

  // Selects the object whose table holds the cursor of the shown page's .page.toml file.
  cursorMoved(editor: vscode.TextEditor): void {
    if (editor.document.uri.toString() !== this.shownToml?.toString()) {
      return;
    }
    const line = editor.selection.active.line;
    const found = this.shownObjects.find((entry) =>
      entry.firstLine <= line && line <= entry.lastLine);
    if (found) {
      this.select(this.shownToml, found.name);
    }
  }

  // Lists the objects again after a pause, once the shown page's file changes.
  changed(uri: vscode.Uri): void {
    if (uri.toString() === this.shownToml?.toString()) {
      // A list asked for before the change no longer counts.
      this.asked++;
      if (this.refreshing) {
        clearTimeout(this.refreshing);
      }
      this.refreshing = setTimeout(() => void this.readObjects(), 300);
    }
  }

  // The language server started, or started again.
  serverStarted(): void {
    void this.readObjects();
  }

  private async readObjects(): Promise<void> {
    const client = this.client();
    const toml = this.shownToml;
    if (!client || !toml) {
      return;
    }
    const asked = ++this.asked;
    const reply = await client
      .sendRequest<{ objects: PageObject[] } | null>("nxwright/pageObjects", {
        textDocument: { uri: toml.toString() },
      })
      .catch(() => null);
    // Without a reply, such as while the server restarts, the list stays.
    if (asked !== this.asked || toml.toString() !== this.shownToml?.toString() || !reply) {
      return;
    }
    this.shownObjects = reply.objects;
    // An object renamed or removed in the page file is no longer selected.
    const selected = this.selected(toml);
    if (selected && !this.shownObjects.some((entry) => entry.name === selected)) {
      this.select(toml, undefined);
    }
    this.pageChanged.fire();
  }
}
