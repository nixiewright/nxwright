// Tests the commands on TFT files inside VS Code (src/tftCommands.ts):
// Compile TFT, Upload TFT, choosing the screen, and Decompile. A real
// compile needs the vendor's firmware, a real upload a screen, and a real
// decompile a TFT file of the vendor's. The tests have none of these, so
// nxwright's command is stand_in_nxwright.py while they run (stand_in.cjs).
// It answers those subcommands, and runs every other with the real
// nxwright. The tests choose the files and the screen, and give the answers
// to the questions, so that nothing prompts.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vscode = require("vscode");
const { test } = require("./runner.cjs");
const { withStandIn } = require("./stand_in.cjs");

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

test("Decompile runs once, and writes a folder the round trip did not confirm", async () => {
  await withStandIn(async (work, runs) => {
    const file = path.join(work, "app.tft");
    fs.writeFileSync(file, "stand-in");
    const written = path.join(work, "written");
    assert.equal(await vscode.commands.executeCommand(
      "nxwright.decompile", { file, folder: written, open: false }), 0);
    assert.ok(fs.existsSync(path.join(written, "app.toml")));
    assert.deepEqual(runs("decompile"), [[file, written, "--continue-unconfirmed"]]);
  });
});
