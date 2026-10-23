// Which project the side bar's sections show, kept apart from VS Code, which
// test/ tests. The project is a source folder, by its path.

// Returns the current project: `remembered`, the last one worked in or
// picked, while `rememberedExists`, its app.toml being there; else the
// workspace's only source folder among `found`, if it has just one; else
// none, until the user picks one.
export function currentProjectOf(remembered: string | undefined, rememberedExists: boolean,
                                 found: string[]): string | undefined {
  if (remembered !== undefined && rememberedExists) {
    return remembered;
  }
  return found.length === 1 ? found[0] : undefined;
}

// The current project and what the server says of it. A project becomes
// current at once, before the server answers, so that a command run
// meanwhile acts on it; the answer follows, unless another project became
// current meanwhile. `ask(folder)` asks the server; `changed()` is told of
// each change, of the project or of its answer.
export class ProjectTracker<Info> {
  private current: string | undefined;
  private answer: Info | null = null;
  // How many updates were made: only the latest's answer counts.
  private updates = 0;

  constructor(private readonly ask: (folder: string) => Promise<Info | null>,
              private readonly changed: () => void) {}

  get folder(): string | undefined {
    return this.current;
  }

  // What the server said of the project, or null before it answers.
  get info(): Info | null {
    return this.answer;
  }

  // Makes `folder` current, or none, and asks the server about it.
  async update(folder: string | undefined): Promise<void> {
    const update = ++this.updates;
    if (folder !== this.current) {
      this.current = folder;
      this.answer = null;
      this.changed();
    }
    const info = folder === undefined ? null : await this.ask(folder);
    if (update !== this.updates || JSON.stringify(info) === JSON.stringify(this.answer)) {
      return;
    }
    this.answer = info;
    this.changed();
  }
}
