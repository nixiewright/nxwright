// The launch configuration that simulates a source folder's app
// (src/launchConfiguration.ts, compiled to out/ before the tests run).
import assert from "node:assert/strict";
import { test } from "node:test";
import { applyEdits, parse } from "jsonc-parser";
import { fileURLToPath } from "node:url";
import { declaredLaunchParameters, simulationEntry, simulationEntryEdits, simulationEntryText,
  simulationsOf } from "../out/launchConfiguration.js";

const WORKSPACE = "C:\\work";
const FOLDER = "C:\\work\\screens\\app";

// The names of the configurations simulating FOLDER among `existing`.
const simulationNames = (existing) =>
  simulationsOf(existing, WORKSPACE, FOLDER, "win32").map((entry) => entry.name);

test("an entry is added to no entries, its folder under ${workspaceFolder}", () => {
  assert.deepEqual(simulationEntry([], WORKSPACE, FOLDER, "win32"), {
    type: "nxwright", request: "launch", name: "Simulate app",
    sourceFolder: "${workspaceFolder}/screens/app",
  });
});

test("an entry is named after the app, written as JSON whatever the name holds", () => {
  const entry = simulationEntry([], WORKSPACE, FOLDER, "win32", 'Kitchen "clock" \\ 2');
  assert.equal(entry.name, 'Simulate Kitchen "clock" \\ 2');
  assert.equal(parse(simulationEntryText(entry, {}), [], { allowTrailingComma: true }).name,
               entry.name);
});

test("an entry is added beside others", () => {
  const others = [{ type: "node", request: "launch", name: "Server" },
                  { type: "nxwright", request: "launch", name: "Simulate other",
                    sourceFolder: "${workspaceFolder}/other" }];
  assert.equal(simulationEntry(others, WORKSPACE, FOLDER, "win32").sourceFolder,
               "${workspaceFolder}/screens/app");
});

test("a source folder that is the workspace folder is ${workspaceFolder} itself", () => {
  assert.equal(simulationEntry([], FOLDER, FOLDER, "win32").sourceFolder, "${workspaceFolder}");
});

test("none is added when an entry simulates the folder already", () => {
  for (const sourceFolder of ["${workspaceFolder}/screens/app", "${workspaceFolder}\\screens\\app",
                              "C:\\work\\screens\\app", "c:/work/screens/app/"]) {
    const existing = [{ type: "nxwright", request: "launch", name: "Mine", sourceFolder }];
    assert.equal(simulationEntry(existing, WORKSPACE, FOLDER, "win32"), undefined, sourceFolder);
  }
});

test("an entry of another type naming the folder does not count", () => {
  const existing = [{ type: "python", sourceFolder: "${workspaceFolder}/screens/app" }];
  assert.notEqual(simulationEntry(existing, WORKSPACE, FOLDER, "win32"), undefined);
});

test("elsewhere than on Windows, paths differing in case are different folders", () => {
  const existing = [{ type: "nxwright", sourceFolder: "${workspaceFolder}/Screens/App" }];
  assert.notEqual(simulationEntry(existing, "/work", "/work/screens/app", "linux"), undefined);
  assert.equal(simulationEntry(existing, "/work", "/work/Screens/App", "linux"), undefined);
});

test("the configurations simulating a folder are found among others, by name", () => {
  const existing = [
    { type: "node", request: "launch", name: "Server" },
    { type: "nxwright", request: "launch", name: "Simulate app",
      sourceFolder: "${workspaceFolder}/screens/app" },
    { type: "nxwright", request: "launch", name: "Settings page", page: "settings",
      sourceFolder: "C:\\work\\screens\\app" },
    { type: "nxwright", request: "launch", name: "Other",
      sourceFolder: "${workspaceFolder}/other" },
    { type: "nxwright", request: "launch", name: "A test", testFolder: "${workspaceFolder}/tests" },
  ];
  assert.deepEqual(simulationNames(existing), ["Simulate app", "Settings page"]);
});

test("a configuration without a name is not listed", () => {
  const existing = [{ type: "nxwright", sourceFolder: "${workspaceFolder}/screens/app" }];
  assert.deepEqual(simulationNames(existing), []);
});

test("each configuration is found whole, those sharing a name included", () => {
  const first = { type: "nxwright", name: "Twice",
                  sourceFolder: "${workspaceFolder}/screens/app" };
  const second = { ...first, page: "settings" };
  assert.deepEqual(simulationsOf([first, second], WORKSPACE, FOLDER, "win32"), [first, second]);
});

// A few parameters, declared as package.json declares them.
const DECLARED = {
  testFolder: { type: "string", description: "To debug a test: the folder of tests." },
  test: { type: "string", description: "To debug a test: its id." },
  sourceFolder: { type: "string", description: "To simulate an app: its source folder." },
  page: { type: "string", description: "In a simulation: the page to start on." },
  values: { type: "object", description: "The values to start with.", default: {},
            examples: [{ "t0.txt": "Hello", "n0.val": 5 }] },
  serialPort: { type: "object", description: "The serial port.",
                properties: { name: { type: "string" }, baud: { type: "integer" } } },
  stopOnEntry: { type: "boolean", description: "Stop at the first line that runs." },
  logSent: { type: "string", enum: ["text", "hex", "both"], default: "hex",
             description: "How the log shows what the screen sends." },
};
const ENTRY = { type: "nxwright", request: "launch", name: "Simulate app",
                sourceFolder: "${workspaceFolder}/screens/app" };

test("the entry's text gives every parameter but the test's, commented out", () => {
  assert.equal(simulationEntryText(ENTRY, DECLARED), [
    "{",
    '  "type": "nxwright",',
    '  "request": "launch",',
    '  "name": "Simulate app",',
    '  "sourceFolder": "${workspaceFolder}/screens/app",',
    "  // In a simulation: the page to start on.",
    '  // "page": "",',
    "  // The values to start with.",
    '  // "values": {"t0.txt": "Hello", "n0.val": 5},',
    "  // The serial port.",
    '  // "serialPort": {"name": "", "baud": 0},',
    "  // Stop at the first line that runs.",
    '  // "stopOnEntry": false,',
    "  // How the log shows what the screen sends. 'text', 'hex' or 'both'.",
    '  // "logSent": "hex",',
    "}",
  ].join("\n"));
});

test("a long description stays on one line of comment", () => {
  const description = "word ".repeat(40).trim();
  const long = { page: { type: "string", description } };
  const lines = simulationEntryText(ENTRY, long).split("\n");
  assert.deepEqual(lines.filter((line) => line.startsWith("  // word")), [`  // ${description}`]);
});

test("the parameters are the extension's own, as its package.json file declares them", async () => {
  const declared = await declaredLaunchParameters(
    fileURLToPath(new URL("../package.json", import.meta.url)));
  assert.ok("sourceFolder" in declared && "logSent" in declared);
  for (const [key, declaration] of Object.entries(declared)) {
    assert.ok(declaration.description, `${key} has a description`);
  }
  for (const key of ["preLaunchTask", "postDebugTask", "presentation", "debugServer"]) {
    assert.ok(!(key in declared), `${key} is VS Code's own`);
  }
  const lines = simulationEntryText(ENTRY, declared).split("\n");
  assert.ok(!lines.includes("  // "), "no comment is empty");
});

// Applies the edits to `text`, and returns the result, which parses.
function placed(text) {
  const edits = simulationEntryEdits(text, simulationEntryText(ENTRY, DECLARED));
  const result = applyEdits(text, edits);
  const errors = [];
  const parsed = parse(result, errors, { allowTrailingComma: true });
  assert.deepEqual(errors, [], result);
  return { result, parsed };
}

test("the entry goes after the other entries, the file's comments staying", () => {
  const text = [
    "{",
    "  // My configurations.",
    '  "version": "0.2.0",',
    '  "configurations": [',
    '    { "type": "node", "request": "launch", "name": "Server" } // the server',
    "  ]",
    "}",
  ].join("\n");
  const { result, parsed } = placed(text);
  assert.deepEqual(parsed.configurations.map((entry) => entry.name), ["Server", "Simulate app"]);
  assert.ok(result.includes("// My configurations."));
  assert.ok(result.includes("// the server"));
  assert.ok(result.includes('\n    {\n      "type": "nxwright",'));
});

test("the entry goes after an entry followed by a comma already", () => {
  const text = '{\n  "configurations": [\n    { "name": "Server" },\n  ]\n}';
  const { parsed } = placed(text);
  assert.deepEqual(parsed.configurations.map((entry) => entry.name), ["Server", "Simulate app"]);
});

test("the entry goes into an empty list", () => {
  const { parsed } = placed('{\n  "version": "0.2.0",\n  "configurations": []\n}');
  assert.deepEqual(parsed.configurations.map((entry) => entry.name), ["Simulate app"]);
});

test("a file without configurations gets them", () => {
  const { parsed } = placed('{\n  // Mine.\n  "version": "0.2.0"\n}');
  assert.deepEqual(parsed.configurations.map((entry) => entry.name), ["Simulate app"]);
});

test("an empty file becomes a launch.json holding the entry", () => {
  const { parsed } = placed("");
  assert.equal(parsed.version, "0.2.0");
  assert.deepEqual(parsed.configurations.map((entry) => entry.name), ["Simulate app"]);
});

test("a file whose top level is no object, or holds only comments, is refused", () => {
  const entry = simulationEntryText(ENTRY, DECLARED);
  assert.equal(simulationEntryEdits("[]", entry), undefined);
  assert.equal(simulationEntryEdits("// nothing yet\n", entry), undefined);
});

test("a file with Windows line breaks keeps them", () => {
  const text = '{\r\n  "configurations": [\r\n    { "name": "Server" }\r\n  ]\r\n}\r\n';
  const { result, parsed } = placed(text);
  assert.deepEqual(parsed.configurations.map((entry) => entry.name), ["Server", "Simulate app"]);
  assert.equal(result.replace(/\r\n/g, "").includes("\n"), false);
});

test("a file indented with tabs gets the entry indented with tabs", () => {
  const text = '{\n\t"configurations": [\n\t\t{ "name": "Server" }\n\t]\n}';
  const { result } = placed(text);
  assert.ok(result.includes('\n\t\t{\n\t\t\t"type": "nxwright",'), result);
  assert.equal(/\n\t* +\S/.test(result), false, result);
});

test("an empty list in a file indented with tabs gets the entry indented with tabs", () => {
  const { result } = placed('{\n\t"configurations": []\n}');
  assert.ok(result.includes('[\n\t\t{\n\t\t\t"type": "nxwright",'), result);
  assert.equal(/\n\t* +\S/.test(result), false, result);
});
