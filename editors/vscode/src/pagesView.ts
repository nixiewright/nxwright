// The Pages section of nxwright's side bar: the current project's pages
// (currentProject.ts), in ID order, each with its ID. Choosing one opens its
// page file, which opens in the preview, as VS Code's default for page
// files. The page the side bar shows (pages.ts) is selected. The section's
// header buttons, New page and Add a keyboard page, are package.json's.
//
// A locked page shows a padlock, and its right-click menu offers Unlock
// page. An unlocked page's menu offers Lock page and Lock page with password. The section asks
// the server which pages are locked (nxwright/pageLocks) when the project
// changes, and again shortly after one of its page files changes, saved or
// not.
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { CurrentProject, NO_PROJECT_NOTE } from "./currentProject";
import { pageFileStem } from "./pageFileNames";
import { pageItemLook } from "./pageLocking";
import { Pages, tomlOf } from "./pages";

// How long, in milliseconds, page files must stop changing before the
// section asks which pages are locked again.
const LOCKS_PAUSE = 300;

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
  private locksTimer: ReturnType<typeof setTimeout> | undefined;
  // How many times the section has asked for the locked pages.
  private locksAsked = 0;

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
        void this.askLocks();
      }),
      { dispose: () => clearTimeout(this.locksTimer) },
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
    // By name, which a project's pages never share, so that the shown page
    // is found again after the list changes.
    item.id = page.name;
    item.description = String(page.id);
    const look = pageItemLook(page.name, this.locked);
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
  // of the current project, asks again which pages are locked, after a
  // pause, because the change may lock or unlock its page.
  fileChanged(uri: vscode.Uri): void {
    const folder = this.project.folder;
    if (!folder || !uri.fsPath.endsWith(".page.toml") ||
        !uri.fsPath.startsWith(vscode.Uri.joinPath(folder, "pages").fsPath)) {
      return;
    }
    clearTimeout(this.locksTimer);
    this.locksTimer = setTimeout(() => void this.askLocks(), LOCKS_PAUSE);
  }

  // Asks the server which pages of the current project are locked, and
  // shows them. Without a server or an answer, no page shows as locked.
  private async askLocks(): Promise<void> {
    const asked = ++this.locksAsked;
    const folder = this.project.folder;
    const client = this.client();
    const answer = folder && client
      ? await client.sendRequest<{ locked: string[] }>("nxwright/pageLocks",
                                                        { folder: folder.fsPath })
        .catch(() => undefined)
      : undefined;
    // A later request, such as one for another project, may have been sent
    // while the server answered this one. Only the latest answer is shown.
    if (asked !== this.locksAsked) {
      return;
    }
    this.locked = new Set(answer?.locked ?? []);
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
