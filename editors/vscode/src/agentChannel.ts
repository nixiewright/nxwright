// The agent channel's own rules, kept apart from VS Code so that Node's
// test runner checks them (test/agent-channel.test.mjs). The channel is a
// local connection through which a program on the same computer, such as
// `nxwright mcp`, drives this window's simulations (agentChannelServer.ts).
//
// It listens on this computer's own address, 127.0.0.1, which only programs
// of this computer reach, on a port the system picks free. Any of them may
// connect, whichever account runs it: the token keeps them out, a secret a
// program shows first. The channel's file, one for each window, says where
// the channel listens and holds its token. The file lies in a folder of the
// user's own application data, which only the user's account can read.
// A conversation is one JSON object per line each way: a request, {id,
// method, params}, and its answer, {id, result} or {id, error: {message}}.
import * as crypto from "crypto";
import * as path from "path";

// The version of the messages, which hello answers with, so that a program
// can tell a later change apart and refuse what it does not speak.
export const MESSAGES_VERSION = 1;

// Where the channel listens: this computer's own address, never one that
// another computer reaches.
export const CHANNEL_HOST = "127.0.0.1";

// The methods a program may call once it said hello.
const METHODS = new Set(["simulations", "start", "stop", "press", "move", "release", "serial",
                         "startAgain", "gpioInput", "gpioInputs", "screen", "components",
                         "values", "log"]);

// The folder of the channels' files on the system `platform`, given its
// environment `env` and the user's home folder `home`: in the user's own
// application data. Undefined on Windows without LOCALAPPDATA, as there is
// then no folder that only the user's account reads.
export function channelFolder(platform: string, env: Record<string, string | undefined>,
                              home: string): string | undefined {
  if (platform === "win32") {
    return env.LOCALAPPDATA
      ? path.win32.join(env.LOCALAPPDATA, "nxwright", "agent-channels") : undefined;
  }
  if (platform === "darwin") {
    return path.posix.join(home, "Library", "Application Support", "nxwright", "agent-channels");
  }
  return path.posix.join(env.XDG_DATA_HOME || path.posix.join(home, ".local", "share"),
                         "nxwright", "agent-channels");
}

// Whether only the user `uid` can access a folder on macOS or Linux: the
// folder's `owner` is that user, and its `mode` gives no access to anyone
// else. `owner` and `mode` are as fs.statSync gives them.
export function onlyUserCanAccess(owner: number, mode: number,
                                  uid: number | undefined): boolean {
  return owner === uid && (mode & 0o077) === 0;
}

// The text of the channel's file: where the channel listens, CHANNEL_HOST
// and its `port`; its `token`; the window's `workspaceFolders`, by their
// paths; and the extension host's process, `pid`.
export function channelFileText(port: number, token: string, workspaceFolders: string[],
                                pid: number): string {
  return JSON.stringify({ host: CHANNEL_HOST, port, token, workspaceFolders, pid });
}

// Whether `given` is the channel's `token`, compared in constant time, so
// that how long a wrong guess takes tells nothing of the token.
export function tokenMatches(given: unknown, token: string): boolean {
  if (typeof given !== "string") {
    return false;
  }
  // Compared by bytes, which the comparison needs to be as many: a text of
  // as many characters may have more bytes.
  const givenBytes = Buffer.from(given);
  const tokenBytes = Buffer.from(token);
  return givenBytes.length === tokenBytes.length
    && crypto.timingSafeEqual(givenBytes, tokenBytes);
}

// Whether the source folder whose real path is `realSource` lies inside one
// of the workspace's folders, by their real paths `realFolders`, on the
// system `platform`. Windows paths name the same folder whatever their
// letters' case.
export function insideWorkspace(realSource: string, realFolders: string[],
                                platform: string): boolean {
  const paths = platform === "win32" ? path.win32 : path.posix;
  return realFolders.some((folder) => {
    const relative = paths.relative(folder, realSource);
    return relative === "" || (relative !== ".." && !relative.startsWith(".." + paths.sep)
                               && !paths.isAbsolute(relative));
  });
}

// What a conversation does with a line it was sent: answers with a line,
// or closes the connection.
export interface Reaction {
  line?: string;
  close?: boolean;
}

// The window's simulations, as the channel's methods reach them.
export interface ChannelHost {
  call(method: string, params: Record<string, unknown>): Promise<unknown>;
}

// One program's conversation with the channel. Its first request must be
// hello with the channel's `token`; any other first line closes the
// connection. After that, each request goes to `host`, and its answer, or
// the error it raised, comes back.
export class Conversation {
  private saidHello = false;

  constructor(private readonly token: string, private readonly host: ChannelHost) {}

  // Whether the program has said hello with the token.
  get greeted(): boolean {
    return this.saidHello;
  }

  async answer(text: string): Promise<Reaction> {
    const request = parsedRequest(text);
    if (!this.saidHello) {
      if (request?.method === "hello" && tokenMatches(request.params.token, this.token)) {
        this.saidHello = true;
        return answered(request.id, { result: { version: MESSAGES_VERSION } });
      }
      return { close: true };
    }
    if (!request) {
      return answered(null, { error: { message: "a request is one JSON object on a line, with "
                                                 + "id, method, and params" } });
    }
    if (request.method === "hello") {
      return answered(request.id, { error: { message: "hello comes once, first" } });
    }
    if (!METHODS.has(request.method)) {
      return answered(request.id, { error: { message: `there is no method ${request.method}` } });
    }
    try {
      return answered(request.id, { result: await this.host.call(request.method,
                                                                 request.params) ?? {} });
    } catch (error) {
      return answered(request.id, {
        error: { message: error instanceof Error ? error.message : String(error) } });
    }
  }
}

interface Request {
  id: string | number;
  method: string;
  params: Record<string, unknown>;
}

// The request a line holds, or undefined when it holds none.
function parsedRequest(text: string): Request | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return undefined;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return undefined;
  }
  const { id, method, params } = parsed as Record<string, unknown>;
  const goodParams = params === undefined
    || (typeof params === "object" && params !== null && !Array.isArray(params));
  if ((typeof id !== "string" && typeof id !== "number") || typeof method !== "string"
      || !goodParams) {
    return undefined;
  }
  return { id, method, params: (params ?? {}) as Record<string, unknown> };
}

function answered(id: string | number | null, body: Record<string, unknown>): Reaction {
  return { line: JSON.stringify({ id, ...body }) };
}

// What the user answered, for the simulation running, to whether an agent
// may act on it while its serial line reaches a device: asked and not yet
// answered, yes, or no.
export type AgentAnswer = "asking" | "yes" | "no" | undefined;

// What a serial line reaching a device lets an agent do, under the user's
// settings: act at once, ask the user, wait for the answer being asked, or
// be refused. `connected` is whether a port is connected; `ask` whether the
// user wants to be asked first (nxwright.agents.askBeforeSerialActions);
// `answer` what the user said for this simulation, if anything yet.
export function serialRule(state: { connected: boolean; ask: boolean; answer: AgentAnswer }):
    "act" | "ask" | "wait" | "refuse" {
  if (!state.connected || !state.ask || state.answer === "yes") {
    return "act";
  }
  if (state.answer === "no") {
    return "refuse";
  }
  return state.answer === "asking" ? "wait" : "ask";
}

// How long an action waits for the user's answer before saying that VS Code
// still waits for it, in milliseconds, and how often it looks meanwhile.
export const ANSWER_WAIT = 2000;
const ANSWER_LOOK = 100;

// The simulation's serial line, as an agent's action meets it: the port's
// state as it is now, the user's answer for this simulation, and asking
// the user `question`, which resolves with whether the user allowed it.
// `pause` waits, so that a test need not.
export interface SerialLine {
  port(): { name: string | null; connected: boolean } | undefined;
  givenAnswer(): AgentAnswer;
  keepAnswer(answer: AgentAnswer): void;
  question(port: string | null): Promise<boolean>;
  pause(milliseconds: number): Promise<void>;
}

// Whether an agent's action on the simulation may go, by serialRule, `ask`
// being whether the user wants to be asked first: asks the user once, when
// the rule says so, and waits a while for the answer. Resolves with
// whether the user allowed the agent, which the debug adapter checks again
// as the action runs (`allowed`). Rejects, in words the agent reads, when
// the user said no, or has not answered yet.
export async function agentMayAct(line: SerialLine, ask: boolean): Promise<boolean> {
  // The port and the answer as they are now: each may change while it waits.
  const rule = () => serialRule({ connected: line.port()?.connected === true, ask,
                                  answer: line.givenAnswer() });
  if (rule() === "ask") {
    line.keepAnswer("asking");
    void line.question(line.port()?.name ?? null)
      .then((allowed) => line.keepAnswer(allowed ? "yes" : "no"),
            // A question that fails counts as a no: the device stays safe.
            () => line.keepAnswer("no"));
  }
  for (let waited = 0; rule() === "wait" && waited < ANSWER_WAIT; waited += ANSWER_LOOK) {
    await line.pause(ANSWER_LOOK);
  }
  const port = line.port()?.name;
  if (rule() === "refuse") {
    throw new Error(`the user did not allow agents to act on this simulation while its serial `
                    + `port ${port} is connected; that holds until the simulation ends`);
  }
  if (rule() === "wait") {
    throw new Error("VS Code waits for the user's answer, whether an agent may act on this "
                    + `simulation while its serial port ${port} is connected; try again once `
                    + "the user has answered");
  }
  return !ask || line.givenAnswer() === "yes";
}
