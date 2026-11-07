// The Project section of nxwright's side bar, at its top. With a current
// project (currentProject.ts), it shows the project's settings, as the
// language server gives them, then the chain from the source folder to the
// screen: the project file, with Build HMI, the TFT file, with Compile TFT,
// and the screen, with Upload TFT (tftCommands.ts). Without one, it offers
// to create a project or import one, and, with several in the workspace, to
// choose one. Its page (media/project.mjs)
// draws what this sends it. The section's header buttons are package.json's.
import * as path from "path";
import * as vscode from "vscode";
import { CurrentProject, projectFileKey } from "./currentProject";
import { appName } from "./projectName";
import { ScreenChoice, chosenScreen, projectFileLinked, tftFileKey } from "./tftFiles";
import { webviewPage } from "./webviewPage";

// The side bar's Project section, as package.json declares it.
const PROJECT_VIEW = "nxwright.project";

// The commands the page's buttons run, and no others.
const PAGE_COMMANDS = new Set(["nxwright.build", "nxwright.compile", "nxwright.chooseTftFile",
                               "nxwright.toggleProjectFileLink", "nxwright.upload",
                               "nxwright.chooseScreen", "nxwright.newSourceFolder",
                               "nxwright.importProject", "nxwright.chooseProject",
                               "nxwright.switchToNxlang", "nxwright.chooseProjectFile",
                               "nxwright.changeScreen", "nxwright.changeRotation",
                               "nxwright.changeEncoding"]);

// What the page draws.
export interface ProjectShown {
  // The project's folder's name and path, and what the server says of it,
  // or null before it answers; with the project file Build writes and the
  // TFT file Compile writes, when chosen, and whether Compile also writes
  // the project file; and the screen Upload sends to, once chosen.
  project?: {
    name: string;
    path: string;
    info: unknown;
    projectFile?: string;
    tftFile?: string;
    linked: boolean;
    screen?: ScreenChoice;
  };
  // Without a project: how many source folders the workspace holds.
  folders: number;
}

export class ProjectView implements vscode.WebviewViewProvider {
  private view: vscode.WebviewView | undefined;

  constructor(private readonly context: vscode.ExtensionContext,
              private readonly project: CurrentProject) {}

  register(): vscode.Disposable[] {
    return [
      vscode.window.registerWebviewViewProvider(PROJECT_VIEW, this),
      this.project.onDidChange(() => this.refresh()),
    ];
  }

  // A file chosen for a folder, or whether Compile also writes the project
  // file, changed, which the section shows.
  projectFileChanged(): void {
    this.refresh();
  }

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.onDidDispose(() => {
      if (this.view === view) {
        this.view = undefined;
      }
    });
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media")],
    };
    view.webview.html = webviewPage(view.webview, this.context.extensionUri, {
      script: "project.mjs", styles: STYLES, body: '<div id="project"></div>',
    });
    view.webview.onDidReceiveMessage((message) => {
      if (message.type === "ready") {
        this.refresh();
      } else if (message.type === "run" && PAGE_COMMANDS.has(message.command)) {
        void vscode.commands.executeCommand(message.command);
      }
    });
  }

  private refresh(): void {
    const folder = this.project.folder;
    const shown: ProjectShown = { folders: this.project.folders.length };
    if (folder) {
      shown.project = {
        name: appName(this.project.info, folder.fsPath),
        path: folder.fsPath,
        info: this.project.info,
        projectFile: this.context.workspaceState.get<string>(projectFileKey(folder)),
        tftFile: this.context.workspaceState.get<string>(tftFileKey(folder)),
        linked: projectFileLinked(this.context, folder),
        screen: chosenScreen(this.context),
      };
    }
    void this.view?.webview.postMessage({ type: "project", shown });
  }
}

// The styles of the section: lines of settings, and text buttons with their
// glyphs, in the theme's button colours.
const STYLES = `
  body { padding: 4px 8px 8px; }
  h2 { margin: 4px 0 0; font-size: 13px; }
  .note { margin: 6px 0; color: var(--vscode-descriptionForeground); }
  .line { margin: 2px 0; overflow-wrap: break-word; }
  .value { white-space: nowrap; }
  /* A file's name, a value with its path as the tooltip, may be too long to
     keep whole: it wraps rather than make the section scroll sideways. */
  .value[title] { white-space: normal; overflow-wrap: anywhere; }
  .line:first-of-type { margin-top: 6px; }
  a { color: var(--vscode-textLink-foreground); }
  .buttons { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
  button {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    padding: 4px 10px; border: none; border-radius: 2px; cursor: pointer; font: inherit;
    color: var(--vscode-button-foreground); background: var(--vscode-button-background);
  }
  button:hover { background: var(--vscode-button-hoverBackground); }
  /* The background keeps a disabled button from changing colour on hover. */
  button:disabled {
    cursor: default; opacity: 0.4; background: var(--vscode-button-background);
  }
  button:focus-visible { outline: 1px solid var(--vscode-focusBorder); outline-offset: 2px; }
  button.secondary {
    color: var(--vscode-button-secondaryForeground);
    background: var(--vscode-button-secondaryBackground);
  }
  button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
  button.edit {
    display: inline-flex; vertical-align: middle; margin-left: 2px; padding: 1px;
    color: var(--vscode-icon-foreground); background: transparent;
  }
  button.edit:hover { background: var(--vscode-toolbar-hoverBackground); }
  /* The chain is a grid. The buttons fill the left column, all the same
     width, and each button's file or screen sits in the right column, where
     a long name wraps. When the section is too narrow for two columns, each
     value goes under its button. */
  .chain {
    display: grid; grid-template-columns: max-content minmax(0, 1fr);
    gap: 6px 8px; align-items: center; margin-top: 10px;
  }
  @media (max-width: 260px) {
    .chain { grid-template-columns: minmax(0, 1fr); }
    .chain > button:not(:first-child) { margin-top: 4px; }
  }
  .file { overflow-wrap: anywhere; }
  .tools { white-space: nowrap; }
  /* The link button, VS Code's toggle: highlighted when on, dimmed when off. */
  button.toggle {
    display: inline-flex; vertical-align: middle; margin-left: 2px; padding: 1px;
    border: 1px solid transparent; color: var(--vscode-icon-foreground);
    background: transparent; opacity: 0.5;
  }
  button.toggle:hover { background: var(--vscode-toolbar-hoverBackground); opacity: 1; }
  button.toggle.on {
    opacity: 1; color: var(--vscode-inputOption-activeForeground);
    background: var(--vscode-inputOption-activeBackground);
    border-color: var(--vscode-inputOption-activeBorder);
  }
  svg {
    flex: none; width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.2;
    stroke-linecap: round; stroke-linejoin: round;
  }`;
