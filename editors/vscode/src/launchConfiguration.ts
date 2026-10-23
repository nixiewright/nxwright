// The launch configuration that simulates a source folder's app, as the
// command "Add a launch configuration" adds it to its workspace folder's
// launch.json. Kept apart from VS Code, which test/ tests.
import { applyEdits, createScanner, Edit, findNodeAtLocation, modify, parseTree, SyntaxKind }
  from "jsonc-parser";
import { readFile } from "fs/promises";
import * as path from "path";

// A launch configuration of type nxwright naming the source folder it simulates.
export interface SimulationEntry {
  type: "nxwright";
  request: "launch";
  name: string;
  sourceFolder: string;
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

// Returns the entry simulating `sourceFolder`, which lies in `workspaceFolder`,
// named after the app `name`, the folder's own by default, to add to the
// workspace folder's launch configurations `existing`; or
// undefined when one of them simulates that folder already. Its folder is
// written from ${workspaceFolder}, with forward slashes, so that it holds on
// other computers.
export function simulationEntry(existing: unknown[], workspaceFolder: string,
                                sourceFolder: string, platform: NodeJS.Platform,
                                name?: string): SimulationEntry | undefined {
  if (existing.some((entry) => simulates(entry, workspaceFolder, sourceFolder, platform))) {
    return undefined;
  }
  const paths = platform === "win32" ? path.win32 : path.posix;
  const relative = paths.relative(workspaceFolder, sourceFolder).split(paths.sep).join("/");
  return {
    type: "nxwright",
    request: "launch",
    name: `Simulate ${name ?? paths.basename(sourceFolder)}`,
    sourceFolder: relative === "" ? "${workspaceFolder}" : `\${workspaceFolder}/${relative}`,
  };
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

// Returns the edits that add the entry `entryText` to the launch.json whose
// text is `text`, last in its configurations, keeping the rest as it is,
// comments included. After the last entry, a comma is added unless one
// follows it already; the entry then goes after the end of that line, so
// that a comment ending the line stays with the entry it is about. An empty
// file becomes a launch.json holding the entry; one without configurations
// gets them first, through jsonc-parser's modify, and is then written whole.
// The entry is indented as the file is, with tabs in a file indented so.
// Returns undefined for a file whose top level is no object, such as one
// holding only comments, which nothing is added to.
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
