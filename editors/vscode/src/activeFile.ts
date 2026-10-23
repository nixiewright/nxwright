// The active file, and its source folder, for the current project
// (currentProject.ts), the page preview's commands, and the status bar's
// limits. A page preview is a custom editor, which leaves no text editor
// active while it is in front, so the active file is its page file then.
import * as path from "path";
import * as vscode from "vscode";
import { PREVIEW_VIEW_TYPE } from "./pages";

// Returns the page file of the page preview in front, or undefined when
// the active tab is no page preview.
export function activePreview(): vscode.Uri | undefined {
  const active = vscode.window.tabGroups.activeTabGroup.activeTab?.input;
  return active instanceof vscode.TabInputCustom && active.viewType === PREVIEW_VIEW_TYPE
    ? active.uri : undefined;
}

// Returns the active file: the page file of the active page preview, or the
// active text editor's file; undefined when neither is in front, or it is
// not a file on disk.
export function activeFile(): vscode.Uri | undefined {
  const uri = activePreview() ?? vscode.window.activeTextEditor?.document.uri;
  return uri?.scheme === "file" ? uri : undefined;
}

// Returns the source folder of a file: the nearest folder above it holding
// an app.toml, or undefined.
export async function sourceFolderOf(file: vscode.Uri | undefined):
    Promise<vscode.Uri | undefined> {
  if (!file || file.scheme !== "file") {
    return undefined;
  }
  let folder = path.dirname(file.fsPath);
  for (;;) {
    try {
      await vscode.workspace.fs.stat(vscode.Uri.file(path.join(folder, "app.toml")));
      return vscode.Uri.file(folder);
    } catch {
      const parent = path.dirname(folder);
      if (parent === folder) {
        return undefined;
      }
      folder = parent;
    }
  }
}

// Whether `file` lies inside `folder`, at any depth.
export function isInside(file: vscode.Uri, folder: vscode.Uri): boolean {
  const relative = path.relative(folder.fsPath, file.fsPath);
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}
