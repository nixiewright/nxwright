# Contributing

Bug reports, fixes, and documentation are welcome. For a larger change, open an issue first, so we can agree on the approach before you write it.

## Working on nxwright

- Python 3.11 or later. Use well-known, maintained libraries for standard formats and protocols (images, fonts, QR codes, TOML, the Language Server Protocol), never a hand-written implementation of one. A new dependency is added only once the maintainers agree.
- Run the tests from the repository's root, and add tests for what you change. Install nxwright from your copy once, then run the tests. With `-e`, the `nxwright` command runs your copy's code:

  ```
  python -m pip install -e .
  python -m unittest discover -s tests -t .
  python run.py test examples/thermostat/tests
  ```

- `pyproject.toml` lists nxwright's packages by name, so that `docs/` ships with them, for `nxwright mcp`'s `about` tool. A new package goes in that list too, which `tests/test_mcp_server.py` checks.
- The VS Code extension's client, in `editors/vscode`, is TypeScript (see Running the VS Code extension from source, below). It has no knowledge of the language, which stays in the language server (`nxwright/language_server/`), tested with the rest.
- The tests compare written project files byte for byte. A change to what nxwright writes is a change of behaviour: say so in the pull request.
- `README.md`'s nxlang examples come from `nxwright/language/nxlang_samples.py`, which also feeds the Switch to nxlang panel. After changing the samples, run `python -m tools.readme` to rewrite the README. `tests/test_readme.py` fails until you do.
- nxwright contains none of the vendor's files or texts. Before you attempt to work out how the Nextion Editor behaves, read the rules in [INDEPENDENCE.md](INDEPENDENCE.md#for-contributors).
- `tools/editor/` contains an optional tool that drives the Nextion Editor, for contributors who have it: see its [README](tools/editor/README.md). Its tests need neither the Nextion Editor nor the tool's packages, and run on Windows with `python -m unittest discover -s tools/editor/tests -t .`.
- Comments and documentation follow [docs/STYLE.md](docs/STYLE.md).

## Where things are

- `nxwright/`: the package.
  - `project/` reads and writes project files and their dumps.
  - `source/` handles source folders.
  - `drawing/` draws a page and its components, for the page preview and the simulator.
  - `language/` contains the compiler.
  - `testing/` runs a screen's code on a PC, for tests, and a whole app, for the simulator.
  - `language_server/` answers a code editor's questions (`nxwright lsp`).
  - `debug_adapter/` debugs the code a test or a simulation runs (`nxwright debug-adapter`).
  - `mcp_server/` lets agents start and drive the simulator (`nxwright mcp`).
  - `cli.py` is the command.
- `docs/`: the documentation. `docs/STYLE.md` says how it is written.
- `tests/`: the tests, with their fixtures in `tests/fixtures/`.
- `editors/vscode/`: the VS Code extension.
  - `src/`: the TypeScript client. `extension.ts` starts it.
  - `media/`: the scripts and images of its webviews: the page preview, the side bars' sections, and the simulator.
  - `syntaxes/`: the TextMate grammar of `.nx` files.
  - `test/`: the tests Node runs. `test/host/` has those that need VS Code itself.
- `examples/thermostat/`: a demo built with nxwright, with its own tests.
- `tools/readme.py` and `tools/editor/`: the README's examples and the Nextion Editor tool, described above.

## Running the VS Code extension from source

Build the extension in `editors/vscode`, with [Node.js](https://nodejs.org) and npm:

```
npm install
npm run compile
```

`npm test` compiles the client, then runs its tests (`test/`) with Node's own test runner. It needs the Node.js versions jsdom supports: 22.22.2 or later in version 22, 24.15.0 or later in version 24, or 26 and later.

`npm run test:host` compiles the client, then runs the tests that need VS Code itself (`test/host/`): the extension activating on a source folder, its commands registered, the language server's errors as code is typed, the page preview opening, and an agent driving a simulation through the agent channel, `nxwright mcp`'s own client included.

- The tests run in a VS Code installed apart from your own, which `@vscode/test-electron` starts, and never downloads.
- To set one up:
  1. Download [VS Code's zip](https://code.visualstudio.com/download), and unpack it in a folder of its own, such as `C:\Tools\vscode`.
  2. In that folder, beside `Code.exe`, create an empty folder named `data`. That VS Code then keeps its settings there, apart from your own VS Code's.
  3. Set the environment variable `NXWRIGHT_TEST_VSCODE` to its program, such as `C:\Tools\vscode\Code.exe`.
- Each run keeps its settings and caches in `editors/vscode/.vscode-test/`, which git ignores, and opens `tests/fixtures/files/app` without changing it.
- The tests run nxwright with `python`, or with the Python that `NXWRIGHT_TEST_PYTHON` points at.
- A test VS Code window shows while the tests run. On Linux, as in CI, the tests need a display, such as `xvfb-run npm run test:host`.

To use it, run **Developer: Install Extension from Location...** from VS Code's command palette, and pick that folder. VS Code keeps a link to the folder, and runs the client compiled there, in `out/`, which git does not track. So after pulling changes or switching branches, run `npm run compile` again, then **Developer: Reload Window**. Until then, VS Code reads the new `package.json` but runs the old client. A command new in `package.json` then shows in the command palette, and fails with "command not found".

The link is to one folder, for every VS Code window. With several checkouts of the repository, such as git worktrees, every window runs the extension of the checkout installed, whichever checkout it has open.

The extension runs nxwright itself for its language server and its commands. Which nxwright is a setting of its own, `nxwright.command`, which can run a checkout's `run.py` ([the extension's README](editors/vscode/README.md#settings), Settings).

To remove the extension, uninstall "nxwright" from the Extensions view.

## Sign-off

Each commit in a pull request must carry a sign-off: a line certifying that you wrote the change, or have the right to submit it under this project's license, as the [Developer Certificate of Origin](https://developercertificate.org) states:

```
Signed-off-by: Your Name <you@example.com>
```

`git commit -s` adds it. To sign off commits already made on your branch: `git rebase --signoff main`. A check on each pull request reports any commit without one.

## Versions

The toolchain and the VS Code extension each have a version of their own: the toolchain's in `pyproject.toml`, the extension's in `editors/vscode/package.json`. They need not match.

- A release of a part is a publish that changes its code. It raises that part's version once, however many changes it carries. A publish of only docs or tests raises neither.
- Below 1.0, the middle number goes up for a new feature, or for anything that stops working as it did, such as a command that behaves differently, or a source folder that needs `nxwright upgrade`: 0.1.0 becomes 0.2.0. The last number goes up for fixes alone: 0.1.0 becomes 0.1.1. 1.0 comes when the maintainers decide a part is stable. From then on, the first number goes up only for a change that stops something working as it did.
- The change that raises a version also adds its entry to [CHANGELOG.md](CHANGELOG.md).
- The extension warns when the toolchain it runs is older than `OLDEST_TOOLCHAIN`, in `editors/vscode/src/toolchainVersion.ts`. When the extension starts relying on something only a newer toolchain has, such as a new request to the language server, raise `OLDEST_TOOLCHAIN` to the toolchain version that carries it, in the same change. If that version does not exist yet, raise the toolchain's version to it too, with its changelog entry.
- The source folder's `format`, in `app.toml`, is a third number: the version of the folder's layout. It goes up only when the layout changes, in the same change as the `nxwright upgrade` step that brings older folders forward.

## AI assistance

You may use AI tools. The sign-off is yours either way: by signing off, you state that you have reviewed the change, understand it, and have the right to submit it.

## How changes are merged

Maintainers review each pull request. An accepted change is merged into the maintainers' own tree, then published back here, so it can take a moment to appear on `main`.

## License

nxwright is under the [Apache License 2.0](LICENSE). Your contributions are too.

A file nxwright ships from another project keeps that project's license, in a file beside it, and `pyproject.toml` lists that license too. So far there is one: the Noto Sans font, under the SIL Open Font License 1.1 ([nxwright/project/fonts/OFL.txt](nxwright/project/fonts/OFL.txt)).
