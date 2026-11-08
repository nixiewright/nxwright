// The nxwright extension. Highlighting .nx files needs no code: package.json
// declares the grammar. This file starts nxwright's language server,
// `nxwright lsp`, which answers questions such as where a name is defined,
// runs nxwright's subcommands from the command palette, and opens the page
// preview (preview.ts), nxwright's side bar (sideBar.ts, projectView.ts,
// pagesView.ts, and mediaView.ts), the simulator (simulator.ts) and the
// channel through which agents drive it (agentChannelServer.ts), the Fonts
// panel (fontPanel.ts), the font and media viewers (fontViewer.ts,
// mediaViewer.ts), and the Editor code a .nx file compiles to
// (editorCodeViews.ts).
// The client holds no knowledge of the language: the server has it all.
import { execFile } from "child_process";
import * as path from "path";
import * as vscode from "vscode";
import { LanguageClient, LanguageClientOptions, ServerOptions } from "vscode-languageclient/node";
import { activeFile } from "./activeFile";
import { AgentChannel } from "./agentChannelServer";
import { CurrentProject, NO_PROJECT_ERROR, projectFileKey } from "./currentProject";
import { EditorCodeViews } from "./editorCodeViews";
import { FontPanels } from "./fontPanel";
import { FontViewer } from "./fontViewer";
import { animationArguments, MediaQuestions, pictureArguments, sdPictureArguments,
  soundArguments, videoArguments } from "./mediaCommands";
import { findNxwright, NxwrightSearch, programOnPath, runsCleanly } from "./nxwrightCommand";
import { declaredLaunchParameters, simulationEntry, simulationEntryEdits, simulationEntryText }
  from "./launchConfiguration";
import { MediaActions } from "./mediaActions";
import { MediaView } from "./mediaView";
import { MediaViewers } from "./mediaViewer";
import { NxlangPanel } from "./nxlangPanel";
import { askChineseFont, PageEditing } from "./pageEditing";
import { isPageFile, Pages } from "./pages";
import { PageComponents } from "./pageComponents";
import { PagesView } from "./pagesView";
import { DRAWN_FILE_TYPES, PagePreviews } from "./preview";
import { appName, projectFileName } from "./projectName";
import { ProjectView } from "./projectView";
import { ChosenPython } from "./pythonExtension";
import { ServerKeeper } from "./serverKeeper";
import { ComponentsView, PropertiesView } from "./sideBar";
import { Simulator } from "./simulator";
import { startTests } from "./tests";
import { registerTftCommands } from "./tftCommands";
import { projectFileMayBeReplaced, rememberProjectFile, settingsArguments } from "./tftFiles";
import { warnerOnce } from "./toolchainVersion";
import { extractChoice } from "./unknownContent";
import { appTomlUnsaved, refusedForUnsaved } from "./unsavedChanges";
import { errorText } from "./userMessages";

let client: LanguageClient | undefined;
// The page previews and the side bar's page, told when the server starts.
let pagePreviews: PagePreviews | undefined;
let shownPages: Pages | undefined;
// The project the side bar shows, and the folder commands act on, and the
// side bar's Project section, told when a project file is chosen.
let currentProject: CurrentProject | undefined;
let projectView: ProjectView | undefined;
// The Python interpreter chosen in VS Code, which a search may ask for.
let chosenPython: ChosenPython | undefined;
// The searches for the command that runs nxwright, and the language
// server's starts and stops, kept in order (serverKeeper.ts).
const keeper = new ServerKeeper({ search: searchCommand, start: startServer, stop: stopServer });

// The measures of a page against the build's limits, as the server's
// nxwright/limits request returns them.
interface PageLimits {
  page: string;
  objects: number;
  mostObjects: number;
  chain: string[];
  mostChain: number;
  globals: number;
  mostGlobals: number;
}

// The status bar entry showing the active file's page against its limits.
const limitsItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);

// The views of the Editor code a .nx file compiles to (editorCodeViews.ts).
const editorCodeViews = new EditorCodeViews(() => client);

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const getClient = () => client;
  const pages = new Pages(getClient);
  const editing = new PageEditing(getClient);
  const previews = new PagePreviews({ context, client: getClient, pages, editing });
  const properties = new PropertiesView(context, getClient, pages, editing);
  const project = new CurrentProject(getClient);
  const fontPanels = new FontPanels(context, getClient, project);
  const simulator = new Simulator(context, project, pages);
  pagePreviews = previews;
  shownPages = pages;
  currentProject = project;
  projectView = new ProjectView(context, project);
  const nxlangPanel = new NxlangPanel(context, getClient, project);
  // A preview redraws when its page's folder changes, on disk or in an editor.
  // The watcher also covers .nx files, because an edit to one can change
  // which events the Go to Event submenu marks as having code.
  const folderFiles = vscode.workspace.createFileSystemWatcher(
    `**/*.{${[...DRAWN_FILE_TYPES, "nx"].join(",")}}`);
  const pagesView = new PagesView(project, pages, getClient);
  const changed = (uri: vscode.Uri) => {
    previews.changed(uri);
    pagesView.fileChanged(uri);
    pages.changed(uri);
    fontPanels.changed(uri);
  };
  // The side bar shows the page of the last active editor that was a page's.
  const editorChanged = (editor: vscode.TextEditor | undefined) => {
    if (editor && isPageFile(editor.document.uri)) {
      pages.show(editor.document.uri);
    }
  };
  editorChanged(vscode.window.activeTextEditor);
  chosenPython = new ChosenPython(() => void keeper.searchAgain());
  context.subscriptions.push(
    chosenPython,
    limitsItem,
    folderFiles,
    folderFiles.onDidChange(changed),
    folderFiles.onDidCreate(changed),
    folderFiles.onDidDelete(changed),
    ...previews.register(),
    properties.register(),
    new ComponentsView(pages),
    ...new PageComponents(pages, editing).register(),
    ...project.register(),
    ...projectView.register(),
    ...pagesView.register(),
    ...simulator.register(),
    ...new AgentChannel(simulator).register(),
    ...new MediaView(project).register(),
    ...new MediaActions({
      project, fontPanels, client: getClient, command: commandToRun,
      runSubcommand, questions: MEDIA_QUESTIONS, workingFolder: firstWorkspaceFolder,
    }).register(),
    new FontViewer(context, getClient, fontPanels).register(),
    ...new MediaViewers(context, getClient).register(),
    vscode.commands.registerCommand("nxwright.showPreview", () => previews.show()),
    vscode.commands.registerCommand("nxwright.showPageText", () => previews.showText()),
    vscode.window.onDidChangeActiveTextEditor(editorChanged),
    vscode.window.onDidChangeActiveTextEditor(showLimits),
    // A preview becoming active, or a page's tabs closing.
    vscode.window.tabGroups.onDidChangeTabs(() => {
      pages.tabsChanged();
      void showLimits();
    }),
    // The server sends new findings after each check, with new measures.
    vscode.languages.onDidChangeDiagnostics(showLimits),
    vscode.workspace.onDidChangeConfiguration(async (event) => {
      if (event.affectsConfiguration("nxwright.command")) {
        await keeper.searchAgain();
      }
    }),
    vscode.commands.registerCommand("nxwright.build", () => build(context)),
    ...registerTftCommands({
      context, sourceFolder: activeSourceFolder, command: commandToRun,
      workingFolder: firstWorkspaceFolder,
      appName: async (folder) =>
        await currentProject?.nameOf(folder) ?? path.basename(folder.fsPath),
      changed: () => projectView?.projectFileChanged(),
    }),
    vscode.commands.registerCommand("nxwright.extract",
      (given?: ExtractArguments) => extract(given)),
    // The warning before a changed project file is replaced runs this (tftFiles.ts).
    // It is not in the palette.
    vscode.commands.registerCommand("nxwright.showChanges",
      (args: string[]) => runSubcommand("diff", args)),
    vscode.commands.registerCommand("nxwright.changeScreen", () => changeDevice("screen")),
    vscode.commands.registerCommand("nxwright.changeRotation", () => changeDevice("rotation")),
    vscode.commands.registerCommand("nxwright.changeEncoding", () => changeDevice("encoding")),
    vscode.commands.registerCommand("nxwright.chooseProjectFile", () => chooseProjectFile(context)),
    vscode.commands.registerCommand("nxwright.upgrade", upgrade),
    ...nxlangPanel.register(),
    vscode.commands.registerCommand("nxwright.switchToNxlang", () => nxlangPanel.show()),
    vscode.commands.registerCommand("nxwright.newSourceFolder", newSourceFolder),
    vscode.commands.registerCommand("nxwright.importProject", () => importProject(context)),
    vscode.commands.registerCommand("nxwright.addPage", addPage),
    vscode.commands.registerCommand("nxwright.addLaunchConfiguration",
                                    () => addLaunchConfiguration(context)),
    vscode.commands.registerCommand("nxwright.fonts", () => showFonts(fontPanels, false)),
    vscode.commands.registerCommand("nxwright.addFont", () => showFonts(fontPanels, true)),
    vscode.commands.registerCommand("nxwright.addKeyboard", addKeyboard),
    vscode.commands.registerCommand("nxwright.addPictures",
                                    () => addMedia("pictures", pictureArguments)),
    vscode.commands.registerCommand("nxwright.addAnimation",
                                    () => addMedia("an animation", animationArguments)),
    vscode.commands.registerCommand("nxwright.addVideo",
                                    () => addMedia("a video", videoArguments)),
    vscode.commands.registerCommand("nxwright.addSound",
                                    () => addMedia("a sound", soundArguments)),
    vscode.commands.registerCommand("nxwright.writeCardPictures", writeCardPictures),
    // The debugger of a test and its screen code: nxwright's debug adapter, one per session.
    vscode.debug.registerDebugAdapterDescriptorFactory("nxwright", {
      createDebugAdapterDescriptor: async () => {
        const { command, pythons } = await keeper.forCommand();
        if (command === undefined) {
          // VS Code shows it as the session's error.
          throw new Error(notFoundMessage(pythons));
        }
        const run = withWorkspaceFolder(command);
        return new vscode.DebugAdapterExecutable(run[0], [...run.slice(1), "debug-adapter"]);
      },
    }),
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (event.document.uri.scheme === "file") {
        changed(event.document.uri);
      }
    }),
    vscode.window.onDidChangeTextEditorSelection((event) => {
      // Not when an edit moved the cursor: the edit may come from the side bar.
      if (event.kind !== undefined) {
        pages.cursorMoved(event.textEditor);
      }
    }),
    vscode.languages.onDidChangeDiagnostics((event) => properties.diagnosticsChanged(event.uris)),
  );
  editorCodeViews.register(context);
  startTests(context, commandToRun);
  await keeper.start();
}

export async function deactivate(): Promise<void> {
  // A restart still queued must not start a server after this stop, and a
  // start under way is stopped once its server has started.
  await keeper.close();
  await stopServer();
}

// Starts the language server with the command `searched` found, or says
// that none was found.
async function startServer(searched: NxwrightSearch): Promise<void> {
  const { command: found, pythons } = searched;
  if (found === undefined) {
    void showErrorWithSetting(`${notFoundMessage(pythons)} Highlighting still works.`);
    return;
  }
  const command = withWorkspaceFolder(found);
  const serverOptions: ServerOptions = { command: command[0], args: [...command.slice(1), "lsp"] };
  const clientOptions: LanguageClientOptions = {
    // Page files and app.toml are chosen by their path. Their language
    // depends on which TOML extension is installed, if any.
    documentSelector: [
      { scheme: "file", language: "nxwright" },
      { scheme: "file", pattern: "**/pages/*.page.toml" },
      { scheme: "file", pattern: "**/app.toml" },
    ],
    // Changes on disk, such as an extract or a git checkout, are checked too.
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher(
        "**/*.{nx,toml,png,jpg,jpeg,bmp,gif,zi,gmov,video,wav}"),
    },
  };
  const starting = new LanguageClient("nxwright", "nxwright", serverOptions, clientOptions);
  try {
    await starting.start();
    client = starting;
    warnOfAnOldToolchain(starting.initializeResult?.serverInfo?.version);
    pagePreviews?.serverStarted();
    shownPages?.serverStarted();
    currentProject?.serverChanged();
    // After each check, which may change the page's measures, even when it
    // finds nothing to report.
    starting.onNotification("nxwright/checked", () => {
      void showLimits();
      currentProject?.serverChanged();
      // A change elsewhere, such as in an included file, changes the views too.
      editorCodeViews.refreshSoon();
    });
  } catch (error) {
    // Without the server, highlighting still works: say why the rest does not.
    void showErrorWithSetting(
      `nxwright: the language server did not start (${error}). ` +
        "Check the setting nxwright.command. Highlighting still works.",
    );
  }
}

// Warns, once a session, when the language server's toolchain is older than
// the extension works with.
const warnOfAnOldToolchain = warnerOnce((warning) => void vscode.window.showWarningMessage(warning));

// Shows the error `message`, with a button that opens the setting nxwright.command.
async function showErrorWithSetting(message: string): Promise<void> {
  const openSetting = "Open Settings";
  if ((await vscode.window.showErrorMessage(message, openSetting)) === openSetting) {
    await vscode.commands.executeCommand("workbench.action.openSettings", "nxwright.command");
  }
}

// Shows the active file's page against the build's limits, from the
// server's last check, or nothing outside a source folder. The active file
// is that of the active text editor, or of the active page preview.
async function showLimits(): Promise<void> {
  const uri = activeFile();
  const limits =
    client && uri
      ? await client
          .sendRequest<PageLimits | null>("nxwright/limits", {
            textDocument: { uri: uri.toString() },
          })
          .catch(() => null)
      : null;
  if (!limits) {
    limitsItem.hide();
    return;
  }
  // A chain of an event and the calls and clicks it nests: its calls and
  // clicks are one fewer than its members.
  const nesting = Math.max(limits.chain.length - 1, 0);
  limitsItem.text = `${limits.page}: ${limits.objects}/${limits.mostObjects} objects, ` +
    `chain ${nesting}/${limits.mostChain}`;
  limitsItem.tooltip =
    `Longest chain of calls and clicks: ${limits.chain.join(" -> ") || "none"}\n` +
    `program.s globals of all pages: ${limits.globals} of the ${limits.mostGlobals} known to work`;
  limitsItem.show();
}

async function stopServer(): Promise<void> {
  const running = client;
  client = undefined;
  await running?.stop();
}

// Returns the command that runs nxwright, for a command or a test about to
// run it (ServerKeeper.forCommand), with ${workspaceFolder} replaced
// (withWorkspaceFolder). When none is found, says so, and returns undefined.
async function commandToRun(): Promise<string[] | undefined> {
  const { command, pythons } = await keeper.forCommand();
  if (command === undefined) {
    void showErrorWithSetting(notFoundMessage(pythons));
    return undefined;
  }
  return withWorkspaceFolder(command);
}

// Starts a search for the command that runs nxwright, and returns it: the
// setting nxwright.command when it is not empty, else as findNxwright finds
// it (nxwrightCommand.ts).
function searchCommand(): Promise<NxwrightSearch> {
  const configured = vscode.workspace.getConfiguration("nxwright").get<string[]>("command") ?? [];
  return configured.length > 0
    ? Promise.resolve({ command: configured, pythons: [] })
    : findNxwright(process.platform, {
        programOnPath: (name) => programOnPath(name, process.env.PATH ?? "", process.platform),
        runsCleanly,
        chosenPython: async () => chosenPython?.path(),
      });
}

// The message saying that nxwright was not found: the Pythons tried, as
// commands, and what to do.
function notFoundMessage(pythons: string[][]): string {
  return "nxwright: the nxwright command is not on PATH, and none of these Pythons runs " +
    `nxwright: ${pythons.map((python) => python.join(" ")).join(", ")}. Install nxwright ` +
    "into one of them with pip, or set nxwright.command.";
}

// Returns `command` with ${workspaceFolder} replaced by the path of the
// workspace's first folder.
function withWorkspaceFolder(command: string[]): string[] {
  return command.map((part) => part.split("${workspaceFolder}").join(firstWorkspaceFolder() ?? ""));
}

function firstWorkspaceFolder(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

// The palette commands. Each works on the current project's source folder
// (currentProject.ts).

async function build(context: vscode.ExtensionContext): Promise<void> {
  const folder = await activeSourceFolder();
  const project = folder && (await projectFile(context, folder));
  // The user chose this file to build into, so it is replaced without asking,
  // unless it changed elsewhere since nxwright last wrote it (tftFiles.ts).
  if (folder && project && await projectFileMayBeReplaced(context, project.fsPath, folder.fsPath)) {
    const code = await runSubcommand("build", ["build", folder.fsPath, project.fsPath,
                                               "--overwrite", ...settingsArguments()],
                                     "building the project file...");
    if (code === 0) {
      await rememberProjectFile(context, project.fsPath);
    }
  }
}

// What a caller may give the Extract command in place of asking the user. The
// overwrite warning gives only the project file. The extension's tests also give
// the folder, and whether to go on when the next build may lose some content.
// With a folder, the command does not prompt the user.
interface ExtractArguments {
  project: string;
  folder?: string;
  goOnPastUnknown?: boolean;
}

// Extracts a project file into a new or empty folder, and asks the user for
// whichever of the two `given` does not have. Returns the exit code of extract
// when `given` has a folder, and otherwise undefined. The new folder does not
// remember the file, because a build from it would then overwrite the project
// file of the folder it came from. Import a Nextion Editor project does remember it.
async function extract(given?: ExtractArguments): Promise<number | undefined> {
  if (given?.folder !== undefined) {
    const unknown = await unknownContentArguments(given.project, given.goOnPastUnknown);
    return unknown === undefined ? undefined
      : runSubcommand("extract", ["extract", given.project, given.folder, ...unknown]);
  }
  const title = "Extract into a new folder";
  const project = given ? vscode.Uri.file(given.project) : (await vscode.window.showOpenDialog({
    filters: { "Nextion project": ["HMI"] },
    openLabel: "Extract",
    title: `${title}: the project file`,
  }))?.[0];
  const folder = project && await extractedIntoChosenFolder(project, title);
  if (folder) {
    await offerToAddToWorkspace(folder);
  }
  return undefined;
}

async function chooseProjectFile(context: vscode.ExtensionContext): Promise<void> {
  const folder = await activeSourceFolder();
  if (folder) {
    await askProjectFile(context, folder);
  }
}

// What `nxwright device` changes, as the question before running it says:
// a new screen resizes the pages; a new rotation also turns the fonts and
// videos; a new encoding converts the fonts.
const PROBLEMS_LISTED = "The terminal will list any problems when it is done.";
const NO_LONGER_FIT =
  `Components will keep their positions and sizes, so some may no longer fit. ${PROBLEMS_LISTED}`;
const DEVICE_CHANGES = {
  screen: `Every page will be resized to the new screen.\n\n${NO_LONGER_FIT}`,
  rotation: "Every page will be resized for the new orientation, and fonts and videos will " +
    `be rotated. Videos will lose a little quality.\n\n${NO_LONGER_FIT}`,
  encoding: "The fonts will be converted to the new encoding. Characters the new encoding " +
    "does not have will be dropped from them.\n\nTexts will be stored in the new encoding " +
    `at the next build. ${PROBLEMS_LISTED}`,
};

// Changes the current project's screen model, rotation, or character
// encoding, as the Project section's pencils ask: a new value from the list
// "Create a new nxwright project" offers, the current one first, then
// `nxwright device`, run as a task once the user confirms what it changes.
async function changeDevice(setting: "screen" | "rotation" | "encoding"): Promise<void> {
  const folder = await activeSourceFolder();
  if (!folder || refusedForUnsaved(folder, "changing the device settings")) {
    return;
  }
  if (!client) {
    void showErrorWithSetting("nxwright: the language server is not running, and it lists " +
                              "the screen models, rotations, and encodings.");
    return;
  }
  const choices = await newFolderChoices(client);
  if (!choices) {
    return;
  }
  const info = currentProject?.info;
  const name = await currentProject?.nameOf(folder) ?? appName(null, folder.fsPath);
  let chosen: string | undefined;
  if (setting === "screen") {
    const current = choices.models.find((entry) => entry.name === info?.screen);
    const models = current ? [current, ...choices.models.filter((entry) => entry !== current)]
      : choices.models;
    chosen = (await vscode.window.showQuickPick(
      models.map((entry) => ({
        label: entry.name,
        description: entry === current ? `${entry.specs ?? entry.size}, current`
          : entry.specs ?? entry.size,
      })),
      { title: `The screen model of ${name}`, matchOnDescription: true }))?.label;
    if (chosen === info?.screen) {
      chosen = undefined;
    }
  } else if (setting === "rotation") {
    const rotation = await pickWithDefault(
      choices.rotations, info?.rotation ?? choices.defaults.rotation,
      `The rotation of ${name}`, (degrees) => `${degrees} degrees`, undefined,
      info?.rotation !== undefined ? "current" : "default");
    chosen = rotation === undefined || rotation === info?.rotation ? undefined : String(rotation);
  } else {
    const encoding = await pickWithDefault(
      choices.encodings, info?.encoding ?? choices.defaults.encoding,
      `The character encoding of ${name}`, (value) => value, undefined,
      info?.encoding !== undefined ? "current" : "default");
    chosen = encoding === info?.encoding ? undefined : encoding;
  }
  if (chosen === undefined) {
    return;
  }
  const question = setting === "screen" ? `Switch ${name} to the ${chosen} screen?`
    : setting === "rotation" ? `Rotate ${name} to ${chosen} degrees?`
    : `Change the character encoding of ${name} to ${chosen}?`;
  const answer = await vscode.window.showWarningMessage(
    question,
    { modal: true, detail: DEVICE_CHANGES[setting] },
    "Change",
  );
  if (answer === "Change") {
    await runSubcommand("device", ["device", folder.fsPath, `--${setting}`, chosen],
                        `changing the ${setting === "screen" ? "screen model"
                            : setting === "encoding" ? "character encoding" : setting} ` +
                          `of ${name}...`);
  }
}

async function upgrade(): Promise<void> {
  const folder = await activeSourceFolder();
  if (folder) {
    await runSubcommand("upgrade", ["upgrade", folder.fsPath]);
  }
}

// The choices `nxwright new` asks for, and their defaults, as the server's
// nxwright/newFolderChoices gives them. A model's specs are its diagonal,
// size, flash, RAM, and processor frequency, in one line of text. An older
// toolchain gives only the size.
interface NewFolderChoices {
  models: { name: string; size: string; specs?: string }[];
  rotations: number[];
  encodings: string[];
  languages: string[];
  defaults: { rotation: number; encoding: string; language: string };
}

// Asks the language server for the choices `nxwright new` asks for. Says so,
// and returns undefined, when the request fails.
async function newFolderChoices(client: LanguageClient): Promise<NewFolderChoices | undefined> {
  try {
    return await client.sendRequest<NewFolderChoices>("nxwright/newFolderChoices", {});
  } catch (error) {
    void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
    return undefined;
  }
}

// What each language of a source folder's code is, as the new project's
// question shows it.
const LANGUAGE_DESCRIPTIONS: Record<string, string> = {
  nxlang: "the nxwright language",
  nextion: "strict Nextion syntax",
};

// Asks for a new project's screen model, rotation, encoding, language, and
// folder, as `nxwright new` asks at a terminal, and writes it through the
// language server. Then opens its first page, and offers to add the folder
// to the workspace when it is outside it.
async function newSourceFolder(): Promise<void> {
  if (!client) {
    void showErrorWithSetting("nxwright: the language server is not running, and it writes " +
                              "the new project.");
    return;
  }
  const title = "Create a new nxwright project";
  const choices = await newFolderChoices(client);
  if (!choices) {
    return;
  }
  const model = await vscode.window.showQuickPick(
    choices.models.map((entry) => ({ label: entry.name, description: entry.specs ?? entry.size })),
    { title: `${title}: the screen model`, matchOnDescription: true });
  const rotation = model && await pickWithDefault(
    choices.rotations, choices.defaults.rotation, `${title}: the rotation`,
    (degrees) => `${degrees} degrees`);
  const encoding = rotation !== undefined ? await pickWithDefault(
    choices.encodings, choices.defaults.encoding, `${title}: the character encoding`,
    (name) => name) : undefined;
  const language = encoding && await pickWithDefault(
    choices.languages, choices.defaults.language, `${title}: the language of the code`,
    (name) => name, (name) => LANGUAGE_DESCRIPTIONS[name]);
  const folder = language && (await vscode.window.showOpenDialog({
    canSelectFiles: false,
    canSelectFolders: true,
    openLabel: "Create the project here",
    title: `${title}: a new or empty folder`,
  }))?.[0];
  // The app's own name, which renaming the folder later keeps.
  const name = folder && await vscode.window.showInputBox({
    title: `${title}: the app's name`,
    value: path.basename(folder.fsPath),
    prompt: "As nxwright shows it. The folder may be renamed later, keeping it.",
    validateInput: (value) => value.trim() === "" || value !== value.trim() || /[\r\n]/.test(value)
      ? "A name of one line, not empty, with no spaces at its start or end." : undefined,
  });
  if (!model || rotation === undefined || !folder || name === undefined || !client) {
    return;
  }
  try {
    const written = await client.sendRequest<{ file: string; warning: string | null }>(
      "nxwright/newSourceFolder",
      { folder: folder.fsPath, screen: model.label, rotation, encoding, language, name },
    );
    await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(written.file));
    // What the folder's first font lacks, such as Noto Sans's box drawing in koi8-r.
    if (written.warning) {
      void vscode.window.showWarningMessage(`nxwright: ${written.warning}`);
    }
  } catch (error) {
    void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
    return;
  }
  await offerToAddToWorkspace(folder);
}

// Asks for one of `values` in a list, `chosen` first, marked as `mark`
// says, the default by default. `label` and `describe` show each value.
// Returns the value, or undefined when the question is dismissed.
async function pickWithDefault<T>(values: T[], chosen: T, title: string,
                                  label: (value: T) => string,
                                  describe?: (value: T) => string | undefined,
                                  mark = "default"):
    Promise<T | undefined> {
  const ordered = [chosen, ...values.filter((value) => value !== chosen)];
  const picked = await vscode.window.showQuickPick(
    ordered.map((value) => ({
      label: label(value),
      description: [describe?.(value), value === chosen ? mark : undefined]
        .filter((part) => part).join(", "),
      value,
    })),
    { title });
  return picked?.value;
}

// When `folder` is outside the workspace, offers to add it. This is a
// command's last step: adding the first folder to a window without one
// restarts the extensions, which ends the command.
async function offerToAddToWorkspace(folder: vscode.Uri): Promise<void> {
  if (vscode.workspace.getWorkspaceFolder(folder)) {
    return;
  }
  const add = "Add to workspace";
  const answer = await vscode.window.showInformationMessage(
    `nxwright: ${folder.fsPath} is outside the workspace.`, add);
  if (answer === add) {
    const count = vscode.workspace.workspaceFolders?.length ?? 0;
    vscode.workspace.updateWorkspaceFolders(count, 0, { uri: folder });
  }
}

// Asks for a new or empty folder, and extracts `project` into it. A folder that
// is not empty is rejected, with a message that says to choose another.
// Returns the folder, or undefined when the project was not extracted.
async function extractedIntoChosenFolder(project: vscode.Uri,
                                         title: string): Promise<vscode.Uri | undefined> {
  const folder = (await vscode.window.showOpenDialog({
    canSelectFiles: false,
    canSelectFolders: true,
    openLabel: "Extract here",
    title: `${title}: a new or empty folder`,
  }))?.[0];
  if (!folder) {
    return undefined;
  }
  if ((await vscode.workspace.fs.readDirectory(folder)).length > 0) {
    void vscode.window.showErrorMessage(
      `nxwright: ${folder.fsPath} is not empty. Choose a new or empty folder.`);
    return undefined;
  }
  const unknown = await unknownContentArguments(project.fsPath);
  if (unknown === undefined) {
    return undefined;
  }
  const exitCode = await runSubcommand("extract",
    ["extract", project.fsPath, folder.fsPath, ...unknown]);
  return exitCode === 0 ? folder : undefined;
}

// Asks for a project file (.HMI) and a new or empty folder, and extracts the
// project into it. The project file is remembered for the folder, so that Build
// writes back to it.
async function importProject(context: vscode.ExtensionContext): Promise<void> {
  const title = "Import a Nextion Editor project";
  const project = (await vscode.window.showOpenDialog({
    filters: { "Nextion project": ["HMI"] },
    openLabel: "Import",
    title: `${title}: the project file`,
  }))?.[0];
  const folder = project && await extractedIntoChosenFolder(project, title);
  if (!project || !folder) {
    return;
  }
  await context.workspaceState.update(projectFileKey(folder), project.fsPath);
  projectView?.projectFileChanged();
  await offerToAddToWorkspace(folder);
}

// Adds a blank page to the current project, named as asked, or the first
// free pageN, and opens it.
async function addPage(): Promise<void> {
  const folder = await activeSourceFolder();
  if (!folder || appTomlUnsaved(folder, "adding a page")) {
    return;
  }
  const name = await vscode.window.showInputBox({
    title: "New page",
    prompt: "The page's name. Leave it empty for the next free name, such as page1.",
  });
  if (name === undefined) {
    return;
  }
  if (!client) {
    void showErrorWithSetting("nxwright: the language server is not running, and it adds " +
                              "the page.");
    return;
  }
  try {
    const added = await client.sendRequest<{ page: string; file: string }>("nxwright/addPage", {
      // The server finds the project from any file of it.
      textDocument: { uri: vscode.Uri.joinPath(folder, "app.toml").toString() },
      ...(name.trim() ? { name: name.trim() } : {}),
    });
    await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(added.file));
  } catch (error) {
    void vscode.window.showErrorMessage(`nxwright: ${errorText(error)}`);
  }
}

// Adds to the launch.json of the current project's workspace folder a launch
// configuration simulating its app, with every other parameter a simulation
// takes commented out, each with its description (launchConfiguration.ts),
// unless one simulates it already, then opens launch.json. The file is
// edited as text, so that its comments stay, in one edit undo takes back.
async function addLaunchConfiguration(context: vscode.ExtensionContext): Promise<void> {
  const folder = await activeSourceFolder();
  if (!folder) {
    return;
  }
  const workspaceFolder = vscode.workspace.getWorkspaceFolder(folder);
  if (!workspaceFolder) {
    void vscode.window.showErrorMessage(
      `nxwright: ${folder.fsPath} is outside the workspace, and a launch configuration ` +
        "belongs to a workspace folder. Add the folder to the workspace first.");
    return;
  }
  // Every configuration VS Code offers for the folder tells whether one
  // simulates it, those of the workspace file and the user's settings among
  // them; the folder's own launch.json alone is written, with the entry added.
  const offered = vscode.workspace.getConfiguration("launch", workspaceFolder.uri)
    .get<unknown[]>("configurations") ?? [];
  const name = await currentProject?.nameOf(folder) ?? path.basename(folder.fsPath);
  const entry = simulationEntry(offered, workspaceFolder.uri.fsPath, folder.fsPath,
                                process.platform, name);
  const file = vscode.Uri.joinPath(workspaceFolder.uri, ".vscode", "launch.json");
  if (!entry) {
    void vscode.window.showInformationMessage(
      `nxwright: launch.json simulates ${folder.fsPath} already.`);
    await vscode.window.showTextDocument(file);
    return;
  }
  const declared = await declaredLaunchParameters(
    path.join(context.extensionPath, "package.json"));
  const exists = await vscode.workspace.fs.stat(file).then(() => true, () => false);
  const document = exists ? await vscode.workspace.openTextDocument(file) : undefined;
  const edits = simulationEntryEdits(document?.getText() ?? "",
                                     simulationEntryText(entry, declared));
  if (!edits) {
    void vscode.window.showErrorMessage(
      `nxwright: ${file.fsPath} holds no object of launch configurations to add one to.`);
    await vscode.window.showTextDocument(file);
    return;
  }
  // A launch.json open with changes not saved is left unsaved, with the
  // entry added: saving it would save those changes too.
  const unsaved = document?.isDirty ?? false;
  const change = new vscode.WorkspaceEdit();
  if (!document) {
    change.createFile(file, { ignoreIfExists: true });
  }
  for (const { offset, length, content } of edits) {
    const start = document ? document.positionAt(offset) : new vscode.Position(0, 0);
    const end = document ? document.positionAt(offset + length) : start;
    change.replace(file, new vscode.Range(start, end), content);
  }
  if (!(await vscode.workspace.applyEdit(change))) {
    void vscode.window.showErrorMessage(`nxwright: ${file.fsPath} could not be written.`);
    return;
  }
  if (!unsaved) {
    await (await vscode.workspace.openTextDocument(file)).save();
  }
  void vscode.window.showInformationMessage(
    `nxwright: added the launch configuration "${entry.name}".`);
  await vscode.window.showTextDocument(file);
}

// Shows the Fonts panel of the current project's source folder; with `atForm`,
// at its form for a new font.
async function showFonts(panels: FontPanels, atForm: boolean): Promise<void> {
  const folder = await activeSourceFolder();
  if (folder) {
    await panels.show(folder, atForm);
  }
}

// nxwright's keyboard pages, as `nxwright keyboard` names them, with the
// `key` that opens each.
const KEYBOARDS = [
  { label: "Full keyboard", description: "key 1", page: "keyboard" },
  { label: "Numeric keypad", description: "key 2", page: "keypad" },
  { label: "Speed dial", description: "key 3", page: "speed-dial" },
  { label: "Chinese input", description: "key 4, for a folder in gb2312",
    page: "chinese-input" },
];

async function addKeyboard(): Promise<void> {
  const folder = await activeSourceFolder();
  if (!folder || appTomlUnsaved(folder, "adding a keyboard page")) {
    return;
  }
  const chosen = await vscode.window.showQuickPick(KEYBOARDS, {
    title: "nxwright keyboard: the keyboard page to add",
  });
  if (!chosen) {
    return;
  }
  const options: string[] = [];
  if (chosen.page === "chinese-input") {
    // The folder's fonts the keyboard takes; without the server, a typeface
    // file alone is offered.
    const fonts = (await client?.sendRequest<{ fonts: string[] }>(
      "nxwright/chineseKeyboardFonts", { folder: folder.fsPath }).catch(() => null))?.fonts ?? [];
    const font = await askChineseFont(fonts);
    if (!font) {
      return;
    }
    options.push(...(font.font !== undefined ? ["--font", font.font]
      : ["--typeface", font.typeface ?? ""]));
  }
  await runSubcommand("keyboard", ["keyboard", folder.fsPath, chosen.page, ...options]);
}

// The questions of the media commands, as VS Code asks them (mediaCommands.ts).
const MEDIA_QUESTIONS: MediaQuestions = {
  files: async (title, filters, many) =>
    (await vscode.window.showOpenDialog({ title, filters, canSelectMany: many,
                                          openLabel: "Add" }))?.map((file) => file.fsPath),
  text: (title, prompt, value, check) =>
    Promise.resolve(vscode.window.showInputBox({ title, prompt, value, validateInput: check })),
  choice: (title, choices) => Promise.resolve(vscode.window.showQuickPick(choices, { title })),
  folder: async (title) =>
    (await vscode.window.showOpenDialog({ title, canSelectFiles: false, canSelectFolders: true,
                                          openLabel: "Write here" }))?.[0]?.fsPath,
};

// Makes `what`, pictures, an animation, a video, or a sound, and adds it to
// the current project's source folder: `ask` asks for its files and
// choices, and gives the arguments of the nxwright subcommand that makes it.
async function addMedia(what: string,
                        ask: (folder: string, questions: MediaQuestions) =>
                          Promise<string[] | undefined>): Promise<void> {
  const folder = await activeSourceFolder();
  if (!folder || appTomlUnsaved(folder, `adding ${what}`)) {
    return;
  }
  const args = await ask(folder.fsPath, MEDIA_QUESTIONS);
  if (args) {
    await runSubcommand(args[0], args, `adding ${what}...`);
  }
}

// Writes the files external pictures show from an SD card, of pictures
// asked for, into a folder asked for: no source folder is needed.
async function writeCardPictures(): Promise<void> {
  const args = await sdPictureArguments(MEDIA_QUESTIONS);
  if (args) {
    await runSubcommand(args[0], args);
  }
}

// Returns the current project's source folder (currentProject.ts). Says so,
// and returns undefined, when there is none.
async function activeSourceFolder(): Promise<vscode.Uri | undefined> {
  const folder = currentProject?.folder;
  if (!folder) {
    void vscode.window.showErrorMessage(NO_PROJECT_ERROR);
  }
  return folder;
}

// Returns the project file (.HMI) that goes with a source folder: the one
// chosen before for it, or one the user picks now, which is remembered.
async function projectFile(
  context: vscode.ExtensionContext,
  folder: vscode.Uri,
): Promise<vscode.Uri | undefined> {
  const remembered = context.workspaceState.get<string>(projectFileKey(folder));
  return remembered ? vscode.Uri.file(remembered) : askProjectFile(context, folder);
}

// Asks for a source folder's project file, and remembers the one chosen. A
// cancelled dialog keeps the earlier choice.
async function askProjectFile(
  context: vscode.ExtensionContext,
  folder: vscode.Uri,
): Promise<vscode.Uri | undefined> {
  const filters = { "Nextion project": ["HMI"] };
  const title = `nxwright: the project HMI file to build ${folder.fsPath} into`;
  // Build's dialog starts from a file named after the app, beside its source folder.
  const named = projectFileName(
    await currentProject?.nameOf(folder) ?? path.basename(folder.fsPath));
  const defaultUri = named === undefined ? undefined
    : vscode.Uri.joinPath(vscode.Uri.file(path.dirname(folder.fsPath)), named);
  const chosen = await vscode.window.showSaveDialog({
    filters, title, saveLabel: "Build", defaultUri });
  if (chosen) {
    await context.workspaceState.update(projectFileKey(folder), chosen.fsPath);
    projectView?.projectFileChanged();
  }
  return chosen;
}

// Runs `nxwright extract --list-unknown` on the project file `project`, and
// returns the extra arguments to pass to extract. That is none, or
// --continue-with-unknown when the user chose to extract a project whose
// content the next build may lose. Returns undefined when extract must not
// run, because unknownContent.ts refuses the project or the user chose not
// to go on. When `goOn` is given, it is the user's choice, and the user is
// not asked. The list runs first because the extract task cannot hand back
// what the command printed. When the list fails, extract runs as usual and
// prints the error itself.
async function unknownContentArguments(project: string,
                                       goOn?: boolean): Promise<string[] | undefined> {
  const command = await commandToRun();
  if (command === undefined) {
    return undefined;
  }
  const listed = await new Promise<string | undefined>((resolve) => {
    execFile(command[0], [...command.slice(1), "extract", "--list-unknown", project],
      { cwd: firstWorkspaceFolder(), windowsHide: true },
      (error, stdout) => resolve(error ? undefined : stdout));
  });
  if (listed === undefined) {
    return [];
  }
  const choice = extractChoice(listed);
  if (choice.kind === "refuse") {
    void vscode.window.showErrorMessage(`nxwright: ${choice.message}`);
    return undefined;
  }
  if (choice.kind === "ask") {
    const goingOn = goOn ?? (await vscode.window.showWarningMessage(
      "Extract anyway?", { modal: true, detail: choice.message }, "Extract")) === "Extract";
    return goingOn ? ["--continue-with-unknown"] : undefined;
  }
  return [];
}

// Runs `nxwright <args>` as a task, so its output shows in a terminal.
// Returns its exit code once it ends, or undefined when it did not run or
// gave none. If `doing` is given, a notification shows that text until the
// task ends, because the terminal can stay empty for a while. The
// notification has no Cancel button, because stopping nxwright partway
// could leave a folder half changed.
async function runSubcommand(name: string, args: string[],
                             doing?: string): Promise<number | undefined> {
  const command = await commandToRun();
  if (command === undefined) {
    return undefined;
  }
  return doing === undefined ? runTask(name, command, args)
    : vscode.window.withProgress({
      location: vscode.ProgressLocation.Notification, title: `nxwright: ${doing}`,
    }, () => runTask(name, command, args));
}

// Runs `command`, which starts nxwright, with `args` as a task called
// `name`. Returns the exit code once the task ends.
async function runTask(name: string, command: string[],
                       args: string[]): Promise<number | undefined> {
  const execution = new vscode.ProcessExecution(command[0], [...command.slice(1), ...args], {
    cwd: firstWorkspaceFolder(),
  });
  const task = new vscode.Task(
    { type: "nxwright", subcommand: name },
    vscode.TaskScope.Workspace,
    name,
    "nxwright",
    execution,
  );
  // This task, as VS Code tells of its end: by its name and command line,
  // since VS Code may hand back another object for it, as for a task that
  // ends before executeTask returns.
  const isThisTask = (ended: vscode.Task) => {
    const run = ended.execution as vscode.ProcessExecution | undefined;
    return ended.name === task.name && run?.process === execution.process &&
      run.args?.join("\0") === execution.args.join("\0");
  };
  // Listened to before the task starts, so that a quick one's end is not
  // missed. A task ends after its process, if it had one, so its exit code
  // is known by then.
  let exitCode: number | undefined;
  let ended!: () => void;
  const end = new Promise<void>((resolve) => { ended = resolve; });
  const listening = [
    vscode.tasks.onDidEndTaskProcess((event) => {
      if (isThisTask(event.execution.task)) {
        exitCode = event.exitCode;
      }
    }),
    vscode.tasks.onDidEndTask((event) => {
      if (isThisTask(event.execution.task)) {
        ended();
      }
    }),
  ];
  try {
    await vscode.tasks.executeTask(task);
    await end;
    return exitCode;
  } finally {
    listening.forEach((listener) => listener.dispose());
  }
}
