// The Pages section of nxwright's side bar: the current project's pages
// (currentProject.ts), in ID order, each with its ID. Choosing one opens its
// page file, which opens in the preview, as VS Code's default for page
// files. The page the side bar shows (pages.ts) is selected. The section's
// header buttons, New page and Add a keyboard page, are package.json's.
import * as vscode from "vscode";
import { CurrentProject, NO_PROJECT_NOTE } from "./currentProject";
import { Pages, tomlOf } from "./pages";

// A page of the current project: its name and ID.
interface ProjectPage {
  name: string;
  id: number;
}

export class PagesView implements vscode.TreeDataProvider<ProjectPage> {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;
  private tree: vscode.TreeView<ProjectPage> | undefined;

  constructor(private readonly project: CurrentProject, private readonly pages: Pages) {}

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
      }),
      this.pages.onDidChangePage(() => this.showShownPage()),
      this.tree.onDidChangeVisibility(() => this.showShownPage()),
    ];
  }

  getChildren(element?: ProjectPage): ProjectPage[] {
    if (element) {
      return [];
    }
    return (this.project.info?.pages ?? []).map((name, id) => ({ name, id }));
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
    const toml = this.pageFile(page.name);
    if (toml) {
      item.resourceUri = toml;
      item.command = { command: "vscode.open", title: "Open the page", arguments: [toml] };
    }
    return item;
  }

  // The page file of a page of the current project.
  private pageFile(name: string): vscode.Uri | undefined {
    const folder = this.project.folder;
    return folder && vscode.Uri.joinPath(folder, "pages", `${name}.page.toml`);
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
