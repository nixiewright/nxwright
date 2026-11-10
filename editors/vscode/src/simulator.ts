// The simulator: a debugging session of nxwright's debug adapter that runs a
// source folder's app (nxwright/testing/simulation.py), with
//  - a panel drawing the page shown, where the mouse presses, drags, and
//    releases the screen (media/simulator.mjs); until the first page is
//    drawn, it says how far the app's start has come, as its pages compile;
//  - the Simulator section of nxwright's side bar (media/simulator-controls.mjs).
//    While a simulation runs, it has pause, resume, start again, the log, the
//    button opening the Signal generator panel (signalGenerators.ts), a
//    field for what the serial line brings the screen, and the MCU port the
//    line is connected to: none, a serial port, a program that listens at
//    an address over TCP, or the port that listens for the project's MCU
//    emulator. The port chosen there is remembered for the project
//    (simulatorSettings.ts). While the port listens for the emulator, a
//    button starts the emulator again. The section also has a port for a real
//    screen beside the simulation. The field can send that screen
//    instructions too, a button starts it again, and the MCU port can be
//    joined to it, in place of the simulator or beside it. While no simulation runs,
//    the section can simulate the current project with the MCU port last
//    chosen for that project and the Simulator settings, from program.nx or
//    from the page shown, run each launch configuration that simulates the
//    project, and create one;
//  - the button "Simulate this page" above a page file's text and its
//    preview, which simulates the app from that page while none runs;
//  - for the agent channel (agentChannelServer.ts): starting a simulation
//    an agent asks for, the MCU port's state, and what the user answered
//    when asked whether the agent may act while a port is connected. The
//    section has a line saying that an agent drives the simulation. While
//    no port is connected, that line has a button that connects the port a
//    simulation of the project would start with
//    (media/simulator-agent-model.mjs);
//  - the project's MCU emulator, started beside the simulation while the
//    MCU port listens for it. The emulator runs through the Python
//    debugger, in a session that is a child of the simulation's
//    (emulatorSession.ts).
// The adapter sends the start's progress, each drawing, the points of the
// page's waveforms when they alone changed, and the ports' states as custom
// events, and takes presses, typed instructions, starting again, and the
// ports' settings as custom requests
// (nxwright/debug_adapter/adapter.py). Its log goes to the Debug Console, as
// a debugging session's output does.
import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import { isInside, sourceFolderOf } from "./activeFile";
import { AgentAnswer } from "./agentChannel";
import { CurrentProject, NO_PROJECT_ERROR } from "./currentProject";
import { ADDRESS_VARIABLE, emulatorConfiguration, emulatorStep, listeningAddress,
         PYTHON_DEBUGGER_EXTENSION } from "./emulatorSession";
import { Simulation, simulationsOf } from "./launchConfiguration";
import { isPageFile, Pages, tomlOf } from "./pages";
import { appName } from "./projectName";
import { DefaultPort, defaultPort, PortChoice, portChoiceKey, ProjectPorts, SimulatorSettings,
         sourceFolderPath, withSimulatorSettings } from "./simulatorSettings";
import { SignalGeneratorPanel } from "./signalGenerators";
import { PictureFile, pictureSources, webviewPage, ZOOM_STYLES } from "./webviewPage";

// The side bar's Simulator section, as package.json declares it.
const CONTROLS_VIEW = "nxwright.simulator";
// The context key telling whether a simulation runs, which the Simulator
// section's header buttons read.
const SIMULATING = "nxwright.simulating";
// The commands the section's buttons run while no simulation runs.
const IDLE_COMMANDS = new Set(["nxwright.simulate", "nxwright.simulatePage",
                               "nxwright.addLaunchConfiguration"]);
// How long to wait for an emulator's session to end before another starts,
// in milliseconds.
const EMULATOR_END_WAIT = 5000;

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

// The MCU port's state, as the adapter sends it (serial_port.py). The port
// is a serial port, a program over TCP, or the port that listens for the
// project's MCU emulator. For the last two, `name` is an address, and `baud`
// is null. The emulator's port is connected from the moment it listens, and
// `attached` is whether an emulator is connected to it.
export interface PortState {
  kind: "serial" | "tcp" | "emulator";
  name: string | null;
  baud: number | null;
  connected: boolean;
  attached?: boolean;
}

// The MCU port the side bar's section asks to connect: a serial port at a
// rate, the program listening at an address, or the port that listens for
// the project's MCU emulator.
type PortToConnect = { name: string; baud: number } | { tcp: string } | { emulator: true };

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
  // The waveforms' points the adapter sent on their own since the last
  // drawing, which a panel opened again paints over it.
  private lastWaves: unknown;
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
  // How many times showAgent was called. A call that is no longer the
  // latest does not tell the section.
  private agentShown = 0;
  // The starts the channel asked for, by the mark in their launch
  // configuration: each waits for VS Code to announce its session, and
  // whether the user allowed the agent as it started.
  private agentStarts = new Map<string, { started: (session: vscode.DebugSession) => void;
                                          allowed: boolean }>();

  // The sessions that run MCU emulators, each by its simulation's session.
  private emulators = new Map<vscode.DebugSession, vscode.DebugSession>();
  // For the simulation running, the address at which the MCU port listened
  // when the emulator was last started. Undefined if the emulator was not
  // started, or was stopped since (emulatorStep).
  private emulatorStartedFor: string | undefined;
  // The starts and stops of emulators still to do. They are done one after
  // the other, so that an emulator has ended before the next one starts.
  private emulatorWork: Promise<void> = Promise.resolve();
  // Whether the user was told that the emulator needs the Python debugger.
  private toldNoDebugger = false;

  // The Signal generator panel of the simulation running.
  private readonly generatorPanel: SignalGeneratorPanel;

  constructor(private readonly context: vscode.ExtensionContext,
              private readonly project: CurrentProject,
              private readonly pages: Pages) {
    this.generatorPanel = new SignalGeneratorPanel(context.extensionUri);
  }

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
      // leaves out. This happens before VS Code replaces variables such as
      // ${workspaceFolder}, so that VS Code replaces them in the settings'
      // values too. The MCU port last chosen for the project comes before
      // the settings' port, and the project's MCU emulator after it.
      vscode.debug.registerDebugConfigurationProvider("nxwright", {
        resolveDebugConfiguration: async (folder, config) => withSimulatorSettings(
          config, simulatorSettings(folder),
          await this.projectPorts(config.sourceFolder, folder)) as vscode.DebugConfiguration,
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
      void this.showAgent();
    }
  }

  // The MCU port that a simulation of the source folder `folder` takes when
  // its launch configuration gives none: the port last chosen for the
  // project in the section, or else the Simulator settings' port, or else
  // the project's MCU emulator (simulatorSettings.ts).
  async defaultPortOf(folder: vscode.Uri): Promise<DefaultPort> {
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(folder);
    return defaultPort(simulatorSettings(workspaceFolder),
                       await this.projectPorts(folder.fsPath, workspaceFolder));
  }

  // Returns the MCU port the user last chose in the section for the project
  // in `sourceFolder`, whether that project has an MCU emulator, and whether
  // the extension can start it. The port
  // is undefined if the user has not chosen yet. Choosing None counts as a
  // choice. `sourceFolder` comes from a launch configuration, so it may
  // contain ${workspaceFolder}, which stands for the workspace folder
  // `folder`.
  private async projectPorts(sourceFolder: unknown,
                             folder: vscode.WorkspaceFolder | undefined): Promise<ProjectPorts> {
    if (typeof sourceFolder !== "string" || !sourceFolder) {
      return { hasEmulator: false };
    }
    const workspaceFolder = folder?.uri.fsPath;
    const emulator = await this.project.emulatorOf(
      vscode.Uri.file(path.resolve(sourceFolderPath(sourceFolder, workspaceFolder))));
    return {
      remembered: this.context.workspaceState.get<PortChoice>(
        portChoiceKey(sourceFolder, process.platform, workspaceFolder)),
      hasEmulator: emulator !== undefined,
      startsEmulator: emulator !== undefined && hasPythonDebugger(),
    };
  }

  // Remembers `choice` as the MCU port of the project being simulated. Then
  // updates the section's line about the agent, whose button offers that
  // port (showAgent).
  private async rememberPort(choice: PortChoice): Promise<void> {
    const sourceFolder = this.session?.configuration.sourceFolder;
    if (typeof sourceFolder === "string" && sourceFolder) {
      await this.context.workspaceState.update(
        portChoiceKey(sourceFolder, process.platform), choice);
      void this.showAgent();
    }
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
    const simulation = session.parentSession;
    if (simulation && isSimulation(simulation)
        && session.configuration.env?.[ADDRESS_VARIABLE] !== undefined) {
      this.emulators.set(simulation, session);
      return;
    }
    if (!isSimulation(session)) {
      return;
    }
    // One simulation at a time has the panel and the controls: the latest.
    // The news of other sessions not announced yet will never show.
    const news = this.unannouncedNews.get(session);
    this.unannouncedNews.clear();
    // The previous simulation's generators ended with that simulation, so
    // their panel closes.
    this.generatorPanel.close();
    this.session = session;
    this.lastDrawing = news?.drawing;
    this.lastWaves = undefined;
    this.lastStarting = news?.starting;
    this.lastPins = news?.pins;
    this.portState = news?.port;
    this.emulatorStartedFor = undefined;
    this.followEmulatorPort();
    const agentStart = this.agentStarts.get(session.configuration.agentStart);
    this.agentDriven = agentStart !== undefined;
    this.answer = agentStart?.allowed ? "yes" : undefined;
    if (agentStart) {
      this.agentStarts.delete(session.configuration.agentStart);
      agentStart.started(session);
    }
    void this.showAgent();
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
    for (const [simulation, emulator] of this.emulators) {
      if (session === emulator) {
        this.emulators.delete(simulation);
      } else if (session === simulation) {
        // An emulator ends by itself when its simulation closes the
        // connection, but not while it is stopped at a breakpoint.
        this.emulators.delete(simulation);
        void endSession(emulator);
      }
    }
    if (session !== this.session) {
      return;
    }
    this.session = undefined;
    this.emulatorStartedFor = undefined;
    this.lastPins = undefined;
    this.portState = undefined;
    this.agentDriven = false;
    this.answer = undefined;
    void this.showAgent();
    this.showPins();
    void vscode.commands.executeCommand("setContext", SIMULATING, false);
    this.offerIdle();
    this.panel?.dispose();
    this.generatorPanel.close();
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
      this.lastWaves = undefined;
      this.showDrawing();
    } else if (event.event === "nxwright/waves") {
      this.lastWaves = event.body;
      this.showWaves();
    } else if (event.event === "nxwright/serialState") {
      this.portState = event.body as PortState;
      this.followEmulatorPort();
      void this.showAgent();
      // The adapter sends one at launch, so the section learns of the ports
      // once the simulation can answer; and the ports may have changed.
      void this.controls?.webview.postMessage({ type: "portState", state: event.body });
      void this.offerPorts();
    } else if (event.event === "nxwright/screenState") {
      void this.controls?.webview.postMessage({ type: "screenState", state: event.body });
    } else if (event.event === "nxwright/bridgeState") {
      void this.controls?.webview.postMessage({ type: "bridgeState", ...event.body });
    } else if (event.event === "nxwright/gpio") {
      this.lastPins = (event.body as { pins: GpioPin[] | null }).pins;
      this.showPins();
    }
  }

  // Tells the side bar's section whether an agent drives the simulation
  // running, and which MCU port a simulation of its project would start with
  // (defaultPortOf). While no port is connected, the section offers to
  // connect that port. The port is null when such a simulation would start
  // without one.
  private async showAgent(): Promise<void> {
    // Only the latest call tells the section. An earlier call that is still
    // waiting for the project's port would otherwise show a port that is out
    // of date.
    const shown = ++this.agentShown;
    const session = this.session;
    const port = session
      ? await this.defaultPortOf(vscode.Uri.file(session.configuration.sourceFolder))
      : undefined;
    if (shown !== this.agentShown) {
      return;
    }
    // A launch configuration gives the emulator's port as "emulator". The
    // request that connects the port takes { emulator: true }.
    const connection = port?.serialPort === "emulator" ? { emulator: true } : port?.serialPort;
    void this.controls?.webview.postMessage({
      type: "agent", driven: this.session !== undefined && this.agentDriven,
      port: port?.shown ? { shown: port.shown, connection } : null,
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
  // states of the MCU port and of the screen port. Also says whether the
  // project has an MCU emulator, so that the section can list Emulator, and
  // whether the extension can start it, so that the section can offer to
  // start it again.
  private async offerPorts(): Promise<void> {
    const session = this.session;
    if (!this.controls || !session) {
      return;
    }
    try {
      const offer = await session.customRequest("nxwright/serialPorts");
      const emulator = await this.project.emulatorOf(
        vscode.Uri.file(session.configuration.sourceFolder));
      void this.controls?.webview.postMessage({
        type: "ports", ...offer, emulator: emulator !== undefined,
        emulatorStarts: emulator !== undefined && hasPythonDebugger(),
      });
    } catch {
      // The session ended meanwhile.
    }
  }

  // Connects the MCU port `port`, and remembers it for the project. If an
  // agent is driving the simulation, connecting also counts as the user's
  // permission for the agent to act on it, because the section shows the
  // user that an agent is driving.
  private async connectPort(port: PortToConnect): Promise<void> {
    if (this.agentDriven) {
      this.answer = "yes";
    }
    await this.rememberPort("emulator" in port ? { kind: "emulator" }
      : "tcp" in port ? { kind: "tcp", address: port.tcp }
        : { kind: "serial", name: port.name, baud: port.baud });
    await this.requestPort(port);
  }

  // Disconnects the MCU port. The port remembered for the project stays.
  private async disconnectPort(): Promise<void> {
    await this.requestPort({ name: "" });
  }

  // Remembers that the project's simulations take no MCU port, and
  // disconnects the one connected.
  private async chooseNoPort(): Promise<void> {
    await this.rememberPort({ kind: "none" });
    await this.requestPort({ name: "" });
  }

  // Asks the adapter to connect the MCU port `port`, or, given an empty
  // name, to disconnect it. Then shows the port's state.
  private async requestPort(port: PortToConnect | { name: "" }): Promise<void> {
    try {
      const answer = await this.session?.customRequest("nxwright/serialPort", port);
      if (answer) {
        void this.controls?.webview.postMessage({ type: "portState", state: answer.state });
      }
    } catch {
      // The session ended meanwhile.
    }
  }

  // Starts or stops the emulator's session to match the MCU port's state
  // (emulatorStep).
  private followEmulatorPort(): void {
    const session = this.session;
    if (!session || emulatorStep(this.portState, this.emulatorStartedFor) === "keep") {
      return;
    }
    this.restartEmulator(session);
  }

  // Ends the emulator's session of the simulation `session`, if it has one.
  // Then, if the MCU port listens for the emulator, starts the emulator for
  // the address the port listens at.
  private restartEmulator(session: vscode.DebugSession): void {
    const address = listeningAddress(this.portState);
    this.emulatorStartedFor = address;
    this.emulatorWork = this.emulatorWork.then(async () => {
      await this.stopEmulator(session);
      if (address !== undefined) {
        await this.startEmulator(session, address);
      }
    }).catch(() => undefined);
  }

  // Starts the project's MCU emulator beside the simulation `session`.
  // `address` is where the simulation listens for the emulator, and goes
  // into the emulator's environment. The emulator is debugged only if the
  // simulation is debugged. Nothing starts if the project has no emulator,
  // or if the port stopped listening at `address` meanwhile. Without the
  // Python debugger, nothing starts either, and the user is told why once.
  private async startEmulator(session: vscode.DebugSession, address: string): Promise<void> {
    const sourceFolder = vscode.Uri.file(session.configuration.sourceFolder);
    const file = await this.project.emulatorOf(sourceFolder);
    if (file === undefined || session !== this.session
        || listeningAddress(this.portState) !== address) {
      return;
    }
    if (!hasPythonDebugger()) {
      if (!this.toldNoDebugger) {
        this.toldNoDebugger = true;
        void vscode.window.showWarningMessage(
          "nxwright: Cannot start the MCU emulator because the Python Debugger extension " +
          "is not installed. Please install it, or start the emulator yourself with " +
          `${ADDRESS_VARIABLE} set to the address that the Simulator section shows.`);
      }
      return;
    }
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(sourceFolder);
    const existing = workspaceFolder
      ? vscode.workspace.getConfiguration("launch", workspaceFolder.uri)
          .get<unknown[]>("configurations") ?? []
      : [];
    const configuration = emulatorConfiguration(
      file, address, existing, workspaceFolder?.uri.fsPath, process.platform);
    // Ending the emulator's session must not end the simulation, so the
    // parent does not manage the child's lifecycle.
    await vscode.debug.startDebugging(
      workspaceFolder, configuration as vscode.DebugConfiguration,
      { parentSession: session, noDebug: session.configuration.noDebug === true });
  }

  // Ends the emulator's session of the simulation `session`, if the
  // simulation has one. Waits for that session to end, so that the emulator
  // has left the port.
  private async stopEmulator(session: vscode.DebugSession): Promise<void> {
    const emulator = this.emulators.get(session);
    if (!emulator) {
      return;
    }
    const ended = new Promise<void>((resolve) => {
      const done = () => {
        listening.dispose();
        clearTimeout(limit);
        resolve();
      };
      const listening = vscode.debug.onDidTerminateDebugSession((terminated) => {
        if (terminated === emulator) {
          done();
        }
      });
      const limit = setTimeout(done, EMULATOR_END_WAIT);
    });
    await endSession(emulator);
    await ended;
  }

  // Starts the real screen again, then the simulation, each with `rest`.
  // The simulation starts again even if the screen's request is refused.
  private async startBothAgain(): Promise<void> {
    for (const [command, args] of [["nxwright/startScreenAgain", {}],
                                   ["nxwright/serial", { text: "rest" }]] as const) {
      try {
        await this.session?.customRequest(command, args);
      } catch {
        // Refused, or the session ended meanwhile.
      }
    }
  }

  // Joins the MCU port to what `choice`, the value of Goes to, selects
  // (BRIDGE_CHOICES), then shows the bridge's state. If the debug adapter
  // refuses, for example because a port is not connected, it shows the ports
  // as not joined.
  private async joinPorts(choice: string): Promise<void> {
    const args = BRIDGE_CHOICES[choice];
    let state = { bridged: false, simulator: null };
    if (args) {
      try {
        state = (await this.session?.customRequest("nxwright/bridge", args)) ?? state;
      } catch {
        // Refused, or the session ended meanwhile.
      }
    }
    void this.controls?.webview.postMessage({ type: "bridgeState", ...state });
  }

  // Sends the request `command` to connect, find, or disconnect the screen
  // port, then shows the port's state. If the request fails, such as a
  // second Find while one runs, it shows the state from
  // "nxwright/serialPorts" instead.
  private async chooseScreenPort(command: string, args: object): Promise<void> {
    const session = this.session;
    let state: unknown;
    try {
      state = (await session?.customRequest(command, args))?.state;
    } catch {
      try {
        state = (await session?.customRequest("nxwright/serialPorts"))?.screen;
      } catch {
        // The session ended meanwhile.
      }
    }
    if (state) {
      void this.controls?.webview.postMessage({ type: "screenState", state });
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
        this.showWaves();
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

  // Has the panel paint the waveforms' points sent since the last drawing.
  private showWaves(): void {
    if (this.lastWaves !== undefined) {
      void this.panel?.webview.postMessage({ type: "waves", waves: this.lastWaves });
    }
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
  <button data-command="generator">Signal generator</button>
</div>
<form id="serial">
  <label for="instruction">Serial input</label>
  <input id="instruction" placeholder='t0.txt="hello"' autocomplete="off">
  <button type="submit">Send</button>
  <div id="destinations" class="row" hidden>
    <label class="check"><input type="checkbox" id="to-simulator" checked>To the simulator</label>
    <label class="check"><input type="checkbox" id="to-screen" checked>To the screen</label>
  </div>
</form>
<div id="port-group" class="port-group">
  <label for="port">MCU port</label>
  <div class="row">
    <select id="port"
            title="What the screen talks to: a port, a program, or the MCU emulator"></select>
    <select id="rate" title="Its rate, in bits per second"></select>
    <input id="address" placeholder="127.0.0.1:7000" autocomplete="off" hidden
           title="The address the program listens at: a host and a port number">
    <button id="connect">Connect</button>
  </div>
  <div id="port-state" class="port-state"></div>
  <div id="emulator-starts" class="buttons" hidden>
    <button id="start-emulator">Start the emulator again</button>
  </div>
  <div id="bridge-row" class="row" hidden>
    <label for="bridge" class="inline">Goes to</label>
    <select id="bridge">
      <option value="simulator">the simulator</option>
      <option value="screen">the real screen</option>
      <option value="both-screen">both, the real screen answering</option>
      <option value="both-simulator">both, the simulator answering</option>
    </select>
  </div>
</div>
<div id="screen-group" class="port-group">
  <label for="screen-port">Screen port</label>
  <div class="row">
    <select id="screen-port" title="The serial port a real screen is on"></select>
    <select id="screen-rate" title="Its rate, in bits per second"></select>
    <button id="screen-connect">Connect</button>
    <button id="screen-find">Find</button>
  </div>
  <div id="screen-state" class="port-state"></div>
  <div id="screen-starts" class="buttons" hidden>
    <button id="start-screen">Start the screen again</button>
    <button id="start-both">Start both again</button>
  </div>
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
        void this.showAgent();
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
      } else if (message.type === "generator") {
        if (this.session) {
          this.generatorPanel.open(this.session);
        }
      } else if (message.type === "serial" && message.text) {
        // `to` sets where the instruction goes: the simulator, the screen, or both.
        void this.session?.customRequest("nxwright/serial", {
          text: message.text, ...(Array.isArray(message.to) ? { to: message.to } : {}),
        });
      } else if (message.type === "connect" && message.emulator === true) {
        void this.connectPort({ emulator: true });
      } else if (message.type === "connect" && typeof message.tcp === "string" && message.tcp) {
        void this.connectPort({ tcp: message.tcp });
      } else if (message.type === "connect" && message.name) {
        void this.connectPort({ name: message.name, baud: message.baud });
      } else if (message.type === "disconnect") {
        void this.disconnectPort();
      } else if (message.type === "noPort") {
        void this.chooseNoPort();
      } else if (message.type === "connectScreen" && message.name) {
        void this.chooseScreenPort("nxwright/screenPort", { name: message.name,
                                                          baud: message.baud });
      } else if (message.type === "disconnectScreen") {
        void this.chooseScreenPort("nxwright/screenPort", { name: "" });
      } else if (message.type === "findScreen" && message.name) {
        void this.chooseScreenPort("nxwright/findScreen", { name: message.name });
      } else if (message.type === "startEmulator") {
        if (this.session) {
          this.restartEmulator(this.session);
        }
      } else if (message.type === "startScreen") {
        void this.session?.customRequest("nxwright/startScreenAgain");
      } else if (message.type === "startBoth") {
        void this.startBothAgain();
      } else if (message.type === "bridge" && typeof message.choice === "string") {
        void this.joinPorts(message.choice);
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
  button:disabled, input:disabled, select:disabled { opacity: 0.5; cursor: default; }
  button:disabled:hover { background: var(--vscode-button-background); }
  form, .row { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
  label { width: 100%; }
  input, select {
    flex: 1; min-width: 0; color: var(--vscode-input-foreground);
    background: var(--vscode-input-background);
    border: 1px solid var(--vscode-input-border, transparent);
  }
  .port-group { margin-top: 10px; }
  .port-state { margin-top: 4px; color: var(--vscode-descriptionForeground); }
  .port-state.problem { color: var(--vscode-errorForeground); }
  #destinations { width: 100%; gap: 12px; }
  #destinations[hidden], #screen-starts[hidden], #bridge-row[hidden] { display: none; }
  #emulator-starts { margin: 6px 0 0; }
  #emulator-starts[hidden] { display: none; }
  #rate[hidden], #address[hidden] { display: none; }
  #bridge-row { margin-top: 4px; }
  label.inline { width: auto; }
  label.check { width: auto; display: flex; gap: 4px; align-items: center; }
  label.check input { flex: none; }
  #screen-starts { margin: 6px 0 0; }
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

// The arguments that each value of Goes to sends with "nxwright/bridge".
// With both, `simulator` is "listens" if the screen answers the MCU, and
// "answers" if the simulation does.
const BRIDGE_CHOICES: Record<string, { on: boolean; simulator?: string }> = {
  "simulator": { on: false },
  "screen": { on: true },
  "both-screen": { on: true, simulator: "listens" },
  "both-simulator": { on: true, simulator: "answers" },
};

// Whether a debugging session is a simulation: nxwright's, naming a source folder.
function isSimulation(session: vscode.DebugSession): boolean {
  return session.type === "nxwright" && !!session.configuration.sourceFolder;
}

// Asks VS Code to end `session`. A session that has ended already is left
// as it is.
async function endSession(session: vscode.DebugSession): Promise<void> {
  try {
    await vscode.debug.stopDebugging(session);
  } catch {
    // The session ended meanwhile.
  }
}

// Whether the Python Debugger extension is installed. nxwright's extension
// needs it to start a project's MCU emulator.
function hasPythonDebugger(): boolean {
  return vscode.extensions.getExtension(PYTHON_DEBUGGER_EXTENSION) !== undefined;
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
