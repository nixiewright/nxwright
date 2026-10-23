// nxwright's tests in VS Code: Test Explorer lists the tests of each test
// folder, and runs or debugs them; above each test method of a test file, a
// link debugs the test and its screen code. The tests are found and run by
// `nxwright test`, with --list and --report; debugging starts the debug
// adapter, `nxwright debug-adapter`, with the test's id.
import { execFile } from "child_process";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as vscode from "vscode";

// One test's result, as `nxwright test --report` writes it.
interface TestResult {
  id: string;
  outcome: "passed" | "failed" | "error" | "skipped";
  message?: string;
  file?: string;
  line?: number;
}

// Sets up Test Explorer and the debug links. `command` returns the command
// that runs nxwright, ready to run, or undefined, having said why, when
// there is none.
export function startTests(context: vscode.ExtensionContext,
                           command: () => Promise<string[] | undefined>): void {
  const controller = vscode.tests.createTestController("nxwright", "nxwright screen tests");
  context.subscriptions.push(controller);
  // Tests are listed when Test Explorer opens, and again on its refresh button.
  const discover = async () => {
    controller.items.replace([]);
    const run = await command();
    if (run === undefined) {
      return;
    }
    for (const folder of await testFolders()) {
      await listTests(controller, run, folder);
    }
  };
  controller.resolveHandler = discover;
  controller.refreshHandler = discover;
  controller.createRunProfile("Run", vscode.TestRunProfileKind.Run, async (request, token) => {
    const run = await command();
    if (run !== undefined) {
      await runTests(controller, run, request, token);
    }
  });
  // The debugger follows one test at a time: the first one chosen.
  controller.createRunProfile("Debug", vscode.TestRunProfileKind.Debug, async (request) => {
    const first = (request.include ?? []).flatMap(leaves)[0];
    if (first) {
      const [folder, test] = first.id.split("|");
      await debugTest(folder, test);
    } else {
      vscode.window.showInformationMessage("Choose a test to debug: the debugger follows one "
                                           + "test at a time.");
    }
  });
  context.subscriptions.push(
    vscode.commands.registerCommand("nxwright.debugTest", debugTest),
    vscode.languages.registerCodeLensProvider({ language: "python", scheme: "file" },
                                              new DebugLinks()),
  );
}

// Returns the folders of tests: those the setting nxwright.testFolders names,
// else each folder named "tests" beside a source folder.
async function testFolders(): Promise<string[]> {
  const configured = vscode.workspace.getConfiguration("nxwright").get<string[]>("testFolders");
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "";
  if (configured && configured.length > 0) {
    return configured.map((folder) => path.resolve(root, folder));
  }
  const apps = await vscode.workspace.findFiles("**/app.toml", "**/node_modules/**");
  const folders = apps.map((app) => path.join(path.dirname(path.dirname(app.fsPath)), "tests"));
  return [...new Set(folders)].filter((folder) => fs.existsSync(folder));
}

// Adds a folder's tests to Test Explorer: the folder, then each test's
// module, class, and method, from `nxwright test --list`. A test item's id is
// "<folder>|<test id>". When listing fails, the folder shows why.
async function listTests(controller: vscode.TestController, command: string[], folder: string) {
  const listed = await runNxwright(command, ["test", folder, "--list"]);
  const top = controller.createTestItem(folder, path.basename(path.dirname(folder)) + " tests",
                                        vscode.Uri.file(folder));
  controller.items.add(top);
  if (!listed.ok) {
    top.error = listed.output;
    return;
  }
  for (const id of listed.output.split(/\r?\n/).filter((line) => line.trim())) {
    // A module in a package of the folder has dots too: pkg.test_x.Class.method.
    const parts = id.split(".");
    if (parts.length < 3) {
      continue;
    }
    const method = parts.pop()!;
    const testClass = parts.pop()!;
    const module = parts.join(".");
    const file = vscode.Uri.file(path.join(folder, ...parts) + ".py");
    const moduleItem = child(controller, top, folder + "|" + module, module, file);
    const classItem = child(controller, moduleItem, folder + "|" + module + "." + testClass,
                            testClass, file);
    const methodItem = child(controller, classItem, folder + "|" + id, method, file);
    methodItem.range = lineOf(file.fsPath, new RegExp(`def ${method}\\b`));
  }
}

function child(controller: vscode.TestController, parent: vscode.TestItem, id: string,
               label: string, uri: vscode.Uri): vscode.TestItem {
  const existing = parent.children.get(id);
  if (existing) {
    return existing;
  }
  const item = controller.createTestItem(id, label, uri);
  parent.children.add(item);
  return item;
}

// Runs the requested tests, folder by folder, and shows each one's result.
async function runTests(controller: vscode.TestController, command: string[],
                        request: vscode.TestRunRequest, token: vscode.CancellationToken) {
  const run = controller.createTestRun(request);
  const chosen = request.include ?? [...collect(controller.items)];
  const byFolder = new Map<string, vscode.TestItem[]>();
  for (const item of chosen) {
    for (const leaf of leaves(item)) {
      const folder = leaf.id.split("|")[0];
      byFolder.set(folder, [...(byFolder.get(folder) ?? []), leaf]);
      run.started(leaf);
    }
  }
  for (const [folder, items] of byFolder) {
    if (token.isCancellationRequested) {
      break;
    }
    const report = path.join(os.tmpdir(), `nxwright-report-${process.pid}.json`);
    fs.rmSync(report, { force: true });
    const patterns = items.flatMap((item) => ["-k", item.id.split("|")[1]]);
    const { output } = await runNxwright(command,
                                         ["test", folder, ...patterns, "--report", report]);
    run.appendOutput(output.replace(/\r?\n/g, "\r\n"));
    const results: TestResult[] = fs.existsSync(report)
      ? JSON.parse(fs.readFileSync(report, "utf-8")) : [];
    for (const item of items) {
      const result = results.find((found) => found.id === item.id.split("|")[1]);
      if (!result) {
        run.errored(item, new vscode.TestMessage("The test did not run."));
      } else if (result.outcome === "passed") {
        run.passed(item);
      } else if (result.outcome === "skipped") {
        run.skipped(item);
      } else {
        const message = new vscode.TestMessage(result.message ?? result.outcome);
        if (result.file && result.line) {
          message.location = new vscode.Location(vscode.Uri.file(result.file),
                                                 new vscode.Position(result.line - 1, 0));
        }
        if (result.outcome === "failed") {
          run.failed(item, message);
        } else {
          run.errored(item, message);
        }
      }
    }
  }
  run.end();
}

function* collect(items: vscode.TestItemCollection): Generator<vscode.TestItem> {
  for (const [, item] of items) {
    yield item;
  }
}

// Returns the test methods an item holds: itself, when it is one. Modules and
// classes are made only with a method under them, so an item without children
// is a method, unless it is a folder that holds no tests.
function leaves(item: vscode.TestItem): vscode.TestItem[] {
  if (item.children.size === 0) {
    return item.id.includes("|") ? [item] : [];
  }
  return [...collect(item.children)].flatMap(leaves);
}

// Debugs the test `test` of the folder `folder`, and the screen code it runs.
async function debugTest(folder: string, test: string): Promise<void> {
  await vscode.debug.startDebugging(vscode.workspace.workspaceFolders?.[0], {
    type: "nxwright",
    request: "launch",
    name: "Debug " + test,
    testFolder: folder,
    test,
  });
}

// The "Debug test" link above each test method of a test file: a file
// named test*.py in a folder of tests, or in a package inside one.
class DebugLinks implements vscode.CodeLensProvider {
  async provideCodeLenses(document: vscode.TextDocument): Promise<vscode.CodeLens[]> {
    const name = path.basename(document.fileName);
    if (!/^test.*\.py$/.test(name)) {
      return [];
    }
    // Its test id starts with its path from the folder of tests, in dots.
    const folder = (await testFolders()).find((candidate) => inside(candidate, document.fileName));
    if (!folder) {
      return [];
    }
    const module = path.relative(folder, document.fileName).slice(0, -3).split(path.sep).join(".");
    const links: vscode.CodeLens[] = [];
    let testClass: string | undefined;
    for (let number = 0; number < document.lineCount; number++) {
      const text = document.lineAt(number).text;
      const classMatch = /^class (\w+)/.exec(text);
      const methodMatch = /^\s+def (test\w*)\(/.exec(text);
      if (classMatch) {
        testClass = classMatch[1];
      } else if (methodMatch && testClass) {
        links.push(new vscode.CodeLens(document.lineAt(number).range, {
          title: "Debug test",
          command: "nxwright.debugTest",
          arguments: [folder, `${module}.${testClass}.${methodMatch[1]}`],
        }));
      }
    }
    return links;
  }
}

// True when `file` lies inside the folder `folder`.
function inside(folder: string, file: string): boolean {
  const relative = path.relative(folder, file);
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}

// Returns the range of the first line of a file matching `pattern`, if any.
function lineOf(file: string, pattern: RegExp): vscode.Range | undefined {
  const lines = fs.existsSync(file) ? fs.readFileSync(file, "utf-8").split(/\r?\n/) : [];
  const number = lines.findIndex((line) => pattern.test(line));
  return number >= 0 ? new vscode.Range(number, 0, number, 0) : undefined;
}

// Runs nxwright with `args`; returns whether it succeeded, and its output.
// A failing test makes `nxwright test` fail, so callers decide what failing means.
function runNxwright(command: string[], args: string[]): Promise<{ ok: boolean; output: string }> {
  return new Promise((resolve) => {
    execFile(command[0], [...command.slice(1), ...args],
             { cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath, maxBuffer: 1 << 24 },
             (error, stdout, stderr) => resolve({ ok: !error, output: stdout + stderr }));
  });
}
