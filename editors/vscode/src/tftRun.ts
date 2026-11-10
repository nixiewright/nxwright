// Running the toolchain's commands on TFT files with --json: compile, upload,
// and ports. With --json, each prints one JSON object per line on its
// output, such as {"event": "progress", ...}, and its words for people on
// its errors' stream (the toolchain's docs/commands.md, Output for
// programs). This module runs such a command as a process of its own, hands
// each object over as it comes, and gives back the exit code and the
// words. It uses no VS Code API, so Node runs its tests (test/tft-run.test.mjs).

import { spawn } from "child_process";

// One object the command printed, as JSON gives it.
export type JsonEvent = Record<string, unknown>;

// A run's end: its exit code, or undefined when it gave none, as when it
// could not start or was stopped; the objects it printed, in order; the
// lines it printed that are no JSON object, such as decompile's list of
// names; what it wrote on its errors' stream, with why it could not start,
// if so; and whether it was stopped through its signal.
export interface JsonRun {
  code: number | undefined;
  events: JsonEvent[];
  printed: string[];
  errors: string;
  stopped: boolean;
}

export interface JsonRunOptions {
  cwd?: string;
  // Called with each object as it is read.
  onEvent?: (event: JsonEvent) => void;
  // Stops the command once aborted.
  signal?: AbortSignal;
}

// Reads JSON objects, one per line, from text that arrives in pieces of any
// size. A line that is not a JSON object, such as a Python traceback, is
// kept in `other`, not handed over.
export class JsonLines {
  readonly other: string[] = [];
  private pending = "";

  constructor(private readonly onEvent: (event: JsonEvent) => void) {}

  add(text: string): void {
    this.pending += text;
    const lines = this.pending.split("\n");
    this.pending = lines.pop() ?? "";
    lines.forEach((line) => this.read(line));
  }

  // The output ended: a last line without its line break is read too.
  end(): void {
    this.read(this.pending);
    this.pending = "";
  }

  private read(line: string): void {
    const text = line.trim();
    if (!text) {
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = undefined;
    }
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      this.onEvent(parsed as JsonEvent);
    } else {
      this.other.push(text);
    }
  }
}

// Runs `command`, the program and its own arguments, with `args` after them,
// and resolves once it has ended.
export function runJson(command: string[], args: string[],
                        options: JsonRunOptions = {}): Promise<JsonRun> {
  return new Promise((resolve) => {
    const events: JsonEvent[] = [];
    let errors = "";
    let stopped = false;
    const lines = new JsonLines((event) => {
      events.push(event);
      options.onEvent?.(event);
    });
    const child = spawn(command[0], [...command.slice(1), ...args], {
      cwd: options.cwd, windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
    });
    const stop = () => {
      stopped = true;
      child.kill();
    };
    if (options.signal?.aborted) {
      stop();
    } else {
      options.signal?.addEventListener("abort", stop, { once: true });
    }
    child.stdout.setEncoding("utf8").on("data", (text: string) => lines.add(text));
    child.stderr.setEncoding("utf8").on("data", (text: string) => { errors += text; });
    let finished = false;
    const finish = (code: number | undefined) => {
      if (finished) {
        return;
      }
      finished = true;
      options.signal?.removeEventListener("abort", stop);
      lines.end();
      resolve({ code, events, printed: lines.other, errors, stopped });
    };
    child.on("error", (error) => {
      errors += `${error.message}\n`;
      finish(undefined);
    });
    // "close", not "exit": by then both streams have been read whole.
    child.on("close", (code) => finish(code ?? undefined));
  });
}

// The most lines of warnings that Decompile shows in its dialog.
const MOST_SHOWN = 12;

// What Decompile shows once `nxwright decompile` has written the folder.
// `detail` contains the warnings that `nxwright decompile` wrote, for the
// detail of a warning dialog, and is left out when there were none.
export interface DecompiledReport {
  message: string;
  detail?: string;
}

// Returns what Decompile shows once `nxwright decompile` has written
// `folder` from the TFT file `file`. `errors` is what `nxwright decompile`
// wrote on its errors' stream, which contains its warnings.
export function decompiledReport(file: string, folder: string, errors: string): DecompiledReport {
  const warnings = roundTripDifferences(errors);
  const done = `nxwright: decompiled ${file} into ${folder}`;
  return warnings ? { message: `${done}, with warnings.`, detail: warnings }
    : { message: `${done}.` };
}

// Returns the warnings in `errors` as text for a dialog, or "" when there
// are none. The warnings come from the round trip, the check in which
// `nxwright decompile` compiles the folder again and compares the result
// with the TFT file. They give each difference, or why the folder could
// not be compiled again. Advice for the command line, such as passing
// --continue-unconfirmed, is left out. Only the first MOST_SHOWN lines are
// kept, and a last line then gives how many were left out.
export function roundTripDifferences(errors: string): string {
  const lines = errors.split("\n")
    .filter((line) => line.trim() && !line.includes("--continue-unconfirmed"))
    .map((line) => line.replace(/^nxwright decompile: (warning: )?/, ""))
    .map((line) => line.charAt(0).toUpperCase() + line.slice(1));
  if (lines.length <= MOST_SHOWN) {
    return lines.join("\n");
  }
  return [...lines.slice(0, MOST_SHOWN),
          `And ${lines.length - MOST_SHOWN} more lines, in the output panel.`].join("\n");
}
