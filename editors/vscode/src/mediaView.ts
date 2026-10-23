// The Media section of nxwright's side bar: the current project's resources
// (currentProject.ts), a collapsible group per kind, each listing its names
// in ID order, with the ID. A group's buttons, shown on hover, are
// package.json's (view/item/context, inline), told apart by the group's
// contextValue. Choosing a resource opens its file: a font's in the font
// viewer (fontViewer.ts), an animation's, a video's, or a sound's in its
// media viewer (mediaViewer.ts), a picture as VS Code shows pictures.
import * as path from "path";
import * as vscode from "vscode";
import { CurrentProject, NO_PROJECT_NOTE } from "./currentProject";

// The groups, in order: their list in app.toml, as the server names it, and
// their label.
const GROUPS = [
  { list: "fonts", label: "Fonts" },
  { list: "pictures", label: "Pictures" },
  { list: "animations", label: "Animations" },
  { list: "videos", label: "Videos" },
  { list: "sounds", label: "Sounds" },
];

// The suffix of the file of each kind of media the media viewers open: an
// animation's GmovMaker file, which plays the screen's form beside it.
const MEDIA_FILES: Record<string, string> = {
  animations: ".gmov", videos: ".video", sounds: ".wav",
};

// A group, or a resource of one: its list, and for a resource, its name and ID.
interface MediaEntry {
  list: string;
  name?: string;
  id?: number;
}

export class MediaView implements vscode.TreeDataProvider<MediaEntry> {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;

  constructor(private readonly project: CurrentProject) {}

  register(): vscode.Disposable[] {
    const tree = vscode.window.createTreeView("nxwright.media", { treeDataProvider: this });
    tree.message = NO_PROJECT_NOTE;
    return [
      tree,
      this.changed,
      this.project.onDidChange(() => {
        tree.message = this.project.folder ? undefined : NO_PROJECT_NOTE;
        this.changed.fire();
      }),
      vscode.commands.registerCommand("nxwright.openPicture",
                                      (name: string) => this.openPicture(name)),
    ];
  }

  getChildren(element?: MediaEntry): MediaEntry[] {
    const resources = this.project.info?.resources;
    if (!this.project.folder || !resources) {
      return [];
    }
    if (!element) {
      return GROUPS.map((group) => ({ list: group.list }));
    }
    if (element.name !== undefined) {
      return [];
    }
    return (resources[element.list] ?? []).map((name, id) => ({ list: element.list, name, id }));
  }

  getTreeItem(entry: MediaEntry): vscode.TreeItem {
    if (entry.name === undefined) {
      const group = GROUPS.find((candidate) => candidate.list === entry.list)!;
      const item = new vscode.TreeItem(group.label, vscode.TreeItemCollapsibleState.Collapsed);
      item.id = entry.list;
      item.description = String(this.project.info?.resources?.[entry.list]?.length ?? 0);
      item.contextValue = `mediaGroup.${entry.list}`;
      return item;
    }
    const item = new vscode.TreeItem(entry.name);
    item.id = `${entry.list}/${entry.name}`;
    item.description = String(entry.id);
    const folder = this.project.folder;
    if (entry.list === "fonts" && folder) {
      item.command = { command: "vscode.open", title: "Open the font",
                       arguments: [vscode.Uri.joinPath(folder, "fonts", `${entry.name}.zi`)] };
    } else if (MEDIA_FILES[entry.list] && folder) {
      item.command = { command: "vscode.open", title: "Play it", arguments: [
        vscode.Uri.joinPath(folder, entry.list, `${entry.name}${MEDIA_FILES[entry.list]}`)] };
    } else if (entry.list === "pictures") {
      item.command = { command: "nxwright.openPicture", title: "Open the picture",
                       arguments: [entry.name] };
    }
    return item;
  }

  // Opens the file of the picture `name` of the current project: the one
  // file in pictures/ named after it, whatever its suffix.
  private async openPicture(name: string): Promise<void> {
    const folder = this.project.folder;
    if (!folder) {
      return;
    }
    // A name such as icons/arrow is the file arrow.png in pictures/icons.
    const parts = name.split("/");
    const stem = parts.pop()!;
    const pictures = vscode.Uri.joinPath(folder, "pictures", ...parts);
    const entries = await Promise.resolve(vscode.workspace.fs.readDirectory(pictures))
      .catch((): [string, vscode.FileType][] => []);
    const files = entries
      .filter(([file, type]) => type === vscode.FileType.File && path.parse(file).name === stem)
      .map(([file]) => vscode.Uri.joinPath(pictures, file));
    if (files.length === 1) {
      await vscode.commands.executeCommand("vscode.open", files[0]);
    } else {
      void vscode.window.showErrorMessage(
        `nxwright: the picture ${name} has ${files.length === 0 ? "no file" : "two files"} in ` +
          "the pictures folder.");
    }
  }
}
