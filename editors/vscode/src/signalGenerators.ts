// The Signal generator panel, where the user sets up generators that send
// values to the running simulation, the way devices on the serial line
// would (nxwright/testing/signal_generators.py). The Simulator section's
// "Signal generator" button opens it beside the screen (simulator.ts). The
// panel's page, media/signal-generators.mjs, keeps the generators'
// settings. This file passes the page's requests on to the simulation's
// session as the adapter's custom requests
// (nxwright/debug_adapter/adapter.py). It also shows the dialogs that save
// the generators to a settings file, open one, and open a CSV file of a
// custom wave's values. These files can be anywhere on the computer.
import * as path from "path";
import * as vscode from "vscode";
import { webviewPage } from "./webviewPage";

// How long the panel waits for an app that is still starting before it
// asks for its waveforms again, in ms, and how many times it asks.
const ASK_AGAIN = 500;
const MOST_ASKS = 40;

export class SignalGeneratorPanel {
  private panel: vscode.WebviewPanel | undefined;
  // The folder the last file was saved to or opened from, which the next
  // dialog starts in.
  private lastFolder: vscode.Uri | undefined;

  constructor(private readonly extensionUri: vscode.Uri) {}

  // Opens the panel for the simulation of `session`, or shows it when it is
  // open already.
  open(session: vscode.DebugSession): void {
    if (this.panel) {
      this.panel.reveal(undefined, false);
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      "nxwrightSignalGenerator",
      "Signal generator",
      { viewColumn: vscode.ViewColumn.Beside, preserveFocus: false },
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, "media")],
      },
    );
    panel.webview.html = webviewPage(panel.webview, this.extensionUri, {
      script: "signal-generators.mjs", styles: STYLES, body: BODY,
    });
    panel.webview.onDidReceiveMessage((message) => void this.received(session, panel, message));
    panel.onDidDispose(() => {
      if (this.panel === panel) {
        this.panel = undefined;
      }
    });
    this.panel = panel;
  }

  // Closes the panel: its simulation ended, and its generators with it.
  close(): void {
    this.panel?.dispose();
  }

  // Does what the page asks. A message about one generator carries the
  // page's `key` for it, which the reply gives back. What the simulation
  // refuses goes back to the page, which shows it.
  private async received(session: vscode.DebugSession, panel: vscode.WebviewPanel,
                         message: { type?: string; [name: string]: unknown }): Promise<void> {
    // A panel closed meanwhile takes no reply.
    const post = (reply: object) => {
      if (this.panel === panel) {
        void panel.webview.postMessage(reply);
      }
    };
    try {
      if (message.type === "ready") {
        post({ type: "state", ...await this.state(session, panel) });
      } else if (message.type === "start") {
        const started = await session.customRequest("nxwright/startGenerator",
                                                    { settings: message.settings });
        post({ type: "started", key: message.key, number: started.number });
      } else if (message.type === "change") {
        await session.customRequest("nxwright/changeGenerator",
                                    { number: message.number, settings: message.settings });
        post({ type: "changed", key: message.key });
      } else if (message.type === "stop") {
        await session.customRequest("nxwright/stopGenerator", { number: message.number });
        post({ type: "stopped", key: message.key });
      } else if (message.type === "save" && typeof message.text === "string") {
        await this.save(session, message.text);
      } else if (message.type === "open") {
        const file = await this.chosenFile(session, "Open signal generators",
                                           { "Signal generators": ["json"] });
        if (file) {
          post({ type: "opened", ...file });
        }
      } else if (message.type === "csv") {
        const file = await this.chosenFile(session, "Open a custom wave's values",
                                           { "CSV and text files": ["csv", "txt"] });
        if (file) {
          post({ type: "csvValues", key: message.key, scope: message.scope, ...file });
        }
      }
    } catch (error) {
      post({ type: "refused", key: message.key,
             message: error instanceof Error ? error.message : String(error) });
      await this.tellRunning(session, post);
    }
  }

  // Tells the page which generators run, after the simulation refused
  // something: an agent may have stopped one meanwhile, and the page would
  // go on offering to stop it.
  private async tellRunning(session: vscode.DebugSession,
                            post: (reply: object) => void): Promise<void> {
    try {
      const running = await session.customRequest("nxwright/generators");
      post({ type: "running", generators: running.generators });
    } catch {
      // A simulation that has ended answers nothing: its panel closes.
    }
  }

  // Returns the app's waveforms and the generators running. A simulation
  // whose pages are still compiling answers neither request, so this asks
  // again until the app has started.
  private async state(session: vscode.DebugSession,
                      panel: vscode.WebviewPanel): Promise<object> {
    for (let asked = 1; ; asked += 1) {
      try {
        const [waveforms, running] = await Promise.all([
          session.customRequest("nxwright/waveforms"),
          session.customRequest("nxwright/generators"),
        ]);
        return { waveforms: waveforms.waveforms, generators: running.generators };
      } catch (error) {
        if (asked === MOST_ASKS || this.panel !== panel) {
          throw error;
        }
        await new Promise((resolve) => setTimeout(resolve, ASK_AGAIN));
      }
    }
  }

  // Asks where to save the generators, and writes `text`, their settings
  // file, there.
  private async save(session: vscode.DebugSession, text: string): Promise<void> {
    const chosen = await vscode.window.showSaveDialog({
      title: "Save the signal generators",
      defaultUri: vscode.Uri.joinPath(this.startFolder(session), "signals.json"),
      filters: { "Signal generators": ["json"] },
    });
    if (!chosen) {
      return;
    }
    this.lastFolder = vscode.Uri.joinPath(chosen, "..");
    await vscode.workspace.fs.writeFile(chosen, Buffer.from(text, "utf8"));
  }

  // Asks for a file, and returns its text and its name, or undefined when
  // none was chosen.
  private async chosenFile(session: vscode.DebugSession, title: string,
                           filters: Record<string, string[]>,
  ): Promise<{ text: string; name: string } | undefined> {
    const chosen = (await vscode.window.showOpenDialog({
      title, filters: { ...filters, "All files": ["*"] }, canSelectMany: false,
      defaultUri: this.startFolder(session),
    }))?.[0];
    if (!chosen) {
      return undefined;
    }
    this.lastFolder = vscode.Uri.joinPath(chosen, "..");
    const text = Buffer.from(await vscode.workspace.fs.readFile(chosen)).toString("utf8");
    return { text, name: path.basename(chosen.fsPath) };
  }

  // Where a dialog starts: the folder of the last file, or else the folder
  // that holds the simulation's source folder, since the settings are not
  // part of the app.
  private startFolder(session: vscode.DebugSession): vscode.Uri {
    return this.lastFolder ??
      vscode.Uri.joinPath(vscode.Uri.file(session.configuration.sourceFolder), "..");
  }
}

const BODY = `
<div class="toolbar">
  <button id="add-waveform" disabled>Add waveform generator</button>
  <span id="add-hint" class="hint"></span>
  <span class="gap"></span>
  <button id="start-all" class="secondary" disabled>Start all</button>
  <button id="stop-all" class="secondary" disabled>Stop all</button>
  <button id="open" class="secondary" disabled>Open…</button>
  <button id="save" class="secondary" disabled>Save…</button>
</div>
<p id="notice" class="problem"></p>
<div id="generators"></div>`;

// The styles of the panel. At the top are the buttons that add a
// generator, start or stop them all, and open or save their file. Below
// them, each generator has a block: its Start or Stop button, its waveforms,
// its channels, and a table of its waves' settings. The table has one row
// for the wave every channel sends, or one row for each channel.
const STYLES = `
  body { padding: 8px 16px 16px; font-size: 12px; }
  .toolbar, .head, .waveforms, .channels {
    display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: center;
  }
  .toolbar { gap: 6px; margin-bottom: 8px; }
  .gap { margin-right: auto; }
  .generator {
    border-top: 1px solid var(--vscode-widget-border, var(--vscode-descriptionForeground));
    padding: 8px 0;
  }
  .head { gap: 6px 8px; }
  .title { font-weight: bold; margin-right: 4px; }
  button {
    color: var(--vscode-button-foreground); background: var(--vscode-button-background);
    border: none; padding: 4px 10px; cursor: pointer;
  }
  button:hover { background: var(--vscode-button-hoverBackground); }
  button:disabled { opacity: 0.5; cursor: default; }
  button.secondary {
    color: var(--vscode-button-secondaryForeground);
    background: var(--vscode-button-secondaryBackground);
  }
  button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
  .run { min-width: 5em; }
  .state { color: var(--vscode-descriptionForeground); margin-right: auto; }
  .state.running { color: var(--vscode-testing-iconPassed, var(--vscode-foreground)); }
  .waveforms { margin: 8px 0; }
  .waveforms .label, .channels .label { color: var(--vscode-descriptionForeground); }
  .same { display: block; margin-bottom: 8px; }
  .channels { margin-bottom: 6px; }
  label { white-space: nowrap; }
  .missing { color: var(--vscode-errorForeground); }
  table { border-collapse: collapse; margin-bottom: 6px; }
  th {
    font-weight: normal; text-align: left; padding: 0 4px 2px 0;
    color: var(--vscode-descriptionForeground);
  }
  td { padding: 2px 4px 2px 0; white-space: nowrap; }
  tr.off td:not(.name) { opacity: 0.45; }
  td.name { padding-right: 10px; }
  input, select {
    color: var(--vscode-input-foreground); background: var(--vscode-input-background);
    border: 1px solid var(--vscode-input-border, transparent); padding: 2px 4px;
    font: inherit;
  }
  input[type="number"] { width: 5em; }
  input[type="text"] { width: 28em; max-width: 60vw; }
  input:invalid { border-color: var(--vscode-inputValidation-errorBorder, red); }
  input::placeholder { color: var(--vscode-input-placeholderForeground); }
  tr.values td { padding-bottom: 6px; }
  tr.values button { margin-left: 6px; }
  .sketch { display: block; color: var(--vscode-charts-blue, var(--vscode-foreground)); }
  .hint { color: var(--vscode-descriptionForeground); }
  .problem { color: var(--vscode-errorForeground); white-space: pre-wrap; margin: 4px 0; }
  .problem:empty { display: none; }`;
