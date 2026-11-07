// What the extension remembers of a source folder's files, in the
// workspace's state, beside its project file (currentProject.ts,
// projectFileKey): the TFT file Compile writes, whether Compile also writes
// the project file, and the hash of each project file nxwright last wrote,
// so that one the Nextion Editor changed since is not replaced without
// asking.
import { createHash } from "crypto";
import { promises as fs } from "fs";
import * as path from "path";
import * as vscode from "vscode";
import {
  EXTRACT_NEW_FOLDER, SHOW_CHANGES, changedProjectFileDetail, showChangesArguments,
} from "./projectFileText";

// The TFT file chosen for a source folder.
export function tftFileKey(folder: vscode.Uri): string {
  return `nxwright.tftFile:${folder.fsPath}`;
}

function linkKey(folder: vscode.Uri): string {
  return `nxwright.projectFileLinked:${folder.fsPath}`;
}

function hashKey(projectFile: string): string {
  return `nxwright.projectFileHash:${projectFile}`;
}

// Whether Compile also writes the source folder's project file: yes until
// the user turns the link off, so that the two files stay in step.
export function projectFileLinked(context: vscode.ExtensionContext, folder: vscode.Uri): boolean {
  return context.workspaceState.get<boolean>(linkKey(folder)) ?? true;
}

export async function setProjectFileLinked(context: vscode.ExtensionContext, folder: vscode.Uri,
                                           linked: boolean): Promise<void> {
  await context.workspaceState.update(linkKey(folder), linked);
}

// Returns the SHA-256 hash of `file`, or undefined when it cannot be read,
// as when it does not exist.
async function hashOf(file: string): Promise<string | undefined> {
  try {
    return createHash("sha256").update(await fs.readFile(file)).digest("hex");
  } catch {
    return undefined;
  }
}

// Remembers the project file `file` as nxwright just wrote it, so that a later
// change made elsewhere can be detected.
export async function rememberProjectFile(context: vscode.ExtensionContext,
                                          file: string): Promise<void> {
  const hash = await hashOf(file);
  if (hash !== undefined) {
    await context.workspaceState.update(hashKey(file), hash);
  }
}

// Returns whether nxwright may replace `file`, the project file of a source
// folder. nxwright may replace the file when it does not exist, when nxwright has
// not written it before, or when it is still as nxwright last wrote it. Otherwise
// it was changed elsewhere, such as in the Nextion Editor, and the user can replace
// it, cancel, see what changed since it was built from the source folder `folder`, or
// extract it into a new folder. Only replacing it returns true. The warning blocks
// the window, so it does not ask again after showing the changes: the user reads them,
// then builds or compiles again.
export async function projectFileMayBeReplaced(context: vscode.ExtensionContext, file: string,
                                               folder: string): Promise<boolean> {
  const remembered = context.workspaceState.get<string>(hashKey(file));
  const hash = await hashOf(file);
  if (remembered === undefined || hash === undefined || hash === remembered) {
    return true;
  }
  const answer = await vscode.window.showWarningMessage(
    `${path.basename(file)} was changed outside nxwright since nxwright last wrote it.`,
    { modal: true, detail: changedProjectFileDetail(backupsAreOn()) },
    "Replace", SHOW_CHANGES, EXTRACT_NEW_FOLDER);
  if (answer === SHOW_CHANGES) {
    await vscode.commands.executeCommand("nxwright.showChanges",
                                         showChangesArguments(folder, file, locksAreOn()));
  } else if (answer === EXTRACT_NEW_FOLDER) {
    await vscode.commands.executeCommand("nxwright.extract", { project: file });
  }
  return answer === "Replace";
}

function backupsAreOn(): boolean {
  return vscode.workspace.getConfiguration("nxwright").get<boolean>("backups", true);
}

function locksAreOn(): boolean {
  return vscode.workspace.getConfiguration("nxwright").get<boolean>("lockPages", true);
}

// Returns the options of a build or a compile that the user's settings decide.
export function settingsArguments(): string[] {
  return [...(backupsAreOn() ? [] : ["--no-backup"]), ...(locksAreOn() ? [] : ["--no-lock"])];
}

// The screen Upload sends to: its serial port, the rate of the upload, and
// the model it last answered as, once one did. One for the workspace, as a
// screen is not a source folder's.
export interface ScreenChoice {
  port: string;
  rate: number;
  model?: string;
}

const SCREEN_KEY = "nxwright.screen";

// The screen chosen for the workspace, or undefined before one is.
export function chosenScreen(context: vscode.ExtensionContext): ScreenChoice | undefined {
  return context.workspaceState.get<ScreenChoice>(SCREEN_KEY);
}

// Keeps `screen` as the workspace's, in place of the earlier one. It asks
// nothing: the commands that ask are tftCommands.ts's.
export async function saveScreen(context: vscode.ExtensionContext,
                                 screen: ScreenChoice): Promise<void> {
  await context.workspaceState.update(SCREEN_KEY, screen);
}
