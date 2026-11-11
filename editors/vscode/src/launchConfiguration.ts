// The launch configurations that the command "Add a launch configuration"
// adds to a workspace folder's launch.json. One simulates a source folder's
// app. For a project that has an MCU emulator, the command also adds a
// configuration of the Python debugger that runs the emulator. This file is
// kept apart from VS Code's API, so that Node's test runner can check it
// (test/launch-configuration.test.mjs).
import { applyEdits, createScanner, Edit, findNodeAtLocation, modify, parseTree, SyntaxKind }
  from "jsonc-parser";
import { readFile } from "fs/promises";
import * as path from "path";
import { ADDRESS_VARIABLE, ownEmulatorConfiguration, PYTHON_DEBUGGER_TYPE }
  from "./emulatorSession";

// A launch configuration of type nxwright, with the source folder it
// simulates. For a project that has an MCU emulator, the configuration's
// `serialPort` is "emulator", the MCU port that listens for the emulator.
export interface SimulationEntry {
  type: "nxwright";
  request: "launch";
  name: string;
  sourceFolder: string;
  serialPort?: "emulator";
}

// A launch configuration of the Python debugger that runs a project's MCU
// emulator.
export interface EmulatorEntry {
  type: string;
  request: "launch";
  name: string;
  program: string;
  console: "integratedTerminal";
}

// A launch configuration that simulates a source folder, with its name, as
// VS Code starts it.
export interface Simulation {
  name: string;
  [key: string]: unknown;
}

// Returns the configurations among `existing` that simulate `sourceFolder`,
// which lies in `workspaceFolder`, in their order: those of type nxwright
// naming it as their sourceFolder, and having a name to show.
export function simulationsOf(existing: unknown[], workspaceFolder: string,
                              sourceFolder: string, platform: NodeJS.Platform): Simulation[] {
  return existing.filter((entry): entry is Simulation =>
    simulates(entry, workspaceFolder, sourceFolder, platform) &&
    typeof (entry as { name?: unknown }).name === "string" && (entry as Simulation).name !== "");
}

// Returns the entry that simulates `sourceFolder`, for the command to add
// to the launch configurations of the workspace folder `workspaceFolder`.
// `existing` lists those configurations. If one of them simulates the
// source folder already, the function returns undefined.
//
// The entry is named after the app, `name`, or after the source folder when
// `name` is not given. Its `sourceFolder` starts with ${workspaceFolder},
// so that the entry works on other computers (fromWorkspaceFolder). When
// the project has an MCU emulator (`hasEmulator`), the entry's `serialPort`
// is "emulator", the MCU port that listens for the emulator.
export function simulationEntry(existing: unknown[], workspaceFolder: string,
                                sourceFolder: string, platform: NodeJS.Platform,
                                name?: string, hasEmulator = false): SimulationEntry | undefined {
  if (existing.some((entry) => simulates(entry, workspaceFolder, sourceFolder, platform))) {
    return undefined;
  }
  const paths = platform === "win32" ? path.win32 : path.posix;
  return {
    type: "nxwright",
    request: "launch",
    name: `Simulate ${name ?? paths.basename(sourceFolder)}`,
    sourceFolder: fromWorkspaceFolder(workspaceFolder, sourceFolder, platform),
    ...(hasEmulator ? { serialPort: "emulator" as const } : {}),
  };
}

// Returns the entry that runs the MCU emulator whose file is `emulatorFile`,
// for the command to add to the workspace folder's launch configurations.
// The extension uses this entry when it starts the emulator beside a
// simulation, so the user can edit the entry to give the emulator its own
// interpreter, arguments, or environment.
//
// `existing` lists the workspace folder's configurations. If one of them
// runs `emulatorFile` with the Python debugger already
// (ownEmulatorConfiguration), the function returns undefined. The entry is
// named after the app, `name`.
export function emulatorEntry(existing: unknown[], workspaceFolder: string,
                              emulatorFile: string, platform: NodeJS.Platform,
                              name: string): EmulatorEntry | undefined {
  if (ownEmulatorConfiguration(emulatorFile, existing, workspaceFolder, platform)) {
    return undefined;
  }
  return {
    type: PYTHON_DEBUGGER_TYPE,
    request: "launch",
    name: `MCU emulator of ${name}`,
    program: fromWorkspaceFolder(workspaceFolder, emulatorFile, platform),
    console: "integratedTerminal",
  };
}

// Returns `target` as a path that starts with ${workspaceFolder} and uses
// forward slashes, so that it works on other computers. A path on a
// different drive from `workspaceFolder` cannot start that way, and is
// returned unchanged.
function fromWorkspaceFolder(workspaceFolder: string, target: string,
                             platform: NodeJS.Platform): string {
  const paths = platform === "win32" ? path.win32 : path.posix;
  const relative = paths.relative(workspaceFolder, target);
  if (paths.isAbsolute(relative)) {
    return target;
  }
  const written = relative.split(paths.sep).join("/");
  return written === "" ? "${workspaceFolder}" : `\${workspaceFolder}/${written}`;
}

// Whether `entry`, a launch configuration, simulates `sourceFolder`: one of
// type nxwright whose sourceFolder, written from ${workspaceFolder} either
// way or as an absolute path, is that folder. On Windows, paths differing
// only in case are one folder.
function simulates(entry: unknown, workspaceFolder: string, sourceFolder: string,
                   platform: NodeJS.Platform): boolean {
  if (typeof entry !== "object" || entry === null) {
    return false;
  }
  const { type, sourceFolder: named } = entry as { type?: unknown; sourceFolder?: unknown };
  if (type !== "nxwright" || typeof named !== "string") {
    return false;
  }
  const paths = platform === "win32" ? path.win32 : path.posix;
  const key = (folder: string) => {
    const resolved = paths.resolve(folder);
    return platform === "win32" ? resolved.toLowerCase() : resolved;
  };
  return key(named.split("${workspaceFolder}").join(workspaceFolder)) === key(sourceFolder);
}

// A parameter of a launch configuration, as package.json declares it
// (debuggers, configurationAttributes.launch).
export interface ParameterDeclaration {
  type?: string;
  description?: string;
  markdownDescription?: string;
  enum?: unknown[];
  default?: unknown;
  examples?: unknown[];
  properties?: Record<string, ParameterDeclaration>;
}

// Returns the launch parameters that the nxwright debugger declares in the
// package.json file at `packageJsonPath`. They are read from the file. The
// extension's packageJSON in memory will not do: VS Code adds its own
// attributes to it, such as preLaunchTask, as it builds launch.json's schema.
export async function declaredLaunchParameters(packageJsonPath: string):
    Promise<Record<string, ParameterDeclaration>> {
  const packageJson = JSON.parse(await readFile(packageJsonPath, "utf8")) as {
    contributes: { debuggers: { type: string; configurationAttributes: {
      launch: { properties: Record<string, ParameterDeclaration> } } }[] } };
  return packageJson.contributes.debuggers.find((entry) => entry.type === "nxwright")!
    .configurationAttributes.launch.properties;
}

// The parameters that debug a test, which a simulation does not take.
const TEST_PARAMETERS = new Set(["testFolder", "test"]);

// Returns the text of `entry`, a launch configuration simulating a source
// folder, as Add a launch configuration writes it: its own keys, then each
// other parameter a simulation takes, as `declared` declares them, commented
// out after a one-line comment giving its description and its choices, with a
// sample value: its example, its default, its first choice, or an empty value
// of its type. Each line ends with a comma, which launch.json takes after the
// last one too, so that any commented line can be put back as it is.
export function simulationEntryText(entry: SimulationEntry,
                                    declared: Record<string, ParameterDeclaration>): string {
  const lines = ["{"];
  for (const [key, value] of Object.entries(entry)) {
    lines.push(`  "${key}": ${JSON.stringify(value)},`);
  }
  for (const [key, declaration] of Object.entries(declared)) {
    if (key in entry || TEST_PARAMETERS.has(key)) {
      continue;
    }
    let description = declaration.description ?? declaration.markdownDescription ?? "";
    if (declaration.enum?.length) {
      description += ` ${choices(declaration.enum)}.`;
    }
    lines.push(`  // ${description.trim()}`);
    lines.push(`  // "${key}": ${written(sampleOf(declaration))},`);
  }
  lines.push("}");
  return lines.join("\n");
}

// Returns the text that Add a launch configuration writes for `entry`, a
// launch configuration that runs a project's MCU emulator. The text is a
// comment that explains when the configuration is used, then the entry's
// keys. Each line of a key ends with a comma, the same way as in a
// simulation's entry (simulationEntryText).
export function emulatorEntryText(entry: EmulatorEntry): string {
  const lines = [
    "{",
    "  // Runs the project's MCU emulator.",
    "  // nxwright starts this configuration with the simulation, and sets " +
      `${ADDRESS_VARIABLE} to the simulator's address.`,
    "  // Edit the configuration to change the emulator's interpreter, arguments, or " +
      "environment variables.",
    "  // If you start it on its own, the emulator has no simulator to connect to.",
  ];
  for (const [key, value] of Object.entries(entry)) {
    lines.push(`  "${key}": ${JSON.stringify(value)},`);
  }
  lines.push("}");
  return lines.join("\n");
}

// A parameter's choices, quoted, as 'text', 'hex' or 'both'.
function choices(values: unknown[]): string {
  const quoted = values.map((value) => `'${String(value)}'`);
  return quoted.length < 2 ? quoted.join("")
    : `${quoted.slice(0, -1).join(", ")} or ${quoted[quoted.length - 1]}`;
}

// A parameter's sample value: its first example, its default, its first
// choice, or an empty value of its type, an object's of each of its
// properties.
function sampleOf(declaration: ParameterDeclaration): unknown {
  if (declaration.examples?.length) {
    return declaration.examples[0];
  }
  if ("default" in declaration) {
    return declaration.default;
  }
  if (declaration.enum?.length) {
    return declaration.enum[0];
  }
  switch (declaration.type) {
    case "integer":
    case "number":
      return 0;
    case "boolean":
      return false;
    case "array":
      return [];
    case "object":
      return Object.fromEntries(Object.entries(declaration.properties ?? {})
        .map(([key, property]) => [key, sampleOf(property)]));
    default:
      return "";
  }
}

// A value written on one line, with a space after each colon and comma.
function written(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(written).join(", ")}]`;
  }
  if (typeof value === "object" && value !== null) {
    return `{${Object.entries(value).map(([key, inner]) =>
      `${JSON.stringify(key)}: ${written(inner)}`).join(", ")}}`;
  }
  return JSON.stringify(value);
}

// Returns the edits that add `entryText` at the end of the configurations
// of the launch.json whose text is `text`. `entryText` is one entry, or
// several joined by a comma and a line break. The rest of the file stays as
// it is, comments included.
//
// If the file's last configuration has no comma after it, the edits add
// one. The new text then starts on the next line, so that a comment ending
// that line stays with the configuration it is about. The new text is
// indented the same way as the file, with tabs if the file uses tabs.
//
// An empty file becomes a launch.json whose only configurations are the new
// ones. A file without configurations first gets an empty list of them,
// through jsonc-parser's modify, and is then written whole. If the file's
// top level is not an object, such as a file with only comments, the
// function returns undefined and nothing is added.
export function simulationEntryEdits(text: string, entryText: string): Edit[] | undefined {
  const eol = text.includes("\r\n") ? "\r\n" : "\n";
  if (text.trim() === "") {
    return [{ offset: 0, length: text.length, content: [
      "{", '  "version": "0.2.0",', '  "configurations": [',
      indented(entryText, "    ", eol), "  ]", "}", ""].join(eol) }];
  }
  const tree = parseTree(text);
  if (tree?.type !== "object") {
    return undefined;
  }
  const configurations = findNodeAtLocation(tree, ["configurations"]);
  const tabs = indentedWithTabs(text);
  if (!configurations) {
    const withList = applyEdits(text, modify(text, ["configurations"], [], {
      formattingOptions: { insertSpaces: !tabs, tabSize: 2, eol } }));
    const edits = simulationEntryEdits(withList, entryText);
    return edits && [{ offset: 0, length: text.length, content: applyEdits(withList, edits) }];
  }
  if (configurations.type !== "array") {
    return undefined;
  }
  // The entry's own indentation, two spaces a level, in tabs in a file indented so.
  if (tabs) {
    entryText = entryText.replace(/^((?: {2})+)/gm, (spaces) => "\t".repeat(spaces.length / 2));
  }
  const keyIndent = indentationAt(text, configurations.parent!.offset);
  const entries = configurations.children ?? [];
  if (entries.length === 0) {
    return [{ offset: configurations.offset + 1, length: 0,
              content: eol + indented(entryText, keyIndent + (tabs ? "\t" : "  "), eol) + eol +
                keyIndent }];
  }
  const last = entries[entries.length - 1];
  const itemIndent = indentationAt(text, entries[0].offset);
  const end = last.offset + last.length;
  const comma = commaAfter(text, end);
  const edits: Edit[] = comma === undefined ? [{ offset: end, length: 0, content: "," }] : [];
  edits.push({ offset: lineEnd(text, comma ?? end), length: 0,
               content: eol + indented(entryText, itemIndent, eol) });
  return edits;
}

// Whether a file is indented with tabs: a line of it starts with one.
function indentedWithTabs(text: string): boolean {
  return /\n\t/.test(text);
}

// Each line of `text` after `indent`, the lines joined by `eol`.
function indented(text: string, indent: string, eol: string): string {
  return text.split("\n").map((line) => indent + line).join(eol);
}

// The spaces and tabs starting the line that holds `offset`.
function indentationAt(text: string, offset: number): string {
  const start = text.lastIndexOf("\n", offset - 1) + 1;
  return /^[ \t]*/.exec(text.slice(start))![0];
}

// The offset of the end of the line holding `offset`, before its line break.
function lineEnd(text: string, offset: number): number {
  const found = text.indexOf("\n", offset);
  const end = found === -1 ? text.length : found;
  return text[end - 1] === "\r" ? end - 1 : end;
}

// The offset just after a comma following `offset`, past spaces, line
// breaks, and comments; or undefined when the next token is no comma.
function commaAfter(text: string, offset: number): number | undefined {
  const scanner = createScanner(text, false);
  scanner.setPosition(offset);
  let token = scanner.scan();
  while (token === SyntaxKind.Trivia || token === SyntaxKind.LineBreakTrivia ||
         token === SyntaxKind.LineCommentTrivia || token === SyntaxKind.BlockCommentTrivia) {
    token = scanner.scan();
  }
  return token === SyntaxKind.CommaToken ? scanner.getTokenOffset() + 1 : undefined;
}
