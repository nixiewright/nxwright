// Tests the commands on TFT files inside VS Code (src/tftCommands.ts):
// Compile TFT, Upload TFT, choosing the screen, and Decompile. A real
// compile needs the vendor's firmware, a real upload a screen, and a real
// decompile a TFT file of the vendor's, none of which the tests have, so
// nxwright's command is stand_in_nxwright.py while they run: it answers
// those subcommands, and runs every other with the real nxwright. The tests
// choose the files and the screen, and give the answers to the questions,
// so that nothing prompts.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vscode = require("vscode");
const { test, waitFor } = require("./runner.cjs");

// nxwright's command before the tests set the stand-in, once they have.
let commandBefore;

// Reads the stand-in's log `log`: the arguments of each run of the
// subcommand `name`, such as "compile", in order.
function runsIn(log, name) {
  return (fs.existsSync(log)
    ? fs.readFileSync(log, "utf8").trim().split("\n").map((line) => JSON.parse(line)) : [])
    .filter((run) => run[0] === name).map((run) => run.slice(1));
}

// Sets the stand-in as nxwright's command, the first time. The extension
// takes a new command once it has searched again, which waits behind the
// language server's restart: once the server runs through the stand-in, the
// commands do too. The last test sets the command back.
async function useStandIn() {
  if (commandBefore !== undefined) {
    return;
  }
  const settings = vscode.workspace.getConfiguration("nxwright");
  commandBefore = settings.get("command");
  const log = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "nxwright-tft-")), "server.log");
  process.env.NXWRIGHT_STAND_IN_LOG = log;
  await settings.update("command",
                        [commandBefore[0], path.join(__dirname, "stand_in_nxwright.py")],
                        vscode.ConfigurationTarget.Global);
  await waitFor(() => runsIn(log, "lsp").length > 0, "the language server started by the stand-in");
}

// Runs `body` with the stand-in as nxwright's command, logging what it runs
// to a file of its own, and gives `body` a new folder, and a function that
// returns the arguments of each run of a subcommand, such as "compile", in
// order. Each run reads the log's name when it starts.
async function withStandIn(body) {
  await useStandIn();
  const work = fs.mkdtempSync(path.join(os.tmpdir(), "nxwright-tft-"));
  const log = path.join(work, "runs.log");
  process.env.NXWRIGHT_STAND_IN_LOG = log;
  await body(work, (name) => runsIn(log, name));
}

test("Compile TFT takes the firmware from the answer once it is missing", async () => {
  await withStandIn(async (work, runs) => {
    const tft = path.join(work, "app.tft");
    assert.equal(await vscode.commands.executeCommand("nxwright.chooseTftFile", tft), tft);
    const firmware = path.join(work, "firmware.tft");
    const code = await vscode.commands.executeCommand("nxwright.compileWithoutProjectFile",
                                                      { firmware });
    assert.equal(code, 0);
    assert.match(fs.readFileSync(tft, "utf8"), /^stand-in TFT file of /);
    const [first, second] = runs("compile");
    // The first compile found no firmware; the second was given the file.
    assert.deepEqual(first.slice(1), [tft, "--overwrite", "--json"]);
    assert.deepEqual(second.slice(1), [tft, "--overwrite", "--json", "--firmware", firmware]);
  });
});

test("Compile TFT writes nothing when the user stops at the missing firmware", async () => {
  await withStandIn(async (work, runs) => {
    const tft = path.join(work, "app.tft");
    await vscode.commands.executeCommand("nxwright.chooseTftFile", tft);
    const code = await vscode.commands.executeCommand("nxwright.compileWithoutProjectFile",
                                                      "cancel");
    assert.equal(code, 1);
    assert.equal(fs.existsSync(tft), false);
    assert.equal(runs("compile").length, 1);
  });
});

test("a screen given is kept, its port and rate as given", async () => {
  await withStandIn(async () => {
    assert.deepEqual(await vscode.commands.executeCommand("nxwright.chooseScreen",
                                                          { port: "COM9", rate: 921600 }),
                     { port: "COM9", rate: 921600 });
  });
});

test("Upload a TFT file finds the screen, then uploads at the rate it found", async () => {
  await withStandIn(async (work, runs) => {
    const tft = path.join(work, "app.tft");
    fs.writeFileSync(tft, "stand-in");
    await vscode.commands.executeCommand("nxwright.chooseScreen", { port: "COM9", rate: 921600 });
    assert.equal(await vscode.commands.executeCommand("nxwright.uploadTftFile",
                                                      { file: tft, upload: true }), 0);
    assert.deepEqual(runs("upload"), [
      [tft, "--port", "COM9", "--upload-baud", "921600", "--find", "--json"],
      [tft, "--port", "COM9", "--upload-baud", "921600", "--baud", "115200", "--yes", "--json"],
    ]);
  });
});

test("Upload a TFT file sends nothing when the user does not confirm", async () => {
  await withStandIn(async (work, runs) => {
    const tft = path.join(work, "app.tft");
    fs.writeFileSync(tft, "stand-in");
    await vscode.commands.executeCommand("nxwright.chooseScreen", { port: "COM9", rate: 115200 });
    assert.equal(await vscode.commands.executeCommand("nxwright.uploadTftFile",
                                                      { file: tft, upload: false }), undefined);
    assert.equal(runs("upload").length, 1);
  });
});

test("Upload a TFT file sends nothing when the toolchain cancels the upload", async () => {
  await withStandIn(async (work, runs) => {
    await vscode.commands.executeCommand("nxwright.chooseScreen", { port: "COM9", rate: 115200 });
    // The upload is cancelled once the screen is found, so it never runs.
    const cancelled = path.join(work, "cancelled-at-find.tft");
    fs.writeFileSync(cancelled, "stand-in");
    assert.equal(await vscode.commands.executeCommand("nxwright.uploadTftFile",
                                                      { file: cancelled, upload: true }), 1);
    assert.deepEqual(runs("upload"), [
      [cancelled, "--port", "COM9", "--upload-baud", "115200", "--find", "--json"],
    ]);
    // This upload is cancelled only when it runs, as if another screen
    // had been connected after the first one was found.
    const cancelledLater = path.join(work, "cancelled-at-upload.tft");
    fs.writeFileSync(cancelledLater, "stand-in");
    assert.equal(await vscode.commands.executeCommand("nxwright.uploadTftFile",
                                                      { file: cancelledLater, upload: true }), 1);
    assert.equal(runs("upload").length, 3);
  });
});

test("Decompile writes a folder the round trip did not confirm only when told to", async () => {
  await withStandIn(async (work, runs) => {
    const file = path.join(work, "app.tft");
    fs.writeFileSync(file, "stand-in");
    const kept = path.join(work, "kept");
    assert.equal(await vscode.commands.executeCommand(
      "nxwright.decompile", { file, folder: kept, writeAnyway: false, open: false }), 3);
    assert.equal(fs.existsSync(path.join(kept, "app.toml")), false);
    const written = path.join(work, "written");
    assert.equal(await vscode.commands.executeCommand(
      "nxwright.decompile", { file, folder: written, writeAnyway: true, open: false }), 0);
    assert.ok(fs.existsSync(path.join(written, "app.toml")));
    assert.deepEqual(runs("decompile").at(-1), [file, written, "--continue-unconfirmed"]);
  });
});

test("nxwright's command is set back once the tests of TFT files are done", async () => {
  if (commandBefore !== undefined) {
    await vscode.workspace.getConfiguration("nxwright")
      .update("command", commandBefore, vscode.ConfigurationTarget.Global);
  }
});
