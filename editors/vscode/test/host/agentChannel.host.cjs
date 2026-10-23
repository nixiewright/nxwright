// The agent channel (src/agentChannelServer.ts): with
// nxwright.agents.allowControl on, a program on this computer reads the
// channel's file, says hello with its token, starts a simulation of the
// folder VS Code opened, and drives it, as `nxwright mcp` does. One test
// drives it with `nxwright mcp`'s own client (drive_through_channel.py).
const assert = require("node:assert/strict");
const { execFile } = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { promisify } = require("node:util");
const vscode = require("vscode");
const { folderFile, test, waitFor } = require("./runner.cjs");
const { channelFolder } = require("../../out/agentChannel.js");

const AGENTS = "nxwright.agents";

// Sets a setting of the user's own, or takes it away with `undefined`.
async function setting(section, name, value) {
  await vscode.workspace.getConfiguration(section).update(name, value,
                                                          vscode.ConfigurationTarget.Global);
}

// The channel's file of this window: the one naming this extension host.
function channelFile() {
  const folder = channelFolder(process.platform, process.env, os.homedir());
  if (!folder || !fs.existsSync(folder)) {
    return undefined;
  }
  for (const name of fs.readdirSync(folder).filter((entry) => entry.endsWith(".json"))) {
    try {
      const described = JSON.parse(fs.readFileSync(path.join(folder, name), "utf8"));
      if (described.pid === process.pid) {
        return { path: path.join(folder, name), ...described };
      }
    } catch {
      // Another window's file, being written.
    }
  }
  return undefined;
}

// A connection to the channel its file `file` describes: request(method,
// params) answers with the result, or fails with the error's message; end()
// leaves once what was sent has gone, as a program that stops waiting does.
function connect(file) {
  const socket = net.connect({ host: file.host, port: file.port });
  socket.setEncoding("utf8");
  const waiting = new Map();
  let unread = "";
  let next = 1;
  socket.on("data", (chunk) => {
    unread += chunk;
    let end;
    while ((end = unread.indexOf("\n")) >= 0) {
      const answer = JSON.parse(unread.slice(0, end));
      unread = unread.slice(end + 1);
      const settle = waiting.get(answer.id);
      waiting.delete(answer.id);
      if (answer.error) {
        settle.reject(new Error(answer.error.message));
      } else {
        settle.resolve(answer.result);
      }
    }
  });
  const closed = new Promise((resolve) => socket.on("close", resolve));
  return {
    closed,
    close: () => socket.destroy(),
    end: () => socket.end(),
    request(method, params = {}) {
      const id = next++;
      socket.write(JSON.stringify({ id, method, params }) + "\n");
      return new Promise((resolve, reject) => waiting.set(id, { resolve, reject }));
    },
  };
}

// Opens the channel and gives its file to `body`; then stops any simulation
// left running and closes the channel again.
async function withChannelOpen(body) {
  await setting(AGENTS, "allowControl", true);
  const file = await waitFor(channelFile, "the channel's file", 10000);
  try {
    await body(file);
  } finally {
    if (vscode.debug.activeDebugSession) {
      await vscode.debug.stopDebugging(vscode.debug.activeDebugSession);
      await waitFor(() => !vscode.debug.activeDebugSession, "the simulation's end", 10000);
    }
    await setting(AGENTS, "allowControl", undefined);
    await waitFor(() => !fs.existsSync(file.path), "the channel's file gone", 10000);
  }
}

// Opens the channel, says hello, and gives the connection to `body`; then
// stops any simulation left running and closes the channel again.
async function withChannel(body) {
  await withChannelOpen(async (file) => {
    // On this computer alone.
    assert.equal(file.host, "127.0.0.1");
    const channel = connect(file);
    try {
      assert.deepEqual(await channel.request("hello", { token: file.token }), { version: 1 });
      await body(channel);
    } finally {
      channel.close();
    }
  });
}

test("an agent starts a simulation through the channel and drives it", async () => {
  await withChannel(async (channel) => {
    const started = await channel.request("start", { sourceFolder: folderFile().fsPath });
    assert.equal(started.page, "browsers");
    const { simulations } = await channel.request("simulations");
    assert.deepEqual(simulations.map((entry) => entry.session), [started.session]);
    const session = started.session;
    assert.deepEqual(await channel.request("press", { session, x: 10, y: 10 }), {});
    assert.deepEqual(await channel.request("release", { session }), {});
    const { components } = await channel.request("components", { session });
    assert.equal(components[0].type, "page");
    const { values } = await channel.request("values", { session, names: ["dp"] });
    assert.equal(typeof values.dp, "number");
    // A picture of the screen, a PNG in base64, with its text layout.
    const shown = await channel.request("screen", { session });
    assert.equal(shown.page, "browsers");
    assert.equal(Buffer.from(shown.png, "base64").subarray(1, 4).toString(), "PNG");
    // One simulation at a time in a window: the agent's start is refused.
    await assert.rejects(channel.request("start", { sourceFolder: folderFile().fsPath }),
                         /runs in this window/);
    assert.deepEqual(await channel.request("stop", { session }), {});
  });
});

test("nxwright mcp's own client drives a simulation through the channel", async () => {
  // The Python and the checkout that run nxwright for the extension (run.mjs).
  const [python, runScript] = vscode.workspace.getConfiguration("nxwright").get("command");
  await withChannelOpen(async () => {
    const importPath = [path.dirname(runScript), process.env.PYTHONPATH].filter(Boolean);
    // The client runs while this test waits for it, not blocking this
    // process, from which the channel answers.
    const { stdout } = await promisify(execFile)(
      python, ["-B", path.join(__dirname, "drive_through_channel.py"), folderFile().fsPath],
      { env: { ...process.env, PYTHONPATH: importPath.join(path.delimiter) }, timeout: 60000 });
    const answers = JSON.parse(stdout);
    assert.equal(answers.page, "browsers");
    assert.deepEqual(answers.running, [answers.session]);
    assert.match(answers["second start"], /runs in this window/);
    assert.deepEqual(answers.values, { "dirLabel.txt": "new" });
    assert.equal(answers.screen.page, "browsers");
    assert.match(answers.screen.text, /^page browsers \(/);
    // A PNG's first bytes: 89, then "PNG".
    assert.equal(answers.screen.png, "89504e47");
    assert.equal(answers.components[0], "page");
    assert.ok(answers.log.includes('receives dirLabel.txt="new"'), answers.log.join("\n"));
    await waitFor(() => !vscode.debug.activeDebugSession, "the simulation's end", 10000);
  });
});

test("of two starts at once, one simulation runs and the other start is refused", async () => {
  // As two agents, or one agent's two connections, might: a window runs one.
  await withChannel(async (channel) => {
    const file = channelFile();
    const other = connect(file);
    try {
      await other.request("hello", { token: file.token });
      const sourceFolder = folderFile().fsPath;
      const results = await Promise.allSettled([channel.request("start", { sourceFolder }),
                                                other.request("start", { sourceFolder })]);
      assert.deepEqual(results.map((result) => result.status).sort(), ["fulfilled", "rejected"]);
      assert.match(results.find((result) => result.status === "rejected").reason.message,
                   /starting a simulation in this window|runs in this window/);
      assert.equal(vscode.debug.activeDebugSession !== undefined, true);
    } finally {
      other.close();
    }
  });
});

test("a start goes on once the program that sent it has gone", async () => {
  // As when nxwright mcp stops waiting for it: the simulation still starts,
  // and a new connection finds it. VS Code asks nothing first, the
  // settings naming no serial port, as a test cannot answer its question.
  await withChannel(async (channel) => {
    const file = channelFile();
    const leaving = connect(file);
    await leaving.request("hello", { token: file.token });
    void leaving.request("start", { sourceFolder: folderFile().fsPath });
    leaving.end();
    await leaving.closed;
    const listed = await waitFor(async () => {
      const { simulations } = await channel.request("simulations");
      return simulations[0];
    }, "the simulation the program left", 30000);
    assert.equal(typeof listed.session, "string");
  });
});

test("a program without the channel's token is shut out", async () => {
  await setting(AGENTS, "allowControl", true);
  try {
    const file = await waitFor(channelFile, "the channel's file", 10000);
    const channel = connect(file);
    channel.request("hello", { token: "00".repeat(32) });
    await channel.closed;
  } finally {
    await setting(AGENTS, "allowControl", undefined);
  }
});

test("an agent's simulation has no serial port, unless the setting says otherwise", async () => {
  // pyserial's loop:// stands for a device: what is written to it comes back.
  await setting("nxwright.simulator", "serialPort", "loop://");
  try {
    await withChannel(async (channel) => {
      const sourceFolder = folderFile().fsPath;
      let { session } = await channel.request("start", { sourceFolder });
      assert.equal(vscode.debug.activeDebugSession.configuration.serialPort, null);
      await channel.request("stop", { session });
      await waitFor(() => !vscode.debug.activeDebugSession, "the simulation's end", 10000);
      // With the port, and nothing asked, an action is done at once.
      await setting(AGENTS, "startWithoutSerialPort", false);
      await setting(AGENTS, "askBeforeSerialActions", false);
      ({ session } = await channel.request("start", { sourceFolder }));
      assert.equal(vscode.debug.activeDebugSession.configuration.serialPort.name, "loop://");
      assert.deepEqual(await channel.request("press", { session, x: 10, y: 10 }), {});
    });
  } finally {
    await setting("nxwright.simulator", "serialPort", undefined);
    await setting(AGENTS, "startWithoutSerialPort", undefined);
    await setting(AGENTS, "askBeforeSerialActions", undefined);
  }
});
