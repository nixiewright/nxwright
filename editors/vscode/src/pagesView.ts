// The Pages section of nxwright's side bar. It lists the current project's
// pages (currentProject.ts) in ID order, each with its ID, and selects the
// page the side bar shows (pages.ts). Choosing a page opens its page file in
// the preview, the default editor for page files. The section's header
// buttons, New page and Add a keyboard page, are declared in package.json.
//
// Each page's right-click menu offers to lock or unlock the page, and has
// the Go to Event submenu for the page's own events. To show a padlock on
// locked pages and pick each menu's items, the section asks the language
// server which pages are locked (nxwright/pageLocks) and what events each
// page has (nxwright/pageEvents). It asks when the project changes, and
// again shortly after one of the project's page files or .nx files changes,
// saved or not.
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { isInside } from "./activeFile";
import { CurrentProject, NO_PROJECT_NOTE } from "./currentProject";
import { ObjectEvent } from "./eventMenu";
import { pageFileStem } from "./pageFileNames";
import { pageItemLook } from "./pageLocking";
import { Pages, tomlOf } from "./pages";

// How long, in milliseconds, files must stop changing before the section
// asks again which pages are locked and what events they have.
const PAGES_PAUSE = 300;

// A page of the current project: its name, its ID, and its page file, which
// the commands of its right-click menu take.
export interface ProjectPage {
  name: string;
  id: number;
  toml?: vscode.Uri;
}

export class PagesView implements vscode.TreeDataProvider<ProjectPage> {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;
  private tree: vscode.TreeView<ProjectPage> | undefined;
  // The current project's locked pages, by name.
  private locked: ReadonlySet<string> = new Set();
  // The events of each page of the current project, by name.
  private events: Record<string, ObjectEvent[]> = {};
  private askTimer: ReturnType<typeof setTimeout> | undefined;
  // Numbers the requests about the pages, so that only the answer to the
  // latest one is shown.
  private asked = 0;

  constructor(private readonly project: CurrentProject, private readonly pages: Pages,
              private readonly client: () => LanguageClient | undefined) {}

  register(): vscode.Disposable[] {
    this.tree = vscode.window.createTreeView("nxwright.pages", { treeDataProvider: this });
    this.tree.message = NO_PROJECT_NOTE;
    return [
      this.tree,
      this.changed,
      this.project.onDidChange(() => {
        this.tree!.message = this.project.folder ? undefined : NO_PROJECT_NOTE;
        this.changed.fire();
        this.showShownPage();
        void this.askAboutPages();
      }),
      { dispose: () => clearTimeout(this.askTimer) },
      this.pages.onDidChangePage(() => this.showShownPage()),
      this.tree.onDidChangeVisibility(() => this.showShownPage()),
    ];
  }

  getChildren(element?: ProjectPage): ProjectPage[] {
    if (element) {
      return [];
    }
    return (this.project.info?.pages ?? []).map((name, id) =>
      ({ name, id, toml: this.pageFile(name) }));
  }

  getParent(): undefined {
    return undefined;
  }

  getTreeItem(page: ProjectPage): vscode.TreeItem {
    const item = new vscode.TreeItem(page.name);
    // Identifies the item by the page's name, which no two pages of a project
    // share, so that the shown page can be found again after the list changes.
    item.id = page.name;
    item.description = String(page.id);
    const look = pageItemLook(page.name, this.locked, this.events[page.name]);
    item.contextValue = look.contextValue;
    if (look.padlock) {
      item.iconPath = new vscode.ThemeIcon("lock");
    }
    const toml = this.pageFile(page.name);
    if (toml) {
      item.resourceUri = toml;
      item.command = { command: "vscode.open", title: "Open the page", arguments: [toml] };
    }
    return item;
  }

  // Called when a file changes, on disk or in an editor. If it is a page file
  // or a .nx file of the current project, asks the server again about the
  // pages, after a pause. Editing a page file may lock or unlock its page,
  // and editing a .nx file may add or remove the code of an event.
  fileChanged(uri: vscode.Uri): void {
    const folder = this.project.folder;
    if (!folder) {
      return;
    }
    const pageFile = uri.fsPath.endsWith(".page.toml") &&
      isInside(uri, vscode.Uri.joinPath(folder, "pages"));
    const code = uri.fsPath.endsWith(".nx") && isInside(uri, folder);
    if (!pageFile && !code) {
      return;
    }
    clearTimeout(this.askTimer);
    this.askTimer = setTimeout(() => void this.askAboutPages(), PAGES_PAUSE);
  }

  // Asks the server which pages of the current project are locked and what
  // events each one has, and shows the answers. Without a server or an
  // answer, no page shows as locked or offers the Go to Event submenu.
  private async askAboutPages(): Promise<void> {
    const asked = ++this.asked;
    const folder = this.project.folder;
    const client = this.client();
    const ask = <T>(method: string): Promise<T | undefined> => folder && client
      ? client.sendRequest<T>(method, { folder: folder.fsPath }).then(
        (answer) => answer, () => undefined)
      : Promise.resolve(undefined);
    const [locks, events] = await Promise.all([
      ask<{ locked: string[] }>("nxwright/pageLocks"),
      ask<{ events: Record<string, ObjectEvent[]> }>("nxwright/pageEvents"),
    ]);
    // A later request, such as one for another project, may have been sent
    // while the server answered this one. Only the latest answer is shown.
    if (asked !== this.asked) {
      return;
    }
    this.locked = new Set(locks?.locked ?? []);
    this.events = events?.events ?? {};
    this.changed.fire();
  }

  // The page file of a page of the current project.
  private pageFile(name: string): vscode.Uri | undefined {
    const folder = this.project.folder;
    return folder && vscode.Uri.joinPath(folder, "pages", `${pageFileStem(name)}.page.toml`);
  }

  // Selects the page the side bar shows, when it is one of the current project's.
  private showShownPage(): void {
    const shown = this.pages.shown;
    if (!this.tree?.visible || !shown) {
      return;
    }
    const page = this.getChildren().find(
      (entry) => this.pageFile(entry.name)?.toString() === tomlOf(shown).toString());
    if (page) {
      void this.tree.reveal(page, { select: true, focus: false });
    }
  }
}
