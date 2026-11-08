// The Media section's right-click menu on a resource: Delete, Replace, and
// Rename (package.json's view/item/context, by the item's contextValue,
// mediaResource.<list>). Each runs an nxwright subcommand, `remove`,
// `replace`, or `rename`, after asking the questions that mediaEditing.ts
// builds. A font is replaced from the Fonts panel instead (fontPanel.ts).
// Each action refuses to run while a file of the folder has unsaved
// changes, because the subcommand could rewrite that file.
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { CurrentProject } from "./currentProject";
import { FontPanels } from "./fontPanel";
import { animationArguments, MediaQuestions, MediaSettings, pictureArguments, soundArguments,
         videoArguments } from "./mediaCommands";
import { deleteDialog, isPlaceholder, newNameCheck, RemovalReport, replaceArguments }
  from "./mediaEditing";
import { MediaEntry } from "./mediaView";
import { runJson } from "./tftRun";
import { refusedForUnsaved } from "./unsavedChanges";
import { errorText } from "./userMessages";

// Each list of app.toml, by the word nxwright's commands name its kind with.
const KINDS: Record<string, string> = {
  pictures: "picture", fonts: "font", animations: "animation", videos: "video", sounds: "sound",
};

// What the actions need of the extension.
export interface MediaMeans {
  project: CurrentProject;
  fontPanels: FontPanels;
  client: () => LanguageClient | undefined;
  // The command that runs nxwright, or undefined, having said why.
  command: () => Promise<string[] | undefined>;
  // Runs an nxwright subcommand in a terminal, resolving to its exit code.
  runSubcommand: (name: string, args: string[]) => Promise<number | undefined>;
  questions: MediaQuestions;
  workingFolder: () => string | undefined;
}

export class MediaActions {
  constructor(private readonly means: MediaMeans) {}

  register(): vscode.Disposable[] {
    return [
      vscode.commands.registerCommand("nxwright.deleteResource",
                                      (entry: MediaEntry) => this.delete(entry)),
      vscode.commands.registerCommand("nxwright.replaceResource",
                                      (entry: MediaEntry) => this.replace(entry)),
      vscode.commands.registerCommand("nxwright.renameResource",
                                      (entry: MediaEntry) => this.rename(entry)),
    ];
  }

  // Deletes the resource of `entry`, in the way the user picks in the
  // dialog that mediaEditing.ts builds. `rewroteNumbers` is true once
  // Replace Numbers with Names has run for it, and the dialog then no
  // longer offers that button.
  private async delete(entry: MediaEntry, rewroteNumbers = false): Promise<void> {
    const target = this.target(entry, "deleting a resource");
    if (!target) {
      return;
    }
    const { folder, kind, name } = target;
    const report = await this.json<RemovalReport>(
      `checking where the ${kind} ${name} is used...`,
      `the report on deleting the ${kind} ${name}`,
      ["remove", folder.fsPath, kind, name, "--report"]);
    if (!report) {
      return;
    }
    const dialog = deleteDialog(report, rewroteNumbers);
    const show = dialog.error ? vscode.window.showErrorMessage : vscode.window.showWarningMessage;
    const chosen = await show(dialog.message, { modal: true, detail: dialog.detail || undefined },
                              ...dialog.buttons.map((button) => button.label));
    const action = dialog.buttons.find((button) => button.label === chosen)?.action;
    if (action === "showUses") {
      await this.showUses(folder, entry.list, report);
    } else if (action === "keepIds") {
      await this.means.runSubcommand("remove", ["remove", folder.fsPath, kind, name, "--keep-ids"]);
    } else if (action === "shift" || action === "delete") {
      await this.means.runSubcommand("remove", ["remove", folder.fsPath, kind, name]);
    } else if (action === "namesForNumbers" && await this.writeNumbersAsNames(folder, report)) {
      await this.delete(entry, true);
    }
  }

  // Opens VS Code's References view on the report's uses, by name and by
  // number, anchored at the resource's name in its list in app.toml.
  private async showUses(folder: vscode.Uri, list: string, report: RemovalReport):
      Promise<void> {
    const appToml = vscode.Uri.joinPath(folder, "app.toml");
    const text = new TextDecoder().decode(await vscode.workspace.fs.readFile(appToml));
    const lines = text.split("\n");
    // A picture and a font may share a name: the name is sought in its own list.
    const listStart = Math.max(0, lines.findIndex((each) => each.startsWith(`${list} =`)));
    const line = Math.max(0, lines.findIndex((each, index) => index >= listStart &&
                                             each.includes(`"${report.name}"`)));
    const anchor = new vscode.Position(line, Math.max(0, lines[line].indexOf(report.name)));
    const locations = report.uses.map((use) => new vscode.Location(
      vscode.Uri.joinPath(folder, use.path), new vscode.Range(use.line - 1, 0, use.line - 1, 0)));
    await vscode.commands.executeCommand("editor.action.showReferences", appToml, anchor,
                                         locations);
  }

  // Writes as names the numbers that give the IDs after the report's
  // resource, as far as the language server can, and saves the files it
  // changed. Returns whether the edit was applied.
  private async writeNumbersAsNames(folder: vscode.Uri, report: RemovalReport):
      Promise<boolean> {
    const client = this.means.client();
    if (!client) {
      void vscode.window.showErrorMessage("nxwright: the language server is not running.");
      return false;
    }
    const ids = report.later.map((_, index) => report.id + 1 + index);
    let edit: vscode.WorkspaceEdit | undefined;
    try {
      const reply = await client.sendRequest("nxwright/resourceNumbersAsNames",
                                             { folder: folder.fsPath, kind: report.kind, ids });
      edit = await client.protocol2CodeConverter.asWorkspaceEdit(
        reply as Parameters<typeof client.protocol2CodeConverter.asWorkspaceEdit>[0]);
    } catch (error) {
      void vscode.window.showErrorMessage(
        `nxwright: could not write the numbers as names: ${errorText(error)}`);
      return false;
    }
    if (!edit || !await vscode.workspace.applyEdit(edit)) {
      void vscode.window.showErrorMessage("nxwright: the numbers could not be written as names.");
      return false;
    }
    for (const [uri] of edit.entries()) {
      const document = vscode.workspace.textDocuments.find(
        (open) => open.uri.toString() === uri.toString());
      await document?.save();
    }
    return true;
  }

  // Replaces the resource of `entry`. It asks the questions of adding its
  // kind, filled in with the resource's settings, and a new name when the
  // resource is a placeholder. A font is replaced from the Fonts panel
  // instead.
  private async replace(entry: MediaEntry): Promise<void> {
    const target = this.target(entry, "replacing a resource");
    if (!target) {
      return;
    }
    const { folder, kind, name } = target;
    if (kind === "font") {
      await this.means.fontPanels.show(folder, true, undefined, name);
      return;
    }
    let newName: string | undefined;
    if (isPlaceholder(name)) {
      newName = await vscode.window.showInputBox({
        title: `nxwright: replace the ${kind} ${name}`,
        prompt: `Enter a name for the new ${kind}.`,
        validateInput: (text) => newNameCheck(text, name, this.names(entry.list)),
      });
      if (newName === undefined) {
        return;
      }
    }
    const settings = await this.json<MediaSettings>(
      `reading the settings of the ${kind} ${name}...`,
      `the settings of the ${kind} ${name}`,
      ["replace", folder.fsPath, kind, name, "--settings"]);
    if (!settings) {
      return;
    }
    // The file dialogs' button reads Use, since the files replace a resource.
    const questions: MediaQuestions = {
      ...this.means.questions,
      files: async (title, filters, many) =>
        (await vscode.window.showOpenDialog({ title, filters, canSelectMany: many,
                                              openLabel: "Use" }))?.map((file) => file.fsPath),
    };
    const added = kind === "picture" ? await pictureArguments(folder.fsPath, questions, true)
      : kind === "animation" ? await animationArguments(folder.fsPath, questions, settings)
      : kind === "video" ? await videoArguments(folder.fsPath, questions, settings)
      : await soundArguments(folder.fsPath, questions);
    if (added) {
      await this.means.runSubcommand("replace", replaceArguments(added, name, newName));
    }
  }

  // Renames the resource of `entry`, as a name asked for and checked.
  private async rename(entry: MediaEntry): Promise<void> {
    const target = this.target(entry, "renaming a resource");
    if (!target) {
      return;
    }
    const { folder, kind, name } = target;
    const newName = await vscode.window.showInputBox({
      title: `nxwright: rename the ${kind} ${name}, and each use of its name`,
      value: name,
      validateInput: (text) => newNameCheck(text, name, this.names(entry.list)),
    });
    if (newName !== undefined) {
      await this.means.runSubcommand("rename", ["rename", folder.fsPath, kind, name, newName]);
    }
  }

  // Returns the current project's folder, and the kind and name of the
  // resource of `entry`; or undefined, having said why, when there is no
  // project, or a file of it has unsaved changes `doing` could rewrite.
  private target(entry: MediaEntry, doing: string):
      { folder: vscode.Uri; kind: string; name: string } | undefined {
    const folder = this.means.project.folder;
    if (!folder || entry?.name === undefined || !(entry.list in KINDS)
        || refusedForUnsaved(folder, doing)) {
      return undefined;
    }
    return { folder, kind: KINDS[entry.list], name: entry.name };
  }

  // The names app.toml's list `list` holds.
  private names(list: string): string[] {
    return this.means.project.info?.resources?.[list] ?? [];
  }

  // Runs nxwright with `args`, and returns the JSON object it prints.
  // nxwright can take a while on a large project, so a notification shows
  // `doing` while it runs, with a button to cancel. Returns undefined if the
  // user cancels. If nxwright fails, shows an error that starts
  // "could not get `what`", and returns undefined.
  private async json<T>(doing: string, what: string, args: string[]): Promise<T | undefined> {
    const command = await this.means.command();
    if (command === undefined) {
      return undefined;
    }
    const ran = await vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification, cancellable: true,
      title: `nxwright: ${doing}`,
    }, (_, token) => {
      const stop = new AbortController();
      token.onCancellationRequested(() => stop.abort());
      return runJson(command, args, { cwd: this.means.workingFolder(), signal: stop.signal });
    });
    if (ran.stopped) {
      return undefined;
    }
    if (ran.code !== 0 || ran.events.length === 0) {
      void vscode.window.showErrorMessage(
        `nxwright: could not get ${what}: ${ran.errors.trim() || "nxwright printed nothing"}`);
      return undefined;
    }
    return ran.events[0] as unknown as T;
  }
}
