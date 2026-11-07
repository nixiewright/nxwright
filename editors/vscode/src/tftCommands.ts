// The commands on TFT files.
//  - Compile TFT, a button of the Project section, compiles the source
//    folder into its TFT file, and also writes its project file while the
//    link is on. When no source on the computer has the firmware, it offers
//    the sources the toolchain takes: a download, a TFT file, or a Nextion
//    Editor folder. Compile a Project File, Compile without the Project File,
//    and choosing the TFT file have no button.
//  - Upload TFT, a button too, compiles, then uploads the TFT file to the
//    screen: it finds the screen, asks the user to confirm, and shows the
//    upload's progress. Upload a TFT File uploads any TFT file, and choosing
//    the screen picks its port among those the toolchain lists, and the
//    upload's rate.
//  - Decompile turns a TFT file back into a new source folder, to recover a
//    project, and asks before writing a folder the round trip did not
//    confirm.
// Each runs its toolchain command with --json where it takes it (tftRun.ts),
// and writes what the toolchain said in the output panel.
import * as path from "path";
import * as vscode from "vscode";
import { projectFileKey } from "./currentProject";
import {
  ScreenChoice, chosenScreen, projectFileLinked, projectFileMayBeReplaced,
  rememberProjectFile, saveScreen, setProjectFileLinked, settingsArguments, tftFileKey,
} from "./tftFiles";
import { JsonEvent, JsonRun, roundTripDifferences, runJson } from "./tftRun";

// What the commands need of the extension.
export interface TftMeans {
  context: vscode.ExtensionContext;
  // The current project's source folder, or undefined, having said so.
  sourceFolder(): Promise<vscode.Uri | undefined>;
  // The command that runs nxwright, or undefined, having said so.
  command(): Promise<string[] | undefined>;
  // The folder the toolchain runs in.
  workingFolder(): string | undefined;
  // The app's name, which a new TFT file is named after.
  appName(folder: vscode.Uri): Promise<string>;
  // Shows that a file chosen for a folder, or the link, changed.
  changed(): void;
}

// What a caller, such as the extension's tests, may give Compile TFT in
// place of the user's answer when the firmware is missing: download it,
// take it from a TFT file or a Nextion Editor folder, or stop.
export type FirmwareAnswer = "download" | "cancel" | { firmware: string } | { editor: string };

// What a caller, such as the extension's tests, may give Upload a TFT File
// and Upload TFT in place of the user's choices: the file, for Upload a TFT
// File, and whether to upload once the screen is found.
export interface UploadAnswers {
  file?: string;
  upload?: boolean;
  firmware?: FirmwareAnswer;
}

// What a caller may give Decompile in place of the user's choices: the TFT
// file, the folder to write, whether to write a folder the round trip did
// not confirm, and whether to open the folder once written.
export interface DecompileAnswers {
  file?: string;
  folder?: string;
  writeAnyway?: boolean;
  open?: boolean;
}

// The rates an upload may take, as the toolchain's upload takes them
// (nxwright/tft/upload.py, RATES), the default first.
const UPLOAD_RATES = [115200, 921600, 512000, 256000, 250000, 230400, 57600, 38400, 31250,
                      19200, 9600, 4800, 2400];
const DEFAULT_UPLOAD_RATE = 115200;

// What the toolchain's compile is given for the firmware, by the answer.
function firmwareArguments(answer: Exclude<FirmwareAnswer, "cancel">): string[] {
  if (answer === "download") {
    return ["--download"];
  }
  return "firmware" in answer ? ["--firmware", answer.firmware] : ["--editor", answer.editor];
}

export function registerTftCommands(means: TftMeans): vscode.Disposable[] {
  // Apart from the language server's channel, which is "nxwright".
  const output = vscode.window.createOutputChannel("nxwright TFT files");
  const compiler = new Compiler(means, output);
  return [
    output,
    vscode.commands.registerCommand("nxwright.compile",
      (answer?: FirmwareAnswer) => compiler.compileFolder(true, answer)),
    vscode.commands.registerCommand("nxwright.compileWithoutProjectFile",
      (answer?: FirmwareAnswer) => compiler.compileFolder(false, answer)),
    vscode.commands.registerCommand("nxwright.compileProjectFile",
      () => compiler.compileProjectFile()),
    vscode.commands.registerCommand("nxwright.chooseTftFile",
      (file?: string) => compiler.chooseTftFile(file)),
    vscode.commands.registerCommand("nxwright.toggleProjectFileLink",
      () => compiler.toggleLink()),
    vscode.commands.registerCommand("nxwright.upload",
      (answers?: UploadAnswers) => compiler.uploadFolder(answers)),
    vscode.commands.registerCommand("nxwright.uploadTftFile",
      (answers?: UploadAnswers) => compiler.uploadTftFile(answers)),
    vscode.commands.registerCommand("nxwright.chooseScreen",
      (given?: ScreenChoice) => compiler.chooseScreen(given)),
    vscode.commands.registerCommand("nxwright.decompile",
      (answers?: DecompileAnswers) => compiler.decompile(answers)),
  ];
}

class Compiler {
  constructor(private readonly means: TftMeans, private readonly output: vscode.OutputChannel) {}

  // Compiles the current project's source folder into its TFT file, and,
  // when `withProjectFile` and the link is on, writes its project file too.
  // Returns the compile's exit code, or undefined when it did not run.
  async compileFolder(withProjectFile: boolean,
                      answer?: FirmwareAnswer): Promise<number | undefined> {
    const folder = await this.means.sourceFolder();
    const tft = folder && await this.tftFile(folder);
    if (!folder || !tft) {
      return undefined;
    }
    const context = this.means.context;
    const projectFile = withProjectFile && projectFileLinked(context, folder)
      ? context.workspaceState.get<string>(projectFileKey(folder)) : undefined;
    if (projectFile && !await projectFileMayBeReplaced(context, projectFile, folder.fsPath)) {
      return undefined;
    }
    return this.compile(folder.fsPath, tft, projectFile, answer);
  }

  // Compiles a project file the user picks into a TFT file the user names,
  // remembering neither.
  async compileProjectFile(): Promise<number | undefined> {
    const chosen = await vscode.window.showOpenDialog({
      title: "nxwright: the project file to compile", openLabel: "Compile",
      filters: { "Nextion project": ["HMI"] },
    });
    const project = chosen?.[0];
    if (!project) {
      return undefined;
    }
    const tft = await vscode.window.showSaveDialog({
      title: `nxwright: the TFT file to write from ${path.basename(project.fsPath)}`,
      saveLabel: "Compile", filters: { "TFT file": ["tft"] },
      defaultUri: project.with({ path: project.path.replace(/\.[^./]*$/, "") + ".tft" }),
    });
    return tft ? this.compile(project.fsPath, tft.fsPath) : undefined;
  }

  // Chooses the TFT file of the current project's source folder: `given`,
  // or one the user names, which is remembered. Returns it, or undefined
  // when the user cancelled, which keeps the earlier choice.
  async chooseTftFile(given?: string): Promise<string | undefined> {
    const folder = await this.means.sourceFolder();
    return folder && this.askTftFile(folder, given);
  }

  async toggleLink(): Promise<void> {
    const folder = await this.means.sourceFolder();
    if (folder) {
      const context = this.means.context;
      await setProjectFileLinked(context, folder, !projectFileLinked(context, folder));
      this.means.changed();
    }
  }

  // Compiles the current project's source folder, as Compile TFT does, then
  // uploads its TFT file. Returns the exit code of the step that failed, or
  // of the upload, or undefined when a step did not run.
  async uploadFolder(answers: UploadAnswers = {}): Promise<number | undefined> {
    const compiled = await this.compileFolder(true, answers.firmware);
    const folder = compiled === 0 ? await this.means.sourceFolder() : undefined;
    const tft = folder && this.means.context.workspaceState.get<string>(tftFileKey(folder));
    return tft ? this.upload(tft, answers.upload) : compiled;
  }

  // Uploads a TFT file the user picks, or `answers.file`, without compiling.
  async uploadTftFile(answers: UploadAnswers = {}): Promise<number | undefined> {
    const file = answers.file ?? (await vscode.window.showOpenDialog({
      title: "nxwright: the TFT file to upload", openLabel: "Upload",
      filters: { "TFT file": ["tft"] },
    }))?.[0].fsPath;
    return file ? this.upload(file, answers.upload) : undefined;
  }

  // Chooses the screen: `given`, or a port the user picks among those the
  // toolchain lists, then the upload's rate. Returns the choice, or
  // undefined when the user cancelled, which keeps the earlier choice.
  async chooseScreen(given?: ScreenChoice): Promise<ScreenChoice | undefined> {
    const context = this.means.context;
    let screen = given;
    if (screen === undefined) {
      const port = await this.pickPort();
      const rate = port && await this.pickRate(chosenScreen(context)?.rate);
      screen = port && rate ? { port, rate } : undefined;
    }
    if (screen !== undefined) {
      // The model belongs to the screen on the port: a new port forgets it.
      const earlier = chosenScreen(context);
      const model = earlier?.port === screen.port ? earlier.model : undefined;
      screen = { port: screen.port, rate: screen.rate, ...(model ? { model } : {}) };
      await saveScreen(context, screen);
      this.means.changed();
    }
    return screen;
  }

  // Turns a TFT file the user picks into a new source folder the user picks.
  // Returns the exit code, or undefined when the decompile did not run.
  async decompile(answers: DecompileAnswers = {}): Promise<number | undefined> {
    const file = answers.file ?? (await vscode.window.showOpenDialog({
      title: "nxwright: the TFT file to decompile", openLabel: "Decompile",
      filters: { "TFT file": ["tft"] },
    }))?.[0].fsPath;
    const folder = file && (answers.folder ?? (await vscode.window.showOpenDialog({
      title: "nxwright: a new or empty folder to write the source folder in",
      openLabel: "Decompile Here", canSelectFiles: false, canSelectFolders: true,
    }))?.[0].fsPath);
    if (!file || !folder) {
      return undefined;
    }
    let ran = await this.run(`decompiling ${path.basename(file)}`, ["decompile", file, folder]);
    if (ran?.stopped) {
      return undefined;
    }
    // 3: the round trip did not confirm the folder, so nothing was written.
    if (ran?.code === 3) {
      const writing = answers.writeAnyway ?? (await vscode.window.showWarningMessage(
        "The decompiled folder does not compile back into the same file.",
        { modal: true, detail: `${roundTripDifferences(ran.errors)}\n\nThe folder is ` +
          "still what nxwright read from the file." },
        "Write Anyway")) === "Write Anyway";
      if (!writing) {
        return ran.code;
      }
      ran = await this.run(`decompiling ${path.basename(file)}`,
                           ["decompile", file, folder, "--continue-unconfirmed"]);
      if (ran?.stopped) {
        return undefined;
      }
    }
    if (ran === undefined || ran.code !== 0) {
      if (ran) {
        void this.failed("the decompile", ran.errors);
      }
      return ran?.code;
    }
    const open = answers.open ?? (await vscode.window.showInformationMessage(
      `nxwright: decompiled ${path.basename(file)} into ${folder}.`, "Open Folder")) ===
      "Open Folder";
    if (open) {
      await vscode.commands.executeCommand("vscode.openFolder", vscode.Uri.file(folder),
                                           { forceNewWindow: true });
    }
    return 0;
  }

  // Uploads `tft` to the chosen screen, choosing it first if need be: finds
  // the screen, asks the user to confirm, or takes `confirmed`, then
  // uploads, showing the progress. Returns the upload's exit code, or of
  // the search that failed, or undefined when nothing was sent.
  private async upload(tft: string, confirmed?: boolean): Promise<number | undefined> {
    const screen = chosenScreen(this.means.context) ?? await this.chooseScreen();
    if (!screen) {
      return undefined;
    }
    const target = ["upload", tft, "--port", screen.port, "--upload-baud", String(screen.rate)];
    const finding = await this.run(`looking for the screen on ${screen.port}`,
                                   [...target, "--find", "--json"]);
    if (finding?.stopped) {
      return undefined;
    }
    const found = finding?.events.find((event) => event.event === "found");
    if (found) {
      await saveScreen(this.means.context, { ...screen, model: String(found.screen) });
      this.means.changed();
    }
    if (finding === undefined || finding.code !== 0) {
      if (finding) {
        this.showFailedUpload(tft, screen.port, "finding the screen", finding);
      }
      return finding?.code;
    }
    if (!found) {
      void this.failed("finding the screen", finding.errors);
      return 1;
    }
    const going = confirmed ?? await this.uploadConfirmed(tft, found);
    if (!going) {
      return undefined;
    }
    let shown = 0;
    let skipped = 0;
    const uploading = await this.run(`uploading ${path.basename(tft)}`, [
      ...target, "--baud", String(found.screen_rate), "--yes", "--json",
    ], (event, progress) => {
      if (event.event === "skipped") {
        skipped = Number(event.bytes);
      } else if (event.event === "progress" && Number(event.size) > 0) {
        const percent = Math.floor(100 * Number(event.sent) / Number(event.size));
        progress.report({ increment: percent - shown, message: `${percent}%` });
        shown = percent;
      }
    });
    if (uploading === undefined) {
      return undefined;
    }
    if (uploading.stopped) {
      void vscode.window.showWarningMessage("nxwright: the upload was stopped. The screen now " +
        "needs to be powered off and on, and the file uploaded again.");
    } else if (uploading.code === 0) {
      void vscode.window.showInformationMessage(
        `nxwright: uploaded ${path.basename(tft)} to ${found.screen} on ${screen.port}.` +
        (skipped ? ` The screen already had ${skipped} bytes of it, which were not sent.` : ""));
    } else {
      this.showFailedUpload(tft, screen.port, "the upload", uploading);
    }
    return uploading.code;
  }

  // Shows why the run `ran` failed. If the toolchain cancelled the upload,
  // an error dialog gives the reason. Otherwise the run's errors are shown
  // as a failure of `what`, such as "the upload". Neither dialog is
  // awaited, so that the command returns at once.
  private showFailedUpload(tft: string, port: string, what: string, ran: JsonRun): void {
    const cancelled = ran.events.find((event) => event.event === "cancelled");
    if (cancelled) {
      void vscode.window.showErrorMessage(
        `${path.basename(tft)} cannot be uploaded to the screen on ${port}.`,
        { modal: true, detail: String(cancelled.reason) });
    } else {
      void this.failed(what, ran.errors);
    }
  }

  // Asks whether to upload `tft` to the screen `found`. The question is
  // shown as a warning when the toolchain warned of something, such as an
  // upload rate the screen may not take.
  private async uploadConfirmed(tft: string, found: JsonEvent): Promise<boolean> {
    const megabytes = (Number(found.size) / 1_000_000).toFixed(1);
    const warnings = (found.warnings ?? []) as string[];
    const lines = [
      "The project the screen runs now will be replaced.",
      `The file is ${megabytes} MB, and the upload will run at ${found.upload_rate} baud.`,
      ...warnings.map((warning) => `${warning.charAt(0).toUpperCase()}${warning.slice(1)}.`),
    ];
    const model = String(found.screen).split("_")[0];
    const question = `Upload ${path.basename(tft)} to the ${model} on ${found.port}?`;
    const options = { modal: true, detail: lines.join("\n\n") };
    const answer = warnings.length > 0
      ? await vscode.window.showWarningMessage(question, options, "Upload")
      : await vscode.window.showInformationMessage(question, options, "Upload");
    return answer === "Upload";
  }

  // Lets the user pick a port among those the toolchain lists. Returns it,
  // or undefined when there is none, having said so, or the user cancelled.
  private async pickPort(): Promise<string | undefined> {
    const listed = await this.run("listing the serial ports", ["ports", "--json"]);
    if (listed?.stopped) {
      return undefined;
    }
    if (listed === undefined || listed.code !== 0) {
      if (listed) {
        void this.failed("listing the serial ports", listed.errors);
      }
      return undefined;
    }
    if (listed.events.length === 0) {
      void vscode.window.showErrorMessage("nxwright: no serial port was found. Connect the " +
        "screen's serial adapter, then choose the screen again.");
      return undefined;
    }
    const picked = await vscode.window.showQuickPick(
      listed.events.map((port) => ({ label: String(port.port),
                                     description: String(port.description ?? "") })),
      { title: "nxwright: the screen's serial port" });
    return picked?.label;
  }

  // Lets the user pick the upload's rate, `current` first when given.
  private async pickRate(current?: number): Promise<number | undefined> {
    const first = current ?? DEFAULT_UPLOAD_RATE;
    const rates = [first, ...UPLOAD_RATES.filter((rate) => rate !== first)];
    const picked = await vscode.window.showQuickPick(rates.map((rate) => ({
      label: String(rate),
      description: [rate === current ? "current" : "",
                    rate === DEFAULT_UPLOAD_RATE ? "default" : "",
                    rate > 115200 ? "older screens and some adapters cannot take it" : ""]
        .filter(Boolean).join(", "),
    })), { title: "nxwright: the upload's rate, in bauds" });
    return picked ? Number(picked.label) : undefined;
  }

  // Runs the toolchain with `args`, showing `doing` in a notification that
  // can stop it, and `onEvent`'s progress. Returns the run, or undefined
  // when the toolchain was not found.
  private async run(doing: string, args: string[],
                    onEvent?: (event: JsonEvent,
                               progress: vscode.Progress<{ message?: string;
                                                           increment?: number }>) => void,
  ) {
    const command = await this.means.command();
    if (command === undefined) {
      return undefined;
    }
    this.output.appendLine(`> nxwright ${args.join(" ")}`);
    const ran = await vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification, cancellable: true,
      title: `nxwright: ${doing}`,
    }, (progress, token) => {
      const stop = new AbortController();
      token.onCancellationRequested(() => stop.abort());
      return runJson(command, args, {
        cwd: this.means.workingFolder(), signal: stop.signal,
        onEvent: (event) => onEvent?.(event, progress),
      });
    });
    this.output.append(ran.printed.map((line) => `${line}\n`).join("") + ran.errors);
    return ran;
  }

  // The TFT file chosen for `folder`, or one the user names now.
  private async tftFile(folder: vscode.Uri): Promise<string | undefined> {
    return this.means.context.workspaceState.get<string>(tftFileKey(folder))
      ?? this.askTftFile(folder);
  }

  private async askTftFile(folder: vscode.Uri, given?: string): Promise<string | undefined> {
    let file = given;
    if (file === undefined) {
      // The dialog starts beside the project file, under its name, or else
      // beside the source folder, under the app's.
      const projectFile = this.means.context.workspaceState.get<string>(projectFileKey(folder));
      const start = projectFile ? projectFile.replace(/\.[^.\\/]*$/, "") + ".tft"
        : path.join(path.dirname(folder.fsPath), `${await this.means.appName(folder)}.tft`);
      file = (await vscode.window.showSaveDialog({
        title: `nxwright: the TFT file Compile writes for ${folder.fsPath}`,
        saveLabel: "Choose", filters: { "TFT file": ["tft"] }, defaultUri: vscode.Uri.file(start),
      }))?.fsPath;
    }
    if (file !== undefined) {
      await this.means.context.workspaceState.update(tftFileKey(folder), file);
      this.means.changed();
    }
    return file;
  }

  // Runs the compile of `source`, a source folder or a project file, into
  // `tft`, replacing it, and writing `projectFile` too when given. When the
  // firmware is missing, offers its sources, or takes `answer`, and runs
  // the compile again with the one chosen. Returns the exit code, or
  // undefined when the compile did not run.
  private async compile(source: string, tft: string, projectFile?: string,
                        answer?: FirmwareAnswer): Promise<number | undefined> {
    let given: string[] = [];
    for (;;) {
      const ran = await this.run(`compiling ${path.basename(tft)}`, [
        "compile", source, tft, "--overwrite", "--json", ...settingsArguments(), ...given,
        ...(projectFile ? ["--project-file", projectFile] : []),
      ], (event, progress) => progress.report({ message: progressMessage(event) }));
      if (ran === undefined) {
        return undefined;
      }
      if (ran.code === 0) {
        await this.compiled(tft, projectFile, ran.events);
        return 0;
      }
      if (ran.stopped) {
        void vscode.window.showInformationMessage("nxwright: the compile was stopped.");
        return ran.code;
      }
      const missing = ran.events.find((event) => event.event === "firmware-missing");
      if (missing === undefined || given.length > 0) {
        void this.failed("the compile", ran.errors);
        return ran.code;
      }
      const chosen = answer ?? await this.askFirmware(String(missing.version));
      if (chosen === "cancel") {
        return ran.code;
      }
      given = firmwareArguments(chosen);
    }
  }

  // Says what the compile wrote, with its warnings, and remembers the
  // project file it wrote.
  private async compiled(tft: string, projectFile: string | undefined,
                         events: JsonEvent[]): Promise<void> {
    if (projectFile) {
      await rememberProjectFile(this.means.context, projectFile);
    }
    const written = [tft, projectFile].filter(Boolean).map((file) => path.basename(file!));
    const warnings = (events.find((event) => event.event === "compiled")?.warnings ?? []) as
      string[];
    if (warnings.length > 0) {
      const shown = await vscode.window.showWarningMessage(
        `nxwright: compiled ${written.join(" and ")}, with ${warnings.length} warning` +
        `${warnings.length === 1 ? "" : "s"}.`, "Show Output");
      if (shown) {
        this.output.show();
      }
    } else {
      void vscode.window.showInformationMessage(`nxwright: compiled ${written.join(" and ")}.`);
    }
  }

  // Asks where to take the firmware of `version`, as "1.68.2", from.
  private async askFirmware(version: string): Promise<FirmwareAnswer> {
    const answer = await vscode.window.showWarningMessage(
      `The compile needs the firmware of the Nextion Editor ${version}.`,
      { modal: true, detail: "Nothing on this computer has it. nxwright can download it from " +
        `Nextion's site, about 50 MB, or take it from a TFT file the Nextion Editor ${version} ` +
        "wrote, or from a folder of that Nextion Editor." },
      "Download", "Choose a TFT File", "Choose a Nextion Editor Folder");
    if (answer === "Download") {
      return "download";
    }
    if (answer === "Choose a TFT File") {
      const file = await vscode.window.showOpenDialog({
        title: "nxwright: a TFT file to take the firmware from", openLabel: "Take Firmware",
        filters: { "TFT file": ["tft"] },
      });
      return file ? { firmware: file[0].fsPath } : "cancel";
    }
    if (answer === "Choose a Nextion Editor Folder") {
      const folder = await vscode.window.showOpenDialog({
        title: "nxwright: a Nextion Editor folder to take the firmware from",
        openLabel: "Take Firmware", canSelectFiles: false, canSelectFolders: true,
      });
      return folder ? { editor: folder[0].fsPath } : "cancel";
    }
    return "cancel";
  }

  // Says that `what` failed, with the last line of what the toolchain wrote,
  // and offers the rest, in the output panel.
  private async failed(what: string, errors: string): Promise<void> {
    const last = errors.trim().split("\n").pop()?.replace(/^nxwright \S+: /, "") ?? "";
    const shown = await vscode.window.showErrorMessage(
      `nxwright: ${what} failed${last ? `: ${last}` : "."}`, "Show Output");
    if (shown) {
      this.output.show();
    }
  }
}

// The progress to show for one of the compile's objects: the firmware's
// download, as it goes on.
function progressMessage(event: JsonEvent): string | undefined {
  if (event.event === "download") {
    const done = Number(event.done) / 1_000_000;
    const size = Number(event.size) / 1_000_000;
    return `downloading the firmware, ${done.toFixed(1)} of ${size.toFixed(1)} MB`;
  }
  return undefined;
}
