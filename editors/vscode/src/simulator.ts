// The simulator: a debugging session of nxwright's debug adapter that runs a
// source folder's app (nxwright/testing/simulation.py), with
//  - a panel drawing the page shown, where the mouse presses, drags, and
//    releases the screen (media/simulator.mjs); until the first page is
//    drawn, it says how far the app's start has come, as its pages compile;
//  - the Simulator section of nxwright's side bar (media/simulator-controls.mjs).
//    While a simulation runs: pause, resume, start again, the log, a field
//    for what the serial line brings the screen, and the serial port the
//    line is connected to. While none runs: simulating the current project
//    with the Simulator settings, from program.nx or from the page shown,
//    running each launch configuration that simulates it, and creating one;
//  - the button "Simulate this page" above a page file's text and its
//    preview, which simulates the app from that page while none runs;
//  - for the agent channel (agentChannelServer.ts), starting a simulation
//    an agent asks for, the serial port's state and what the user answered
//    of the agent acting with it, and the section's line saying that an
//    agent drives the simulation, with a button connecting the Simulator
//    settings' port while none is (media/simulator-agent-model.mjs).
// The adapter sends the start's progress, each drawing, and the port's
// state as custom events, and takes presses, typed instructions, starting
// again, and the port's settings as custom requests
// (nxwright/debug_adapter/adapter.py). Its log goes to the Debug Console, as
// a debugging session's output does.
import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import { isInside, sourceFolderOf } from "./activeFile";
import { AgentAnswer } from "./agentChannel";
import { CurrentProject, NO_PROJECT_ERROR } from "./currentProject";
import { Simulation, simulationsOf } from "./launchConfiguration";
import { isPageFile, Pages, tomlOf } from "./pages";
import { appName } from "./projectName";
import { SimulatorSettings, withSimulatorSettings } from "./simulatorSettings";
import { PictureFile, pictureSources, webviewPage, ZOOM_STYLES } from "./webviewPage";

// The side bar's Simulator section, as package.json declares it.
const CONTROLS_VIEW = "nxwright.simulator";
// The context key telling whether a simulation runs, which the Simulator
// section's header buttons read.
const SIMULATING = "nxwright.simulating";
// The commands the section's buttons run while no simulation runs.
const IDLE_COMMANDS = new Set(["nxwright.simulate", "nxwright.simulatePage",
                               "nxwright.addLaunchConfiguration"]);

// A drawing as the adapter sends it (nxwright/drawing/page_drawing.py), with
// the page shown, its `dim`, and whether the screen sleeps.
interface ScreenDrawing {
  page: string;
  pictureFiles?: Record<string, PictureFile>;
  [key: string]: unknown;
}

// How far a start of the app has come, as the adapter sends it: page
// `number` of `count` about to compile, or, with no page, all compiled.
interface StartProgress {
  number: number;
  count: number;
  page: string | null;
}

// The serial port's state, as the adapter sends it (serial_port.py).
export interface PortState {
  name: string | null;
  baud: number;
  connected: boolean;
}

// A GPIO pin, as the adapter sends it: its cfgpio mode, the component a
// bound pin presses, and what it reads.
interface GpioPin {
  mode: number;
  component: string | null;
  level: number;
}

// The latest start progress, drawing, GPIO pins, and serial port state of a
// simulation's session. The pins are null for a screen without GPIO.
interface SessionNews {
  starting?: StartProgress;
  drawing?: ScreenDrawing;
  pins?: GpioPin[] | null;
  port?: PortState;
}

export class Simulator implements vscode.WebviewViewProvider {
  private panel: vscode.WebviewPanel | undefined;
  private controls: vscode.WebviewView | undefined;
  private session: vscode.DebugSession | undefined;
  private lastDrawing: ScreenDrawing | undefined;
  private lastStarting: StartProgress | undefined;
  private lastPins: GpioPin[] | null | undefined;
  // The news of simulations' sessions VS Code has not announced yet. VS Code
  // announces a session once the adapter has answered its launch, and the
  // simulation may have started meanwhile.
  private unannouncedNews = new Map<vscode.DebugSession, SessionNews>();

  // The launch configurations simulating the current project, as the
  // section last showed them, by place: its buttons name them by place, as
  // two may share a name.
  private configurations: Simulation[] = [];

  // For the agent channel (agentChannelServer.ts), of the simulation
  // running: its serial port's state; whether an agent drives it, started
  // through the channel or acted on since; and what the user answered.
  private portState: PortState | undefined;
  private agentDriven = false;
  private answer: AgentAnswer;
  // The starts the channel asked for, by the mark in their launch
  // configuration: each waits for VS Code to announce its session, and
  // whether the user allowed the agent as it started.
  private agentStarts = new Map<string, { started: (session: vscode.DebugSession) => void;
                                          allowed: boolean }>();

  constructor(private readonly context: vscode.ExtensionContext,
              private readonly project: CurrentProject,
              private readonly pages: Pages) {}

  register(): vscode.Disposable[] {
    return [
      vscode.window.registerWebviewViewProvider(CONTROLS_VIEW, this),
      vscode.debug.onDidStartDebugSession((session) => this.started(session)),
      vscode.debug.onDidTerminateDebugSession((session) => this.ended(session)),
      vscode.debug.onDidReceiveDebugSessionCustomEvent((event) => this.received(event)),
      vscode.commands.registerCommand("nxwright.simulate", () => this.simulate()),
      vscode.commands.registerCommand("nxwright.simulatePage", () => this.simulatePage()),
      // VS Code gives the button the file of the editor it is above, which
      // may not be the active one. Without a file, as from a key binding,
      // it simulates from the page shown.
      vscode.commands.registerCommand(
        "nxwright.simulateThisPage",
        (file?: unknown) => file instanceof vscode.Uri
          ? this.simulateThisPage(file) : this.simulatePage()),
      vscode.commands.registerCommand("nxwright.showSimulator", () => this.showPanel()),
      // The simulation's own session: VS Code's stop command stops the
      // session with the focus, which may be a test being debugged.
      vscode.commands.registerCommand(
        "nxwright.stopSimulation",
        () => this.session && vscode.debug.stopDebugging(this.session)),
      this.project.onDidChange(() => this.offerIdle()),
      this.pages.onDidChangePage(() => this.offerIdle()),
      vscode.workspace.onDidChangeConfiguration((event) => {
        if (event.affectsConfiguration("launch")) {
          this.offerIdle();
        }
      }),
      // The simulator's settings fill in what a simulation's configuration
      // leaves out, before VS Code replaces its variables, such as
      // ${workspaceFolder}, in theirs too.
      vscode.debug.registerDebugConfigurationProvider("nxwright", {
        resolveDebugConfiguration: (folder, config) => withSimulatorSettings(
          config, simulatorSettings(folder)) as vscode.DebugConfiguration,
      }),
    ];
  }

  // Whether a simulation runs.
  get simulating(): boolean {
    return this.session !== undefined;
  }

  // The simulation running, for the agent channel: its session, its source
  // folder, and the page its last drawing shows, null before any.
  get running(): { session: vscode.DebugSession; sourceFolder: string;
                   page: string | null } | undefined {
    const session = this.session;
    return session && { session, sourceFolder: session.configuration.sourceFolder,
                        page: this.lastDrawing?.page ?? null };
  }

  // The serial port's state of the simulation running, as the adapter last
  // sent it; undefined before it did.
  get serialPort(): PortState | undefined {
    return this.portState;
  }

  // What the user answered for the simulation running, whether an agent
  // may act on it while its serial line reaches a device.
  get agentAnswer(): AgentAnswer {
    return this.answer;
  }

  // Keeps the user's `answer` for `session`, if it still runs.
  answerFor(session: vscode.DebugSession, answer: AgentAnswer): void {
    if (session === this.session) {
      this.answer = answer;
    }
  }

  // Notes that an agent acted on `session`, if it still runs.
  agentActed(session: vscode.DebugSession): void {
    if (session === this.session && !this.agentDriven) {
      this.agentDriven = true;
      this.showAgent();
    }
  }

  // The serial port the Simulator settings name for a simulation of the
  // source folder `folder`, or "" for none.
  settingsPortOf(folder: vscode.Uri): string {
    return simulatorSettings(vscode.workspace.getWorkspaceFolder(folder)).serialPort;
  }

  // Starts a simulation for the agent channel, of the source folder
  // `folder`: from program.nx, or, given `page`, from that page. Without
  // `withPort`, its serial line has no port, whatever the settings say.
  // `allowed` is whether the user already allowed the agent to act on it.
  // Returns its session, once VS Code announced it.
  async startForAgent(folder: vscode.Uri, page: string | undefined, withPort: boolean,
                      allowed: boolean): Promise<vscode.DebugSession> {
    // A mark of its own in its launch configuration tells its session apart.
    const mark = crypto.randomUUID();
    const started = new Promise<vscode.DebugSession>((resolve) =>
      this.agentStarts.set(mark, { started: resolve, allowed }));
    const launched = await this.start(folder, await this.project.nameOf(folder), page,
                                      { agentStart: mark,
                                        ...(withPort ? {} : { serialPort: null }) });
    if (!launched) {
      this.agentStarts.delete(mark);
      throw new Error("VS Code did not start the simulation");
    }
    return await started;
  }

  // Simulates the app of the current project: from program.nx, or, given
  // `page`, from that page, without running program.nx.
  private async simulate(page?: string): Promise<void> {
    const folder = this.project.folder;
    if (!folder) {
      void vscode.window.showErrorMessage(NO_PROJECT_ERROR);
      return;
    }
    await this.start(folder, appName(this.project.info, folder.fsPath), page);
  }

  // Simulates the app of the page file `file`, whichever project is current,
  // from that page, without running program.nx.
  private async simulateThisPage(file: vscode.Uri): Promise<void> {
    const toml = tomlOf(file);
    const folder = isPageFile(file) ? await sourceFolderOf(toml) : undefined;
    // A page of a source folder is its file pages/<name>.page.toml.
    if (!folder || path.dirname(toml.fsPath) !== path.join(folder.fsPath, "pages")) {
      void vscode.window.showErrorMessage(
        "nxwright: this page is not in the pages folder of a project, so there is no app to simulate.");
      return;
    }
    await this.start(folder, await this.project.nameOf(folder), pageNameOf(toml));
  }

  // Starts a simulation of the app named `name`, of the source folder
  // `folder`: from program.nx, or, given `page`, from that page, `more`
  // added to its launch configuration. Returns whether VS Code started it.
  private async start(folder: vscode.Uri, name: string, page?: string,
                      more: Record<string, unknown> = {}): Promise<boolean> {
    return await vscode.debug.startDebugging(vscode.workspace.getWorkspaceFolder(folder), {
      type: "nxwright",
      request: "launch",
      name: page === undefined ? `Simulate ${name}` : `Simulate ${name}, page ${page}`,
      sourceFolder: folder.fsPath,
      ...(page === undefined ? {} : { page }),
      ...more,
    });
  }

  // Simulates the app of the current project from the page shown.
  private async simulatePage(): Promise<void> {
    const page = this.shownPage();
    if (page === undefined) {
      void vscode.window.showErrorMessage(
        "nxwright: open a page of the current project, or its preview, first.");
      return;
    }
    await this.simulate(page);
  }

  // The name of the page shown in the page side bar (pages.ts), when it is
  // a page of the current project; or undefined.
  private shownPage(): string | undefined {
    const folder = this.project.folder;
    const toml = this.pages.shown;
    if (!folder || !toml || !isInside(toml, folder)) {
      return undefined;
    }
    return pageNameOf(toml);
  }

  private started(session: vscode.DebugSession): void {
    if (!isSimulation(session)) {
      return;
    }
    // One simulation at a time has the panel and the controls: the latest.
    // The news of other sessions not announced yet will never show.
    const news = this.unannouncedNews.get(session);
    this.unannouncedNews.clear();
    this.session = session;
    this.lastDrawing = news?.drawing;
    this.lastStarting = news?.starting;
    this.lastPins = news?.pins;
    this.portState = news?.port;
    const agentStart = this.agentStarts.get(session.configuration.agentStart);
    this.agentDriven = agentStart !== undefined;
    this.answer = agentStart?.allowed ? "yes" : undefined;
    if (agentStart) {
      this.agentStarts.delete(session.configuration.agentStart);
      agentStart.started(session);
    }
    this.showAgent();
    this.showPins();
    void vscode.commands.executeCommand("setContext", SIMULATING, true);
    this.offerIdle();
    this.openPanel(session);
  }

  // Shows the panel of the simulation running, opening it again if it was
  // closed: the simulation runs on without it.
  private showPanel(): void {
    if (this.panel) {
      this.panel.reveal();
    } else if (this.session) {
      this.openPanel(this.session);
    }
  }

  private ended(session: vscode.DebugSession): void {
    if (session !== this.session) {
      return;
    }
    this.session = undefined;
    this.lastPins = undefined;
    this.portState = undefined;
    this.agentDriven = false;
    this.answer = undefined;
    this.showAgent();
    this.showPins();
    void vscode.commands.executeCommand("setContext", SIMULATING, false);
    this.offerIdle();
    this.panel?.dispose();
  }

  private received(event: vscode.DebugSessionCustomEvent): void {
    if (event.session !== this.session) {
      const kept = event.event === "nxwright/starting" || event.event === "nxwright/drawing"
        || event.event === "nxwright/gpio" || event.event === "nxwright/serialState";
      if (kept && isSimulation(event.session)) {
        const news = this.unannouncedNews.get(event.session) ?? {};
        if (event.event === "nxwright/starting") {
          news.starting = event.body as StartProgress;
        } else if (event.event === "nxwright/gpio") {
          news.pins = (event.body as { pins: GpioPin[] | null }).pins;
        } else if (event.event === "nxwright/serialState") {
          news.port = event.body as PortState;
        } else {
          news.drawing = event.body as ScreenDrawing;
        }
        this.unannouncedNews.set(event.session, news);
      }
      return;
    }
    if (event.event === "nxwright/starting") {
      this.lastStarting = event.body as StartProgress;
      this.showStarting();
    } else if (event.event === "nxwright/drawing") {
      this.lastDrawing = event.body as ScreenDrawing;
      this.showDrawing();
    } else if (event.event === "nxwright/serialState") {
      this.portState = event.body as PortState;
      this.showAgent();
      // The adapter sends one at launch, so the section learns of the ports
      // once the simulation can answer; and the ports may have changed.
      void this.controls?.webview.postMessage({ type: "portState", state: event.body });
      void this.offerPorts();
    } else if (event.event === "nxwright/gpio") {
      this.lastPins = (event.body as { pins: GpioPin[] | null }).pins;
      this.showPins();
    }
  }

  // Tells the side bar's section whether an agent drives the simulation
  // running, with the serial port the Simulator settings name for it and
  // its rate, which the section offers to connect while none is.
  private showAgent(): void {
    const session = this.session;
    const settings = session ? simulatorSettings(session.workspaceFolder) : undefined;
    void this.controls?.webview.postMessage({
      type: "agent", driven: session !== undefined && this.agentDriven,
      port: settings?.serialPort ?? "", baud: settings?.serialBaud ?? 9600,
      connected: this.portState?.connected === true,
    });
  }

  // Lists the GPIO pins in the side bar's section, or hides them: for a
  // screen without GPIO, and while no simulation runs.
  private showPins(): void {
    void this.controls?.webview.postMessage({ type: "pins", pins: this.lastPins ?? null });
  }

  // Tells the side bar's section whether a simulation runs, and while none
  // does, the launch configurations that simulate the current project, from
  // its workspace folder's.
  private offerIdle(): void {
    const folder = this.project.folder;
    const workspaceFolder = folder && vscode.workspace.getWorkspaceFolder(folder);
    const existing = workspaceFolder
      ? vscode.workspace.getConfiguration("launch", workspaceFolder.uri)
          .get<unknown[]>("configurations") ?? []
      : [];
    this.configurations = folder && workspaceFolder
      ? simulationsOf(existing, workspaceFolder.uri.fsPath, folder.fsPath, process.platform)
      : [];
    void this.controls?.webview.postMessage({
      type: "idle", simulating: this.simulating, project: folder !== undefined,
      page: this.shownPage(), configurations: this.configurations.map((entry) => entry.name),
    });
  }

  // Starts the launch configuration at `place` among those the section
  // shows, itself, not by its name, which another may share.
  private async launch(place: number): Promise<void> {
    const folder = this.project.folder;
    const workspaceFolder = folder && vscode.workspace.getWorkspaceFolder(folder);
    const configuration = this.configurations[place];
    if (workspaceFolder && configuration) {
      await vscode.debug.startDebugging(workspaceFolder,
                                        configuration as vscode.DebugConfiguration);
    }
  }

  // Gives the side bar's section the computer's ports, the rates, and the
  // port's state.
  private async offerPorts(): Promise<void> {
    const session = this.session;
    if (!this.controls || !session) {
      return;
    }
    try {
      const offer = await session.customRequest("nxwright/serialPorts");
      void this.controls?.webview.postMessage({ type: "ports", ...offer });
    } catch {
      // The session ended meanwhile.
    }
  }

  // Connects the port `name` at `baud`, or disconnects when `name` is empty.
  // A port the user connects while an agent drives the simulation, which
  // the section shows, allows the agent to act on it.
  private async choosePort(name: string, baud?: number): Promise<void> {
    if (name && this.agentDriven) {
      this.answer = "yes";
    }
    try {
      const answer = await this.session?.customRequest("nxwright/serialPort", { name, baud });
      if (answer) {
        void this.controls?.webview.postMessage({ type: "portState", state: answer.state });
      }
    } catch {
      // The session ended meanwhile.
    }
  }

  // The panel beside the editors, drawing the page `session` shows. It may
  // load the source folder's pictures and the files of the SD cards'
  // folders. Opened again, it draws the last drawing as soon as it is ready.
  private openPanel(session: vscode.DebugSession): void {
    this.panel?.dispose();
    const sourceFolder = vscode.Uri.file(session.configuration.sourceFolder);
    // The SD cards given folders: external pictures show their files. The
    // adapter names a file by its card folder's real path, so a folder named
    // through a link is allowed under both.
    const cards = ["sdCard0", "sdCard1"]
      .map((setting) => session.configuration[setting])
      .filter((folder): folder is string => typeof folder === "string" && folder !== "")
      .flatMap((folder) => [folder, realPath(folder)])
      .map((folder) => vscode.Uri.file(folder));
    const panel = vscode.window.createWebviewPanel(
      "nxwrightSimulator",
      "Simulator",
      { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media"),
                             vscode.Uri.joinPath(sourceFolder, "pictures"), ...cards],
      },
    );
    panel.webview.html = webviewPage(panel.webview, this.context.extensionUri, {
      script: "simulator.mjs", styles: `${STYLES}${ZOOM_STYLES}
  #zoom { margin-bottom: 6px; }`,
      allowImages: true,
      body: '<div id="starting">Starting the simulation</div>' +
        '<div id="zoom" class="zoom" hidden></div><canvas id="screen" hidden></canvas>',
    });
    panel.webview.onDidReceiveMessage((message) => {
      if (message.type === "ready") {
        this.showStarting();
        this.showDrawing();
      } else if (message.type === "press") {
        void this.session?.customRequest("nxwright/press", { x: message.x, y: message.y });
      } else if (message.type === "move") {
        void this.session?.customRequest("nxwright/move", { x: message.x, y: message.y });
      } else if (message.type === "release") {
        void this.session?.customRequest("nxwright/release");
      }
    });
    panel.onDidDispose(() => {
      if (this.panel === panel) {
        this.panel = undefined;
      }
    });
    this.panel = panel;
  }

  private showStarting(): void {
    if (this.lastStarting) {
      void this.panel?.webview.postMessage({ type: "starting", progress: this.lastStarting });
    }
  }

  private showDrawing(): void {
    const drawing = this.lastDrawing;
    if (!this.panel || !drawing) {
      return;
    }
    this.panel.title = `Simulator: ${drawing.page}`;
    const { pictureUris, pictureMasks } = pictureSources(this.panel.webview,
                                                         drawing.pictureFiles ?? {});
    void this.panel.webview.postMessage({ type: "drawing", drawing, pictureUris, pictureMasks });
  }

  // The side bar's Simulator section.
  resolveWebviewView(view: vscode.WebviewView): void {
    this.controls = view;
    view.onDidDispose(() => {
      if (this.controls === view) {
        this.controls = undefined;
      }
    });
    // Shown again: the ports may have changed meanwhile.
    view.onDidChangeVisibility(() => {
      if (view.visible) {
        void this.offerPorts();
      }
    });
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media")],
    };
    view.webview.html = webviewPage(view.webview, this.context.extensionUri, {
      script: "simulator-controls.mjs", styles: STYLES, body: `
<div id="idle" hidden>
  <p id="idle-note"></p>
  <div id="idle-buttons" class="idle-buttons"></div>
</div>
<div id="running" hidden>
<div id="agent" hidden>
  <p id="agent-note"></p>
  <button id="agent-connect" hidden></button>
</div>
<div class="buttons">
  <button data-command="pause">Pause</button>
  <button data-command="resume">Resume</button>
  <button data-command="startAgain">Start again</button>
  <button data-command="show">Show the screen</button>
  <button data-command="log">Open the log</button>
</div>
<form id="serial">
  <label for="instruction">Serial input</label>
  <input id="instruction" placeholder='t0.txt="hello"' autocomplete="off">
  <button type="submit">Send</button>
</form>
<div id="port-group">
  <label for="port">Serial port</label>
  <div class="row">
    <select id="port" title="The computer's serial port"></select>
    <select id="rate" title="Its rate, in bits per second"></select>
    <button id="connect">Connect</button>
  </div>
  <div id="port-state"></div>
</div>
<div id="pins-group" hidden>
  <label>GPIO pins</label>
  <div id="pins"></div>
</div>
</div>`,
    });
    view.webview.onDidReceiveMessage((message) => {
      // To the simulation's own session, whichever debug session has the focus.
      if (message.type === "ready") {
        this.offerIdle();
        void this.offerPorts();
        this.showPins();
        this.showAgent();
      } else if (message.type === "openSettings") {
        // The settings a simulation takes its defaults from.
        void vscode.commands.executeCommand("workbench.action.openSettings", "nxwright.simulator");
      } else if (message.type === "run" && IDLE_COMMANDS.has(message.command)) {
        void vscode.commands.executeCommand(message.command);
      } else if (message.type === "launch" && Number.isInteger(message.place)) {
        void this.launch(message.place);
      } else if (message.type === "pause") {
        void this.session?.customRequest("pause", { threadId: 1 });
      } else if (message.type === "resume") {
        void this.session?.customRequest("continue", { threadId: 1 });
      } else if (message.type === "startAgain") {
        void this.session?.customRequest("nxwright/startAgain");
      } else if (message.type === "show") {
        this.showPanel();
      } else if (message.type === "log") {
        void vscode.commands.executeCommand("workbench.debug.action.focusRepl");
      } else if (message.type === "serial" && message.text) {
        void this.session?.customRequest("nxwright/serial", { text: message.text });
      } else if (message.type === "connect" && message.name) {
        void this.choosePort(message.name, message.baud);
      } else if (message.type === "disconnect") {
        void this.choosePort("");
      } else if (message.type === "pin" && Number.isInteger(message.pin)
                 && (message.level === 0 || message.level === 1)) {
        void this.session?.customRequest("nxwright/gpioInput",
                                         { pin: message.pin, level: message.level });
      }
    });
  }
}

// The styles of the simulator's panel and section.
const STYLES = `
  body { padding: 8px; font-size: 12px; }
  canvas { display: block; background: #000; }
  #starting {
    position: fixed; inset: 0; display: flex; align-items: center; justify-content: center;
    font-size: 13px; color: var(--vscode-descriptionForeground);
  }
  #starting[hidden], #screen[hidden] { display: none; }
  .buttons { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
  button {
    color: var(--vscode-button-foreground); background: var(--vscode-button-background);
    border: none; padding: 4px 8px; cursor: pointer;
  }
  button:hover { background: var(--vscode-button-hoverBackground); }
  form, .row { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
  label { width: 100%; }
  input, select {
    flex: 1; min-width: 0; color: var(--vscode-input-foreground);
    background: var(--vscode-input-background);
    border: 1px solid var(--vscode-input-border, transparent);
  }
  #port-group { margin-top: 10px; }
  #port-state { margin-top: 4px; color: var(--vscode-descriptionForeground); }
  #port-state.problem { color: var(--vscode-errorForeground); }
  #pins-group { margin-top: 10px; }
  #pins-group[hidden] { display: none; }
  #pins { display: grid; grid-template-columns: auto 1fr auto; gap: 2px 8px; align-items: center; }
  #pins button { padding: 0 8px; min-width: 2em; }
  #idle[hidden], #running[hidden] { display: none; }
  #agent { margin-bottom: 10px; }
  #agent[hidden], #agent-connect[hidden] { display: none; }
  #agent-note { margin: 0 0 6px; }
  #idle-note { margin: 0 0 8px; color: var(--vscode-descriptionForeground); }
  #idle-note a { color: var(--vscode-textLink-foreground); }
  .idle-buttons { display: flex; flex-direction: column; gap: 6px; }
  .idle-buttons button {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    padding: 4px 10px; font: inherit;
  }
  .idle-buttons button.secondary {
    color: var(--vscode-button-secondaryForeground);
    background: var(--vscode-button-secondaryBackground);
  }
  .idle-buttons button.secondary:hover {
    background: var(--vscode-button-secondaryHoverBackground);
  }
  .idle-buttons svg {
    flex: none; width: 16px; height: 16px; fill: none; stroke: currentColor;
    stroke-width: 1.2; stroke-linecap: round; stroke-linejoin: round;
  }`;

// Whether a debugging session is a simulation: nxwright's, naming a source folder.
function isSimulation(session: vscode.DebugSession): boolean {
  return session.type === "nxwright" && !!session.configuration.sourceFolder;
}

// The name of the page whose file is `toml`, pages/<name>.page.toml.
function pageNameOf(toml: vscode.Uri): string {
  return path.basename(toml.fsPath).replace(/\.page\.toml$/, "");
}

// The simulator's settings, nxwright.simulator.*, for a workspace folder.
function simulatorSettings(folder: vscode.WorkspaceFolder | undefined): SimulatorSettings {
  const settings = vscode.workspace.getConfiguration("nxwright.simulator", folder?.uri);
  return {
    serialPort: settings.get<string>("serialPort", ""),
    serialBaud: settings.get<number>("serialBaud", 9600),
    sdCard0: settings.get<string>("sdCard0", ""),
    sdCard1: settings.get<string>("sdCard1", ""),
    logReceived: settings.get<string>("logReceived", "text"),
    logSent: settings.get<string>("logSent", "hex"),
    pinyinTable: settings.get<string>("pinyinTable", ""),
  };
}

// A path with its links followed, or as it is when it cannot be followed.
function realPath(folder: string): string {
  try {
    return fs.realpathSync.native(folder);
  } catch {
    return folder;
  }
}
