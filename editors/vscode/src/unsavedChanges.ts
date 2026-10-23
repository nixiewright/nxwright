// Changes not saved in an editor, which an action rewriting a project's files
// on disk would lose: the action looks for them first, and refuses while
// there are any, saying in its own words what to save.
import * as path from "path";
import * as vscode from "vscode";
import { isInside } from "./activeFile";

// Returns the files of `folder` open with unsaved changes.
export function unsavedFilesIn(folder: vscode.Uri): vscode.TextDocument[] {
  return vscode.workspace.textDocuments.filter(
    (document) => document.isDirty && isInside(document.uri, folder),
  );
}

// Says so, and returns true, when a file of `folder` has unsaved changes,
// which `doing`, such as "extracting", would lose by rewriting the folder.
export function refusedForUnsaved(folder: vscode.Uri, doing: string): boolean {
  const unsaved = unsavedFilesIn(folder);
  if (unsaved.length > 0) {
    void vscode.window.showErrorMessage(
      `nxwright: save or revert the changes to ${unsaved.length} file(s) of ` +
        `${folder.fsPath} first; ${doing} rewrites them.`,
    );
  }
  return unsaved.length > 0;
}

// Says so, and returns true, when the folder's app.toml has unsaved changes,
// which `what`, rewriting app.toml, would lose.
export function appTomlUnsaved(folder: vscode.Uri, what: string): boolean {
  const appToml = vscode.Uri.joinPath(folder, "app.toml");
  if (vscode.workspace.textDocuments.some((document) => document.isDirty &&
      path.relative(appToml.fsPath, document.uri.fsPath) === "")) {
    void vscode.window.showErrorMessage(
      `nxwright: save or revert the changes to ${appToml.fsPath} first; ${what} rewrites it.`,
    );
    return true;
  }
  return false;
}
