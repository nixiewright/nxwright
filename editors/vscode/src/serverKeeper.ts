// The language server's starts and stops, and the searches for the command
// that runs nxwright (nxwrightCommand.ts), kept in order. Kept apart from
// VS Code, so that its tests run without it: extension.ts gives the steps
// that need VS Code, a search, a start, and a stop.
//
// Starting and stopping are done one at a time. The first search asks for
// the interpreter chosen in VS Code, which may start the Python extension,
// which may then say it chose one. The search and restart that follow then
// wait, rather than starting a second server beside the first.

import { NxwrightSearch } from "./nxwrightCommand";

// What the keeper does through VS Code and the language client.
export interface ServerSteps {
  // Starts a search for the command that runs nxwright, and returns it.
  search(): Promise<NxwrightSearch>;
  // Starts the language server with what a search found, or says it found none.
  start(found: NxwrightSearch): Promise<void>;
  // Stops the language server, if one runs.
  stop(): Promise<void>;
}

export class ServerKeeper {
  // The latest search, under way or done.
  private search: Promise<NxwrightSearch> | undefined;
  // The starts and stops, the latest last.
  private work: Promise<void> = Promise.resolve();
  // Whether the extension stops (close).
  private closed = false;
  // The start under way, if any (startThenStopIfClosed).
  private starting: Promise<void> | undefined;

  constructor(private readonly steps: ServerSteps) {}

  // The extension stops: work still queued, such as a restart whose search
  // has not ended, starts and stops nothing more. Waiting for it instead
  // would hold VS Code's closing until the search ends, up to seconds for
  // each Python it tries. A start already under way is waited for, as the
  // server it starts is then stopped (startThenStopIfClosed). The promise
  // returned ends then, failed or not, for deactivate to wait on.
  close(): Promise<void> {
    this.closed = true;
    return (this.starting ?? Promise.resolve()).catch(() => undefined);
  }

  // Returns the latest search, the first started when there is none yet.
  private latest(): Promise<NxwrightSearch> {
    return this.search ?? this.newSearch();
  }

  // Starts the language server with the latest search's finding, in turn.
  // A start never searches again: it runs in the queue of starts and stops,
  // behind which a new search would wait for ever.
  start(): Promise<void> {
    return this.inTurn(async () => {
      const found = await this.latest();
      if (!this.closed) {
        await this.startThenStopIfClosed(found);
      }
    });
  }

  // Searches again, as when the setting or the interpreter chosen in VS Code
  // changes, and restarts the language server when the command changed, in
  // turn. A server that does not stop cleanly is replaced all the same.
  searchAgain(): Promise<void> {
    return this.inTurn(async () => {
      const before = (await this.search)?.command;
      const { command } = await this.newSearch();
      if (!this.closed && JSON.stringify(command) !== JSON.stringify(before)) {
        await this.steps.stop().catch(() => undefined);
        // The extension may have stopped meanwhile, as a stop takes a while.
        // The finding is read first, so that no wait comes between the
        // check and the start, which close() then sees under way.
        const found = await this.latest();
        if (!this.closed) {
          await this.startThenStopIfClosed(found);
        }
      }
    });
  }

  // Returns the latest search's finding, for a command about to run nxwright.
  // When it found none, searches again first, as nxwright may have been
  // installed since; a command found then starts the language server too.
  async forCommand(): Promise<NxwrightSearch> {
    if ((await this.latest()).command === undefined) {
      await this.searchAgain();
    }
    return this.latest();
  }

  // Starts the language server with `found`. When the extension stopped
  // meanwhile, the server is stopped again: its client counts only once
  // started, so deactivate's own stop found none to stop.
  private async startThenStopIfClosed(found: NxwrightSearch): Promise<void> {
    this.starting = (async () => {
      await this.steps.start(found);
      if (this.closed) {
        await this.steps.stop();
      }
    })();
    try {
      await this.starting;
    } finally {
      this.starting = undefined;
    }
  }

  private newSearch(): Promise<NxwrightSearch> {
    this.search = this.steps.search();
    return this.search;
  }

  // Does `work` once the work before it is done, failed or not.
  private inTurn(work: () => Promise<void>): Promise<void> {
    this.work = this.work.then(work, work);
    return this.work;
  }
}
