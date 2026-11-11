# Contributing

Bug reports, fixes, and documentation are welcome. For a larger change, open an issue first, so we can agree on the approach before you write it.

## Working on nxwright

- You need Python 3.11 or later.
- Add tests for what you change, written as `unittest` test classes like the existing ones. pytest is set up to run only those, so it would skip a test written as a plain function.
- Run nxwright's tests, and the thermostat demo's, from the repository's root:

  ```
  python -m pip install -e . --group test
  python -m pytest
  python run.py test examples/thermostat/tests
  ```

  You only need to run the `pip install` command once. Its `-e` option makes the `nxwright` command run the code in your checkout. `--group test` installs pytest, and needs pip 25.1 or later.

- pytest runs the tests on all of your computer's processors. To use only four of them, run `python -m pytest -n 4`.
- The tests compare the project files nxwright writes byte for byte. If your change alters those files, that is a change of behaviour, so say so in the pull request.
- For standard formats and protocols (images, fonts, QR codes, TOML, the Language Server Protocol), use a well-known, maintained library, and never write your own implementation. Get the maintainers' agreement before adding a new dependency.
- If you add a folder of Python modules under `nxwright/`, also add it to the `packages` list in `pyproject.toml`. `tests/test_mcp_server.py` checks that list.
- Comments and documentation follow [docs/STYLE.md](docs/STYLE.md).
- Put support for the `.nx` language in the language server (`nxwright/language_server/`), where the Python tests cover it, rather than in the VS Code extension's TypeScript client in `editors/vscode`. The client has [its own build](#running-the-vs-code-extension-from-source) and [its own tests](#testing-the-vs-code-extension).
- To change the nxlang examples in `README.md`, edit `nxwright/language/nxlang_samples.py`, then run `python -m tools.readme` to rewrite the README. `tests/test_readme.py` fails until you do. The same file also supplies the examples in the Switch to nxlang panel.
- nxwright contains none of the files or text from Nextion's vendor. To keep it that way, read the rules in [INDEPENDENCE.md](INDEPENDENCE.md#for-contributors) before you try to work out how the Nextion Editor behaves.
- `tools/editor/` contains an optional tool that drives the Nextion Editor, for contributors who have it. See its [README](tools/editor/README.md) for how to use it and run its tests. When Nextion publishes a new release of the Nextion Editor, see [tools/editor/RELEASES.md](tools/editor/RELEASES.md) for the steps to move nxwright to it.

## Where things are

- `nxwright/`: the package.
  - `project/` reads and writes project files and their dumps.
  - `source/` handles source folders.
  - `drawing/` draws a page and its components, for the page preview and the simulator.
  - `language/` contains the nxlang compiler.
  - `testing/` runs code on a PC: a screen's code for tests, and a whole app for the simulator.
  - `language_server/` answers a code editor's questions (`nxwright lsp`).
  - `debug_adapter/` debugs the code a test or a simulation runs (`nxwright debug-adapter`).
  - `mcp_server/` lets agents start and drive the simulator (`nxwright mcp`).
  - `tft/` compiles a project into a TFT file, turns a TFT file back into a source folder, and uploads a TFT file to a screen.
  - `cli.py` is the `nxwright` command.
- `docs/`: the documentation.
- `tests/`: the tests, with their fixtures in `tests/fixtures/`. The tests of TFT files, and their fixtures, are in `tests/tft/`.
- `editors/vscode/`: the VS Code extension.
  - `src/`: the TypeScript client. `extension.ts` starts it.
  - `media/`: the scripts and images for the extension's webviews (the page preview, the side bars' sections, and the simulator).
  - `syntaxes/`: the TextMate grammar of `.nx` files.
  - `test/`: the tests Node runs. `test/host/` has those that need VS Code itself.
- `examples/thermostat/`: a demo built with nxwright, with its own tests.
- `tools/readme.py`: the script that writes the README's examples.
- `tools/nspanel_easy.py`: the script that checks that nxwright still builds the display files of [NSPanel-Easy](https://github.com/edwardtfn/NSPanel-Easy) byte for byte, by comparing them with the ones NSPanel-Easy commits.
- `tools/editor/`: the tool that drives the Nextion Editor.
- `tools/screen/`: the probe that checks nxwright's rules for `ram/` files on a real screen ([tools/screen/README.md](tools/screen/README.md)).
- `tools/tft/`: the scripts that compare nxwright's TFT files with the Nextion Editor's, and write the fixtures in `tests/tft/fixtures/` ([tools/tft/README.md](tools/tft/README.md)).

## Running the VS Code extension from source

Build the extension in `editors/vscode`, with [Node.js](https://nodejs.org) and npm:

```
npm install
npm run compile
```

To use your build, run **Developer: Install Extension from Location...** from VS Code's command palette, and pick the `editors/vscode` folder.

After pulling changes or switching branches, run `npm run compile` again, then **Developer: Reload Window**. VS Code runs the extension straight from your `editors/vscode` folder, and git does not track the compiled client in its `out/` folder. Until you compile again, VS Code reads the new `package.json` but runs the old client, so a new command shows in the command palette and fails with "command not found".

If you have several checkouts of the repository, such as git worktrees, every VS Code window runs the extension from the checkout you installed it from, whichever checkout the window has open.

The extension runs nxwright for its language server and its commands. To choose which nxwright it runs, such as a checkout's `run.py`, change the setting `nxwright.command` (see [Settings](editors/vscode/README.md#settings) in the extension's README).

## Testing the VS Code extension

Run these commands in `editors/vscode`. Both compile the client first.

`npm test` runs the client's tests, in `test/`. It needs a Node.js version that jsdom supports: 22.22.2 or later in version 22, 24.15.0 or later in version 24, or 26 and later.

`npm run test:host` runs the tests that need VS Code itself, in `test/host/`. They run in a separate copy of VS Code, whose window shows while they run, and you have to provide that copy yourself. To set one up on Windows:

1. Download [VS Code's zip](https://code.visualstudio.com/download), and unpack it in a folder of its own, such as `C:\Tools\vscode`.
2. In that folder, beside `Code.exe`, create an empty folder named `data`, so that this copy keeps its settings apart from your own VS Code's.
3. Set the environment variable `NXWRIGHT_TEST_VSCODE` to that copy's `Code.exe`, such as `C:\Tools\vscode\Code.exe`.

On Linux and macOS, see `.github/workflows/tests.yml` for how the CI workflow downloads the copy. On Linux, the tests also need a display, which you can provide with `xvfb-run npm run test:host`.

The tests run nxwright with `python`, or with the Python that `NXWRIGHT_TEST_PYTHON` points at.

## Sign-off

Each commit in a pull request must carry a sign-off line:

```
Signed-off-by: Your Name <you@example.com>
```

With this line, you certify that you wrote the change, or have the right to submit it under this project's license, as the [Developer Certificate of Origin](https://developercertificate.org) states.

`git commit -s` adds the line, and `git rebase --signoff main` adds it to commits already on your branch. A check on each pull request reports any commit without one.

## AI assistance

You may use AI tools. The sign-off is yours either way: by signing off, you state that you have reviewed the change, understand it, and have the right to submit it.

## How changes are merged

Maintainers review each pull request. An accepted change is merged into the maintainers' own tree, then published back here, so it can take a moment to appear on `main`.

## Versions

The toolchain and the VS Code extension each have a version of their own: the toolchain's in `pyproject.toml`, the extension's in `editors/vscode/package.json`. They need not match.

Do not raise a version in your pull request. The maintainers raise versions when they merge it. If your change makes the extension rely on something that only a newer toolchain has, such as a new request to the language server, say so in your pull request. The maintainers then raise `OLDEST_TOOLCHAIN`, in `editors/vscode/src/toolchainVersion.ts`, to the toolchain version that has it. The extension warns when the toolchain it runs is older than that.

- Each change to how the toolchain or the extension behaves raises that part's version, and adds a line for it to [CHANGELOG.md](CHANGELOG.md). A change to docs or tests alone raises neither version.
- Each version adds a section at the top of its part's list in the changelog, headed with the version and the day it was made, such as `### [0.2.1] - 2026-11-08`. Each of its features and fixes takes one line there, written for the people who use nxwright. The changelog is not documentation that explains things in detail: each line is a very short summary. Aim for a max of 50 to 100 chars per line tops, leave the details to the doc, if they are even needed.
- Versions follow [semantic versioning](https://semver.org). A change breaks the public API when people must change their project, its code, their settings, or their scripts to keep them working.
- The first number goes up for a change that breaks the public API, the middle number for a feature, and the last number for a fix. For example, 1.4.2 becomes 2.0.0, 1.5.0, or 1.4.3.
- Before 1.0, a change that breaks the public API raises the middle number instead, and a feature or a fix raises the last number. For example, 0.2.5 becomes 0.3.0 or 0.2.6.
- The maintainers decide when a part reaches 1.0.
- The source folder's `format`, in `app.toml`, is a separate version number for the folder's layout. It goes up only when the layout changes, in the same change as the `nxwright upgrade` step that brings older folders forward.

## License

nxwright is under the [Apache License 2.0](LICENSE). Your contributions are too.

If you add a file from another project, keep that project's license in a file beside it, and list that license in `pyproject.toml` too. So far the only such file is the Noto Sans font, under the SIL Open Font License 1.1 ([nxwright/project/fonts/OFL.txt](nxwright/project/fonts/OFL.txt)).
