// The agent channel, VS Code's side. With the setting
// nxwright.agents.allowControl on, a local connection through which a
// program on the same computer, such as `nxwright mcp`, starts a simulation
// in this window and drives it: presses, typed instructions, and looks at
// what the screen shows. Its rules, apart from VS Code, are agentChannel.ts's.
//
// The channel listens on this computer's own address, 127.0.0.1, on a port
// the system picks free each time it opens, and its file says which, with
// its token, which a program must show first. The file is deleted when the
// window closes or the setting goes off.
//
// What the app sends on its serial line reaches a device when a port is
// connected, so:
//  - a simulation the channel starts has no serial port, unless the
//    setting nxwright.agents.startWithoutSerialPort is off. Then the user is
//    asked first, before the app runs, when the Simulator settings name a
//    port and nxwright.agents.askBeforeSerialActions is on;
//  - an agent's first action on a simulation whose port is connected makes
//    VS Code ask the user, with that setting on. The answer holds until the
//    simulation ends, and the debug adapter refuses an agent's action while
//    a port is connected unless the extension says the user allowed it
//    (nxwright/debug_adapter/adapter.py).
import * as crypto from "crypto";
import * as fs from "fs";
import * as net from "net";
import * as os from "os";
import * as path from "path";
import * as vscode from "vscode";
import {
  agentMayAct,
  CHANNEL_HOST,
  channelFileText,
  channelFolder,
  ChannelHost,
  Conversation,
  insideWorkspace,
  onlyUserCanAccess,
} from "./agentChannel";
import { Simulator } from "./simulator";

const SETTINGS = "nxwright.agents";
// The longest a request may be, in characters: requests are small, so a
// program sending more without ending its line has its connection closed.
const LONGEST_REQUEST = 1_000_000;
// How long a stop waits for VS Code to end the simulation, in milliseconds.
const STOP_WAIT = 10000;
// How long a program has to say hello once connected, in milliseconds.
const HELLO_WAIT = 10000;

// The debug adapter's requests for what happens to the screen, and for
// looks at what the simulation holds, by the channel's method.
const ACTIONS: Record<string, string> = {
  press: "nxwright/press", move: "nxwright/move", release: "nxwright/release",
  serial: "nxwright/serial", startAgain: "nxwright/startAgain", gpioInput: "nxwright/gpioInput",
};
const LOOKS: Record<string, string> = {
  screen: "nxwright/screen", components: "nxwright/components", values: "nxwright/values",
  log: "nxwright/log",
};

// The channel while it is open: its port, its token, and its file.
interface OpenChannel {
  server: net.Server;
  port: number;
  token: string;
  file: string;
}

export class AgentChannel implements ChannelHost {
  private open: OpenChannel | undefined;
  private readonly connections = new Set<net.Socket>();
  // Opening and closing, one after the other, as the setting changes.
  private following: Promise<void> = Promise.resolve();
  // Whether an agent's start is under way: one at a time, as a window runs
  // one simulation.
  private starting = false;
  // Whether the extension let the channel go, as its window closes: an
  // opening still under way then closes at once.
  private disposed = false;

  constructor(private readonly simulator: Simulator) {}

  register(): vscode.Disposable[] {
    this.follow();
    return [
      vscode.workspace.onDidChangeConfiguration((event) => {
        if (event.affectsConfiguration(`${SETTINGS}.allowControl`)) {
          this.follow();
        }
      }),
      vscode.workspace.onDidChangeWorkspaceFolders(() => this.writeFile()),
      {
        dispose: () => {
          this.disposed = true;
          this.close();
        },
      },
    ];
  }

  // Opens the channel, or closes it, as the setting now says.
  private follow(): void {
    this.following = this.following.then(async () => {
      const wanted = vscode.workspace.getConfiguration(SETTINGS).get<boolean>("allowControl",
                                                                              false);
      if (wanted && !this.open) {
        await this.openChannel();
      } else if (!wanted && this.open) {
        this.close();
      }
    });
  }

  private async openChannel(): Promise<void> {
    try {
      const folder = channelFolder(process.platform, process.env, os.homedir());
      if (!folder) {
        throw new Error("LOCALAPPDATA names no folder for its file");
      }
      userOnlyFolder(folder);
      const token = crypto.randomBytes(32).toString("hex");
      const server = net.createServer((socket) => this.converse(socket, token));
      // Port 0: the system picks one free, which no other program can then
      // take, nor share.
      await new Promise<void>((resolve, reject) => {
        server.once("error", reject);
        server.listen({ host: CHANNEL_HOST, port: 0 }, () => {
          server.off("error", reject);
          resolve();
        });
      });
      const port = (server.address() as net.AddressInfo).port;
      const file = path.join(folder, `${crypto.randomBytes(8).toString("hex")}.json`);
      this.open = { server, port, token, file };
      if (this.disposed) {
        // The window closed while the channel was opening: no file is left.
        this.close();
        return;
      }
      this.writeFile(true);
    } catch (error) {
      this.close();
      void vscode.window.showErrorMessage(`nxwright: the agent channel did not open: ${
        error instanceof Error ? error.message : String(error)}.`);
    }
  }

  // Writes the channel's file: where it listens, its token, the window's
  // workspace folders, and the extension host's process. Made readable by
  // the user alone as it is created; written again as the folders change.
  private writeFile(creating = false): void {
    if (!this.open) {
      return;
    }
    const text = channelFileText(
      this.open.port, this.open.token,
      (vscode.workspace.workspaceFolders ?? []).map((entry) => entry.uri.fsPath), process.pid);
    fs.writeFileSync(this.open.file, text, { mode: 0o600, flag: creating ? "wx" : "w" });
  }

  private close(): void {
    const open = this.open;
    this.open = undefined;
    for (const socket of this.connections) {
      socket.destroy();
    }
    if (!open) {
      return;
    }
    open.server.close();
    try {
      fs.unlinkSync(open.file);
    } catch {
      // Already gone.
    }
  }

  // Answers one program's requests, one at a time, in the order they came.
  private converse(socket: net.Socket, token: string): void {
    this.connections.add(socket);
    socket.setEncoding("utf8");
    const conversation = new Conversation(token, this);
    // A program that never says hello does not keep its connection.
    const hello = setTimeout(() => {
      if (!conversation.greeted) {
        socket.destroy();
      }
    }, HELLO_WAIT);
    let unread = "";
    let answering = Promise.resolve();
    socket.on("data", (chunk: string) => {
      unread += chunk;
      let end;
      while ((end = unread.indexOf("\n")) >= 0) {
        const line = unread.slice(0, end).replace(/\r$/, "");
        unread = unread.slice(end + 1);
        answering = answering.then(async () => {
          if (socket.destroyed) {
            return;
          }
          const reaction = await conversation.answer(line);
          if (reaction.close) {
            socket.destroy();
          } else if (reaction.line !== undefined && !socket.destroyed) {
            socket.write(reaction.line + "\n");
          }
        }).catch(() => {
          // An answer that failed, which none should, closes the connection
          // rather than leave it answering nothing.
          socket.destroy();
        });
      }
      if (unread.length > LONGEST_REQUEST) {
        socket.destroy();
      }
    });
    socket.on("error", () => socket.destroy());
    socket.on("close", () => {
      clearTimeout(hello);
      this.connections.delete(socket);
    });
  }

  // A method of the channel, called once the program has said hello.
  async call(method: string, params: Record<string, unknown>): Promise<unknown> {
    if (method === "simulations") {
      const running = this.simulator.running;
      return { simulations: running ? [{ session: running.session.id,
                                         sourceFolder: running.sourceFolder,
                                         page: running.page }] : [] };
    }
    if (method === "start") {
      return await this.start(params);
    }
    const session = this.sessionNamed(params.session);
    if (method === "stop") {
      await vscode.debug.stopDebugging(session);
      // Answered once the window no longer runs it, so that a start may follow.
      for (let waited = 0; this.simulator.running?.session === session && waited < STOP_WAIT;
           waited += 100) {
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      return {};
    }
    if (method in LOOKS) {
      return await session.customRequest(LOOKS[method], lookArguments(method, params));
    }
    return await this.act(session, method, params);
  }

  // The simulation running in this window, if its session is `named`.
  private sessionNamed(named: unknown): vscode.DebugSession {
    const running = this.simulator.running;
    if (!running || running.session.id !== named) {
      throw new Error(`no simulation runs in this window as ${JSON.stringify(named)}`);
    }
    return running.session;
  }

  // Starts a simulation of the source folder `sourceFolder`, from
  // program.nx, or, given `page`, from that page: with no serial port, or
  // with the Simulator settings' port once the user allowed it, as this
  // file's opening comment says. Answers once the app has started, with the
  // page shown, if any.
  private async start(params: Record<string, unknown>): Promise<unknown> {
    const { sourceFolder, page } = params;
    if (typeof sourceFolder !== "string" || !path.isAbsolute(sourceFolder)
        || (page !== undefined && typeof page !== "string")) {
      throw new Error("start takes sourceFolder, a source folder's full path, and page, a "
                      + "page's name, if any");
    }
    this.refuseWhileOneRuns();
    if (this.starting) {
      throw new Error("an agent is starting a simulation in this window: drive it once it runs");
    }
    this.starting = true;
    try {
      return await this.startChecked(sourceFolder, page as string | undefined);
    } finally {
      this.starting = false;
    }
  }

  // Refuses while a simulation runs in this window: one at a time.
  private refuseWhileOneRuns(): void {
    const running = this.simulator.running;
    if (running) {
      throw new Error(`a simulation of ${running.sourceFolder} runs in this window: drive it, `
                      + "or stop it first");
    }
  }

  // Starts the simulation once its source folder is checked, as start says.
  private async startChecked(sourceFolder: string, page: string | undefined): Promise<unknown> {
    const real = realPath(sourceFolder);
    if (!real || !fs.existsSync(path.join(real, "app.toml"))) {
      throw new Error(`${sourceFolder} is no source folder: it has no app.toml`);
    }
    const workspace = (vscode.workspace.workspaceFolders ?? [])
      .map((entry) => realPath(entry.uri.fsPath))
      .filter((entry): entry is string => entry !== undefined);
    if (!insideWorkspace(real, workspace, process.platform)) {
      throw new Error(`${sourceFolder} is not inside this window's workspace`);
    }
    const folder = vscode.Uri.file(real);
    const settings = vscode.workspace.getConfiguration(SETTINGS);
    let withPort = !settings.get<boolean>("startWithoutSerialPort", true);
    let allowed = false;
    const port = withPort ? this.simulator.settingsPortOf(folder) : "";
    if (port) {
      // The app may send at once, as program.nx runs: the user answers first.
      allowed = !settings.get<boolean>("askBeforeSerialActions", true)
        || await this.userAllows(`An agent asks to start a simulation of ${real}, its serial `
                                 + `line connected to ${port}, as the Simulator settings say. `
                                 + "What the app sends will reach the device there. Allow the "
                                 + "agent to drive the simulation with the port connected? "
                                 + "Without, it starts with no port.");
      withPort = allowed;
    }
    // The user may have started one while the question waited.
    this.refuseWhileOneRuns();
    const session = await this.simulator.startForAgent(folder, page, withPort, allowed);
    // The adapter takes a look only once the app's start is over.
    let looked: { components: { name: string; type: string }[] };
    try {
      looked = await session.customRequest("nxwright/components");
    } catch (error) {
      throw new Error(`the simulation ${session.id} started, but its start did not end well: ${
        error instanceof Error ? error.message : String(error)}`);
    }
    const first = looked.components[0];
    return { session: session.id, page: first?.type === "page" ? first.name : null };
  }

  // Does the action `method` on `session`, once the serial port's rules
  // let it (agentChannel.agentMayAct), and answers once the simulation has
  // handled it.
  private async act(session: vscode.DebugSession, method: string,
                    params: Record<string, unknown>): Promise<unknown> {
    const ask = vscode.workspace.getConfiguration(SETTINGS).get<boolean>("askBeforeSerialActions",
                                                                         true);
    const allowed = await agentMayAct({
      port: () => this.simulator.serialPort,
      givenAnswer: () => this.simulator.agentAnswer,
      keepAnswer: (answer) => this.simulator.answerFor(session, answer),
      question: (port) => this.userAllows(`An agent asks to act on the simulation, whose serial `
                                          + `line is connected to ${port}. What the app sends `
                                          + "reaches the device there. Allow the agent to drive "
                                          + "this simulation until it ends?"),
      pause: (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
    }, ask);
    this.simulator.agentActed(session);
    await session.customRequest(ACTIONS[method], { ...actionArguments(method, params),
                                                   handled: true, agent: true, allowed });
    return {};
  }

  // Asks the user `question`, in a dialog that must be answered. Cancel is no.
  private async userAllows(question: string): Promise<boolean> {
    const choice = await vscode.window.showWarningMessage(question, { modal: true }, "Allow");
    return choice === "Allow";
  }
}

// The arguments of an action's request, from the channel's params.
function actionArguments(method: string, params: Record<string, unknown>): Record<string, unknown> {
  switch (method) {
    case "press":
    case "move":
      return { x: params.x, y: params.y };
    case "serial":
      return { text: params.text };
    case "gpioInput":
      return { pin: params.pin, level: params.level };
    default:
      return {};
  }
}

// The arguments of a look's request, from the channel's params.
function lookArguments(method: string, params: Record<string, unknown>): Record<string, unknown> {
  switch (method) {
    case "screen":
      return params.picture === undefined ? {} : { picture: params.picture };
    case "values":
      return params.names === undefined ? {} : { names: params.names };
    case "log":
      return params.after === undefined ? {} : { after: params.after };
    default:
      return {};
  }
}

// Makes the folder of the channels' files, readable by the user alone, and
// checks it is: on macOS and Linux, a folder already there must be the
// user's own, with no access for others; on Windows, it must lie in the
// user's own application data, whose access keeps others out.
function userOnlyFolder(folder: string): void {
  fs.mkdirSync(folder, { recursive: true, mode: 0o700 });
  if (process.platform === "win32") {
    const local = realPath(process.env.LOCALAPPDATA ?? "");
    const real = realPath(folder);
    if (!local || !real || !insideWorkspace(real, [local], "win32")) {
      throw new Error(`its folder, ${folder}, does not lie in LOCALAPPDATA`);
    }
    return;
  }
  const stat = fs.statSync(folder);
  if (!onlyUserCanAccess(stat.uid, stat.mode, process.getuid?.())) {
    throw new Error(`its folder, ${folder}, must be yours, and readable by you alone`);
  }
}

// A path with its links followed, or undefined when it does not exist.
function realPath(file: string): string | undefined {
  try {
    return fs.realpathSync.native(file);
  } catch {
    return undefined;
  }
}
