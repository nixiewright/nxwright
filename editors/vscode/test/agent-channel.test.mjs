// The agent channel's own rules, apart from VS Code (src/agentChannel.ts,
// compiled to out/ before the tests run): where its files lie, what they say,
// who may use it, its conversation, and when an agent may act on a
// simulation whose serial line reaches a device.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  agentMayAct, CHANNEL_HOST, channelFileText, channelFolder, Conversation, insideWorkspace,
  onlyUserCanAccess, serialRule, tokenMatches,
} from "../out/agentChannel.js";

test("the folder of the channels' files, in the user's own application data", () => {
  assert.equal(channelFolder("win32", { LOCALAPPDATA: "C:\\Users\\ann\\AppData\\Local" },
                             "C:\\Users\\ann"),
               "C:\\Users\\ann\\AppData\\Local\\nxwright\\agent-channels");
  assert.equal(channelFolder("darwin", {}, "/Users/ann"),
               "/Users/ann/Library/Application Support/nxwright/agent-channels");
  assert.equal(channelFolder("linux", { XDG_DATA_HOME: "/data" }, "/home/ann"),
               "/data/nxwright/agent-channels");
  for (const env of [{}, { XDG_DATA_HOME: "" }]) {
    assert.equal(channelFolder("linux", env, "/home/ann"),
                 "/home/ann/.local/share/nxwright/agent-channels");
  }
  // Without LOCALAPPDATA, Windows has no folder only the user reads.
  assert.equal(channelFolder("win32", {}, "C:\\Users\\ann"), undefined);
});

test("on macOS and Linux, the folder of the channels' files must be the user's alone", () => {
  // Modes as fs.statSync gives them: 0o40000 marks a folder.
  assert.equal(onlyUserCanAccess(501, 0o40700, 501), true);
  assert.equal(onlyUserCanAccess(501, 0o40750, 501), false);
  assert.equal(onlyUserCanAccess(501, 0o40701, 501), false);
  assert.equal(onlyUserCanAccess(0, 0o40700, 501), false);
  // Node gives no user ID on Windows.
  assert.equal(onlyUserCanAccess(0, 0o40700, undefined), false);
});

test("the channel's file: where it listens, on this computer alone, and its token", () => {
  const token = "ef".repeat(32);
  assert.equal(CHANNEL_HOST, "127.0.0.1");
  assert.deepEqual(JSON.parse(channelFileText(51234, token, ["/home/ann/work"], 7)),
                   { host: "127.0.0.1", port: 51234, token, workspaceFolders: ["/home/ann/work"],
                     pid: 7 });
});

test("the token, compared in full", () => {
  const token = "ab".repeat(32);
  assert.equal(tokenMatches(token, token), true);
  assert.equal(tokenMatches("ac".repeat(32), token), false);
  assert.equal(tokenMatches("ab", token), false);
  for (const given of [undefined, null, 12, ["ab"], { token }]) {
    assert.equal(tokenMatches(given, token), false);
  }
  // As many characters, but more bytes: refused, not an error.
  assert.equal(tokenMatches("é" + "a".repeat(63), token), false);
});

test("a source folder inside the workspace, by its real path", () => {
  assert.equal(insideWorkspace("/work/app", ["/work"], "linux"), true);
  assert.equal(insideWorkspace("/work", ["/work"], "linux"), true);
  assert.equal(insideWorkspace("/workshop/app", ["/work"], "linux"), false);
  assert.equal(insideWorkspace("/Work/app", ["/work"], "linux"), false);
  assert.equal(insideWorkspace("/other", ["/work", "/other"], "linux"), true);
  // Windows paths name the same folder whatever their letters' case.
  assert.equal(insideWorkspace("C:\\Work\\App", ["c:\\work"], "win32"), true);
  assert.equal(insideWorkspace("C:\\Workshop", ["C:\\Work"], "win32"), false);
});

// A host standing in for the window's simulations: it records each call.
function standInHost() {
  const calls = [];
  return {
    calls,
    async call(method, params) {
      calls.push([method, params]);
      if (method === "stop") {
        throw new Error("no simulation is named so");
      }
      return { done: method };
    },
  };
}

const TOKEN = "cd".repeat(32);

async function talk(conversation, ...messages) {
  const answers = [];
  for (const message of messages) {
    answers.push(await conversation.answer(typeof message === "string"
      ? message : JSON.stringify(message)));
  }
  return answers;
}

test("the first request says hello with the token, or the channel closes", async () => {
  for (const first of [{ id: 1, method: "start", params: {} },
                       { id: 1, method: "hello", params: { token: "cd" } },
                       { id: 1, method: "hello", params: { token: "é" + "c".repeat(63) } },
                       "not JSON"]) {
    const host = standInHost();
    const [answer] = await talk(new Conversation(TOKEN, host), first);
    assert.deepEqual(answer, { close: true });
    assert.deepEqual(host.calls, []);
  }
});

test("after hello, requests go to the host and its answers come back", async () => {
  const host = standInHost();
  const answers = await talk(new Conversation(TOKEN, host),
                             { id: 1, method: "hello", params: { token: TOKEN } },
                             { id: 2, method: "press", params: { session: "s", x: 1, y: 2 } },
                             { id: 3, method: "stop", params: { session: "s" } },
                             { id: 4, method: "fly", params: {} },
                             { id: 5, method: "hello", params: { token: TOKEN } },
                             "not JSON");
  assert.deepEqual(answers.map((answer) => answer.line && JSON.parse(answer.line)), [
    // The messages' version, so that a program can tell a later change apart.
    { id: 1, result: { version: 1 } },
    { id: 2, result: { done: "press" } },
    { id: 3, error: { message: "no simulation is named so" } },
    { id: 4, error: { message: "there is no method fly" } },
    { id: 5, error: { message: "hello comes once, first" } },
    { id: null, error: { message: "a request is one JSON object on a line, with id, method, "
                                   + "and params" } },
  ]);
  assert.deepEqual(host.calls, [["press", { session: "s", x: 1, y: 2 }],
                                ["stop", { session: "s" }]]);
});

test("the GPIO methods go to the host, one pin or several", async () => {
  const host = standInHost();
  await talk(new Conversation(TOKEN, host),
             { id: 1, method: "hello", params: { token: TOKEN } },
             { id: 2, method: "gpioInput", params: { session: "s", pin: 2, level: 0 } },
             { id: 3, method: "gpioInputs", params: { session: "s", levels: { pio2: 1 } } });
  assert.deepEqual(host.calls, [["gpioInput", { session: "s", pin: 2, level: 0 }],
                                ["gpioInputs", { session: "s", levels: { pio2: 1 } }]]);
});

test("an agent may act on a simulation whose serial line reaches a device", () => {
  // Without a port connected, or with the question turned off, it may.
  assert.equal(serialRule({ connected: false, ask: true, answer: undefined }), "act");
  assert.equal(serialRule({ connected: true, ask: false, answer: undefined }), "act");
  // Else the user is asked once, and the answer stands.
  assert.equal(serialRule({ connected: true, ask: true, answer: undefined }), "ask");
  assert.equal(serialRule({ connected: true, ask: true, answer: "asking" }), "wait");
  assert.equal(serialRule({ connected: true, ask: true, answer: "yes" }), "act");
  assert.equal(serialRule({ connected: true, ask: true, answer: "no" }), "refuse");
});

// A serial line standing in for the simulation's: `connected` and `answer`
// as the test sets them, and the questions the user was asked, each
// answered by `reply`, a promise the test settles.
function standInLine({ connected, answer, reply }) {
  const line = {
    asked: 0,
    answer,
    port: () => ({ name: "COM4", connected }),
    givenAnswer: () => line.answer,
    keepAnswer: (given) => { line.answer = given; },
    question: async () => {
      line.asked += 1;
      return await reply;
    },
    pause: async () => {},
  };
  return line;
}

test("without a port connected, an agent acts, allowed only as the user said", async () => {
  const line = standInLine({ connected: false, answer: undefined });
  assert.equal(await agentMayAct(line, true), false);
  assert.equal(await agentMayAct(line, false), true);
  assert.equal(line.asked, 0);
});

test("with the question turned off, an agent acts at once, allowed", async () => {
  const line = standInLine({ connected: true, answer: undefined });
  assert.equal(await agentMayAct(line, false), true);
  assert.equal(line.asked, 0);
});

test("the user is asked once, and a yes lets the action go", async () => {
  const line = standInLine({ connected: true, answer: undefined, reply: Promise.resolve(true) });
  assert.equal(await agentMayAct(line, true), true);
  assert.equal(await agentMayAct(line, true), true);
  assert.deepEqual([line.asked, line.answer], [1, "yes"]);
});

test("after a no, each action is refused, and nothing is asked again", async () => {
  const line = standInLine({ connected: true, answer: undefined, reply: Promise.resolve(false) });
  for (let time = 0; time < 2; time += 1) {
    await assert.rejects(agentMayAct(line, true), /did not allow agents .* COM4/);
  }
  assert.equal(line.asked, 1);
});

test("while the user has not answered, an action says VS Code waits", async () => {
  const line = standInLine({ connected: true, answer: undefined, reply: new Promise(() => {}) });
  await assert.rejects(agentMayAct(line, true), /VS Code waits for the user's answer/);
  await assert.rejects(agentMayAct(line, true), /VS Code waits for the user's answer/);
  assert.deepEqual([line.asked, line.answer], [1, "asking"]);
});

test("a question that fails counts as a no, the safe answer", async () => {
  const line = standInLine({ connected: true, answer: undefined,
                             reply: Promise.reject(new Error("the dialog failed")) });
  await assert.rejects(agentMayAct(line, true), /did not allow agents/);
  assert.equal(line.answer, "no");
});
