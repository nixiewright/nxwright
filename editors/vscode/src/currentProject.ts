// The current project: the source folder the side bar's sections show, and
// the commands that work on a project's folder act on. It is the last
// project worked in, the source folder of the last active file that was in
// one, a page preview's included, kept while the active tab is no project's
// file, such as the Fonts panel. Without one, it is the workspace's only
// source folder, or one the user picks (projectChoice.ts).
//
// What the language server says of it (nxwright/project) is kept beside it,
// and sets the context keys the sections' header buttons read.
import * as path from "path";
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { activeFile, sourceFolderOf } from "./activeFile";
import { currentProjectOf, ProjectTracker } from "./projectChoice";
import { appName } from "./projectName";

// What a command says when it needs a project and none is current, and what a
// view of the project shows then.
export const NO_PROJECT_ERROR =
  "nxwright: open a file of a project, or choose one in the Project section, first.";
export const NO_PROJECT_NOTE = "Open a file of a project, or choose one in the Project section.";

// What the language server says of a project (nxwright/project): its
// formats; and in the current format, the rest, the screen's settings when
// app.toml gives them.
export interface ProjectInfo {
  format: number;
  currentFormat: number;
  name?: string;
  language?: string;
  pages?: string[];
  resources?: Record<string, string[]>;
  screen?: string;
  size?: string;
  rotation?: number;
  encoding?: string;
}

export class CurrentProject {
  // The last project worked in or picked, by its folder.
  private remembered: vscode.Uri | undefined;
  // The workspace's source folders, as found by their app.toml.
  private found: vscode.Uri[] = [];
  private readonly changed = new vscode.EventEmitter<void>();
  // The current project, made current at once, and the server's answer
  // about it, which follows (projectChoice.ts).
  private readonly tracker: ProjectTracker<ProjectInfo>;
  // How many times the project was chosen: only the latest choice counts, as
  // choosing waits on the file system.
  private chosen = 0;

  // The project, or what the server says of it, changed.
  readonly onDidChange = this.changed.event;

  constructor(private readonly client: () => LanguageClient | undefined) {
    this.tracker = new ProjectTracker((folder) => this.ask(folder), () => this.trackerChanged());
  }

  // The current project's folder, or undefined.
  get folder(): vscode.Uri | undefined {
    const folder = this.tracker.folder;
    return folder === undefined ? undefined : vscode.Uri.file(folder);
  }

  // What the server says of the current project, or null before it answers,
  // or for a folder whose format cannot be read.
  get info(): ProjectInfo | null {
    return this.tracker.info;
  }

  // The name of the app of the source folder `folder`, as the server gives
  // it, or else the folder's name (projectName.appName).
  async nameOf(folder: vscode.Uri): Promise<string> {
    const info = this.folder?.fsPath === folder.fsPath && this.info
      ? this.info : await this.ask(folder.fsPath);
    return appName(info, folder.fsPath);
  }

  // The workspace's source folders.
  get folders(): readonly vscode.Uri[] {
    return this.found;
  }

  register(): vscode.Disposable[] {
    const appFiles = vscode.workspace.createFileSystemWatcher("**/app.toml");
    const search = () => void this.searchFolders();
    void this.searchFolders();
    void this.activeChanged();
    return [
      this.changed,
      appFiles,
      appFiles.onDidCreate(search),
      appFiles.onDidDelete(search),
      vscode.window.onDidChangeActiveTextEditor(() => void this.activeChanged()),
      // A preview becoming active, which is no text editor.
      vscode.window.tabGroups.onDidChangeTabs(() => void this.activeChanged()),
      vscode.workspace.onDidChangeWorkspaceFolders(() => {
        // A project the workspace no longer holds is current no more.
        if (this.remembered && !vscode.workspace.getWorkspaceFolder(this.remembered)) {
          this.remembered = undefined;
        }
        search();
      }),
      vscode.commands.registerCommand("nxwright.chooseProject", () => this.choose()),
    ];
  }

  // Asks the server again what it says of the project: after it starts, and
  // after each check, as app.toml may have changed.
  serverChanged(): void {
    void this.workOut();
  }

  // "Choose the project": lists the workspace's source folders, and makes
  // the one picked current.
  private async choose(): Promise<void> {
    await this.searchFolders();
    if (this.found.length === 0) {
      void vscode.window.showInformationMessage(
        "nxwright: the workspace holds no source folder. Create a new project, or import one.");
      return;
    }
    const names = await Promise.all(this.found.map((folder) => this.nameOf(folder)));
    const picked = await vscode.window.showQuickPick(
      this.found.map((folder, index) => ({
        label: names[index],
        description: vscode.workspace.asRelativePath(folder),
        folder,
      })),
      { title: "nxwright: the project the side bar shows" });
    if (picked) {
      this.remembered = picked.folder;
      await this.workOut();
    }
  }

  // The active file's project, if it is in one, becomes current.
  private async activeChanged(): Promise<void> {
    const folder = await sourceFolderOf(activeFile());
    if (folder && folder.toString() !== this.remembered?.toString()) {
      this.remembered = folder;
      await this.workOut();
    }
  }

  private async searchFolders(): Promise<void> {
    const files = await vscode.workspace.findFiles("**/app.toml", "**/node_modules/**");
    this.found = files.map((file) => vscode.Uri.file(path.dirname(file.fsPath)))
      .sort((a, b) => a.fsPath.localeCompare(b.fsPath));
    await this.workOut();
  }

  // Works out the current project, and asks the server about it again.
  private async workOut(): Promise<void> {
    const chosen = ++this.chosen;
    const remembered = this.remembered;
    const exists = remembered !== undefined && await fileExists(
      vscode.Uri.joinPath(remembered, "app.toml"));
    if (chosen !== this.chosen) {
      return;
    }
    await this.tracker.update(currentProjectOf(remembered?.fsPath, exists,
                                               this.found.map((folder) => folder.fsPath)));
  }

  // What the server says of the project `folder`, or null without a server.
  private async ask(folder: string): Promise<ProjectInfo | null> {
    const client = this.client();
    return client
      ? client.sendRequest<ProjectInfo | null>("nxwright/project", { folder }).catch(() => null)
      : null;
  }

  // The project or the server's answer changed: the context keys the
  // sections' header buttons read follow, and the sections are told.
  private trackerChanged(): void {
    const info = this.tracker.info;
    void vscode.commands.executeCommand("setContext", "nxwright.hasProject",
                                        this.tracker.folder !== undefined);
    void vscode.commands.executeCommand("setContext", "nxwright.projectOutdated",
                                        info !== null && info.format < info.currentFormat);
    void vscode.commands.executeCommand("setContext", "nxwright.projectLanguage",
                                        info?.language ?? "");
    this.changed.fire();
  }
}

// The key under which the workspace's state keeps the project file (.HMI)
// chosen for a source folder, which Build writes and Extract reads.
export function projectFileKey(folder: vscode.Uri): string {
  return `nxwright.projectFile:${folder.fsPath}`;
}

async function fileExists(file: vscode.Uri): Promise<boolean> {
  try {
    await vscode.workspace.fs.stat(file);
    return true;
  } catch {
    return false;
  }
}
