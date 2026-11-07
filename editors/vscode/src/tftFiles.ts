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

// Remembers the project file `file` as nxwright just wrote it, or read it,
// as extract does, so that a later change made elsewhere shows.
export async function rememberProjectFile(context: vscode.ExtensionContext,
                                          file: string): Promise<void> {
  const hash = await hashOf(file);
  if (hash !== undefined) {
    await context.workspaceState.update(hashKey(file), hash);
  }
}

// Returns whether nxwright may replace the project file `file`. It may when
// the file does not exist, when nxwright has not written it before, or when
// it is still as nxwright last wrote or read it. Otherwise it was changed
// elsewhere, as in the Nextion Editor, and the user chooses: replace it,
// extract it first, which runs Extract and returns false, or cancel.
export async function projectFileMayBeReplaced(context: vscode.ExtensionContext,
                                               file: string): Promise<boolean> {
  const remembered = context.workspaceState.get<string>(hashKey(file));
  const hash = await hashOf(file);
  if (remembered === undefined || hash === undefined || hash === remembered) {
    return true;
  }
  const answer = await vscode.window.showWarningMessage(
    `${path.basename(file)} was changed outside nxwright since nxwright last wrote it.`,
    { modal: true, detail: "Replacing it will lose those changes. Extract brings them into " +
      "the source folder first." },
    "Replace", "Extract First");
  if (answer === "Extract First") {
    await vscode.commands.executeCommand("nxwright.extract");
  }
  return answer === "Replace";
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
