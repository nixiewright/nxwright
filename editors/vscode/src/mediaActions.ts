// The Media section's right-click menu on a resource: Delete, Replace, and
// Rename (package.json's view/item/context, by the item's contextValue,
// mediaResource.<list>). Each runs an nxwright subcommand, `remove`,
// `replace`, or `rename`, after asking the questions that mediaEditing.ts
// builds. A font is replaced from the Fonts panel instead (fontPanel.ts).
// The Pages section's Delete Page deletes a page the same way.
// An action passes --checked to its subcommand only if its setting is on:
// nxwright.checks.delete, nxwright.checks.replace, or nxwright.checks.rename.
// Without --checked, the subcommand does not search or build the folder
// first. No action runs while a file of the folder has unsaved changes,
// because the subcommand could rewrite that file.
import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";
import { CurrentProject } from "./currentProject";
import { FontPanels } from "./fontPanel";
import { animationArguments, MediaQuestions, MediaSettings, pictureArguments, soundArguments,
         videoArguments } from "./mediaCommands";
import { DeleteAction, deleteDialog, deleteTarget, DeleteTarget, isPlaceholder, newNameCheck,
         removeArguments, renameArguments, replaceArguments } from "./mediaEditing";
import { MediaEntry } from "./mediaView";
import { runJson } from "./tftRun";
import { refusedForUnsaved } from "./unsavedChanges";
import { errorText } from "./userMessages";

// Each list of app.toml, by the word nxwright's commands name its kind with.
const KINDS: Record<string, string> = {
  pictures: "picture", fonts: "font", animations: "animation", videos: "video", sounds: "sound",
  pages: "page",
};

// What the actions need of the extension.
export interface MediaMeans {
  project: CurrentProject;
  fontPanels: FontPanels;
  client: () => LanguageClient | undefined;
  // The command that runs nxwright, or undefined, having said why.
  command: () => Promise<string[] | undefined>;
  // Runs an nxwright subcommand in a terminal, resolving to its exit code.
  // If `doing` is given, a notification shows that text until the subcommand ends.
  runSubcommand: (name: string, args: string[], doing?: string) => Promise<number | undefined>;
  questions: MediaQuestions;
  workingFolder: () => string | undefined;
}

export class MediaActions {
  constructor(private readonly means: MediaMeans) {}

  register(): vscode.Disposable[] {
    return [
      vscode.commands.registerCommand("nxwright.deleteResource",
                                      (entry: MediaEntry, answer?: DeleteAction) =>
                                        this.delete(entry, answer)),
      vscode.commands.registerCommand("nxwright.replaceResource",
                                      (entry: MediaEntry) => this.replace(entry)),
      vscode.commands.registerCommand("nxwright.renameResource",
                                      (entry: MediaEntry) => this.rename(entry)),
      // The Pages section's item for a page, deleted as an entry of app.toml's
      // `pages`.
      vscode.commands.registerCommand("nxwright.deletePage",
                                      (page: { name: string }, answer?: DeleteAction) =>
                                        this.delete({ list: "pages", name: page.name }, answer)),
    ];
  }

  // Deletes the resource of `entry`, in the way the user chooses when
  // answering the question that mediaEditing.ts builds. The question needs
  // only what the extension already knows about the project, so it shows
  // immediately. If `answer` is one of the question's choices, it is used in
  // place of asking. The extension's tests pass it. `rewroteNumbers` is true
  // once Replace Numbers with Names has run for the resource, and the
  // question no longer offers that button.
  private async delete(entry: MediaEntry, answer?: DeleteAction,
                       rewroteNumbers = false): Promise<void> {
    const target = this.target(entry, "deleting a resource");
    if (!target) {
      return;
    }
    const { folder, kind, name } = target;
    const deleted = deleteTarget(kind, name, this.names(entry.list),
                                 this.means.project.info?.encoding);
    if (!deleted) {
      void vscode.window.showErrorMessage(
        `nxwright: could not delete the ${kind} ${name}: app.toml no longer lists it.`);
      return;
    }
    const dialog = deleteDialog(deleted, rewroteNumbers);
    let action = dialog.buttons.find((button) => button.action === answer)?.action;
    if (action === undefined) {
      const chosen = await vscode.window.showWarningMessage(
        dialog.message, { modal: true, detail: dialog.detail || undefined },
        ...dialog.buttons.map((button) => button.label));
      action = dialog.buttons.find((button) => button.label === chosen)?.action;
    }
    if (action === "namesForNumbers") {
      if (await this.writeNumbersAsNames(folder, deleted)) {
        await this.delete(entry, undefined, true);
      }
    } else if (action !== undefined) {
      const keepIds = action === "keepIds";
      await this.run(keepIds ? `deleting the ${kind} ${name}, and leaving an empty slot...`
                       : `deleting the ${kind} ${name}...`,
                     removeArguments(folder.fsPath, deleted, keepIds, this.checked("delete")));
    }
  }

  // Writes as names the numbers that give the IDs after `deleted`, as far
  // as the language server can, and saves the files it changed. Returns
  // whether the edit was applied.
  private async writeNumbersAsNames(folder: vscode.Uri, deleted: DeleteTarget):
      Promise<boolean> {
    const client = this.means.client();
    if (!client) {
      void vscode.window.showErrorMessage("nxwright: the language server is not running.");
      return false;
    }
    const ids = deleted.later.map((_, index) => deleted.id + 1 + index);
    return vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification,
      title: "nxwright: replacing numbers with names...",
    }, async () => {
      let edit: vscode.WorkspaceEdit | undefined;
      try {
        const reply = await client.sendRequest("nxwright/resourceNumbersAsNames",
                                               { folder: folder.fsPath, kind: deleted.kind, ids });
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
    });
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
      await this.run(`replacing the ${kind} ${name}...`,
                     replaceArguments(added, name, newName, this.checked("replace")));
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
      await this.run(`renaming the ${kind} ${name} to ${newName}...`,
                     renameArguments(folder.fsPath, kind, name, newName,
                                     this.checked("rename")));
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

  // Returns whether the setting nxwright.checks.<action> is on. When it is,
  // the action passes --checked to its subcommand.
  private checked(action: "delete" | "replace" | "rename"): boolean {
    return vscode.workspace.getConfiguration("nxwright").get<boolean>(`checks.${action}`, false);
  }

  // The names in app.toml's list `list`, as the extension last read them.
  private names(list: string): string[] {
    const info = this.means.project.info;
    return (list === "pages" ? info?.pages : info?.resources?.[list]) ?? [];
  }

  // Runs `nxwright <args>` in a terminal, for a subcommand that changes the
  // folder. A notification shows `doing` until the subcommand ends.
  private async run(doing: string, args: string[]): Promise<void> {
    await this.means.runSubcommand(args[0], args, doing);
  }

  // Runs nxwright with `args`, for a subcommand that only reads the folder,
  // and returns the JSON object it prints. nxwright can take a while on a
  // large project, so a notification shows `doing` while it runs. The
  // notification has a Cancel button, because stopping nxwright cannot leave
  // the folder half changed. Returns undefined if the user cancels, or if
  // nxwright fails. A failure also shows an error that starts
  // "could not get `what`".
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
