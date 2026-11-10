// Sets stand_in_nxwright.py as nxwright's command for the tests inside VS
// Code that must not run a real subcommand: one that needs what the tests
// do not have, such as a screen, or one that would change the source folder
// the tests share. The stand-in answers those subcommands, runs every other
// with the real nxwright, and logs the arguments of each run.
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vscode = require("vscode");
const { testLast, waitFor } = require("./runner.cjs");

// nxwright's command before the tests set the stand-in. It is undefined
// until they do.
let commandBefore;
// The log the stand-in writes to when a run is given no log of its own.
// It is in this checkout's .vscode-test folder, where the tests' VS Code
// keeps its files. If it were in a folder that two checkouts share, such as
// the system's temporary folder, the tests of one checkout would read the
// runs of the other.
const DEFAULT_LOG = path.join(__dirname, "..", "..", ".vscode-test", "stand_in_nxwright.log");

// Reads the stand-in's log `log`: the arguments of each run of the
// subcommand `name`, such as "compile", in order.
function runsIn(log, name) {
  return (fs.existsSync(log)
    ? fs.readFileSync(log, "utf8").trim().split("\n").map((line) => JSON.parse(line)) : [])
    .filter((run) => run[0] === name).map((run) => run.slice(1));
}

// Sets the stand-in as nxwright's command, the first time it is called. The
// extension does not use a new command at once. It first searches for
// nxwright again, then restarts the language server with what it found. The
// function therefore waits until the log shows that the language server
// started through the stand-in. From then on, the extension's commands run
// the stand-in too. A test that runs after every other test sets the
// command back.
async function useStandIn() {
  if (commandBefore !== undefined) {
    return;
  }
  const settings = vscode.workspace.getConfiguration("nxwright");
  commandBefore = settings.get("command");
  testLast("nxwright's command is set back once the tests that use the stand-in are done",
           () => settings.update("command", commandBefore, vscode.ConfigurationTarget.Global));
  const log = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "nxwright-stand-in-")),
                        "server.log");
  process.env.NXWRIGHT_STAND_IN_LOG = log;
  await settings.update("command",
                        [commandBefore[0], path.join(__dirname, "stand_in_nxwright.py")],
                        vscode.ConfigurationTarget.Global);
  await waitFor(() => runsIn(log, "lsp").length > 0, "the language server started by the stand-in");
}

// Runs `body` with the stand-in as nxwright's command. `body` is given three
// arguments:
//  - a new folder to work in;
//  - a function that returns the arguments of each run of a subcommand, such
//    as "compile", in order;
//  - the same function, for the subcommands that the extension runs as a
//    task.
//
// The stand-in logs the runs of this call to a file of their own. Each run
// reads that file's name from this process's environment when it starts. A
// task cannot, because VS Code starts a task in a terminal, which does not
// have this process's environment. A task's run goes to the stand-in's
// default log, which is emptied here first.
async function withStandIn(body) {
  await useStandIn();
  const work = fs.mkdtempSync(path.join(os.tmpdir(), "nxwright-stand-in-"));
  const log = path.join(work, "runs.log");
  process.env.NXWRIGHT_STAND_IN_LOG = log;
  fs.rmSync(DEFAULT_LOG, { force: true });
  await body(work, (name) => runsIn(log, name), (name) => runsIn(DEFAULT_LOG, name));
}

module.exports = { withStandIn };
