# nxwright

A toolchain for Nextion Editor projects (`.HMI` files): it turns a project into a source folder of text files and back, and compiles nxlang into strict Nextion syntax. `README.md` introduces it, `docs/` describes it, and [CONTRIBUTING.md](CONTRIBUTING.md#where-things-are) gives the repository's layout.

## Building and testing

- Python 3.11 or later. Use well-known, maintained libraries for standard formats and protocols, never a hand-written implementation. Ask the user before adding a dependency.
- Never put the vendor's files in the repository: the screen's firmware, the files of the Nextion Editor's installation, or TFT files, which contain the firmware (`INDEPENDENCE.md`, For contributors).
- Run the command from this folder: `python run.py <subcommand>`.
- After every change: `python -m pytest`. After changing the package or the demo, also `python run.py test examples/thermostat/tests`.
- After changing the extension's client: `npm run compile` in `editors/vscode`. `npm install` comes first, once, with the user's go.
- The tests compare written project files byte for byte. A change to what nxwright writes is a change of behavior: say so in the commit message, and never adjust a test to hide it.
- For versions and the changelog, follow CONTRIBUTING.md, Versions, and do what it says the maintainers do. Every commit that changes how the toolchain or the extension behaves raises a version, including a commit that adopts a pull request. Never raise a part to 1.0 on your own.
- If a commit already on main took the same version as yours, `git sync` stops on a conflict in `CHANGELOG.md`. Give your change the next version: put your section above the other one, and raise the version again in `pyproject.toml`, or in `package.json` and `package-lock.json`. Git shows no conflict in those files, because both commits made the same edit there.

## Writing

- Comments, docstrings, docs, and every word users read follow `docs/STYLE.md`. Messages, questions, and VS Code's pages and side bars follow its People using nxwright section.
- Check each claim against the code or a test before writing it.
- Write full sentences and real examples, not labels or shorthand only their author can read.

**When adding to a doc, keep its voice. This is not optional.** Match its sentence length, tone, and level of detail. Do not overrate what you add because you worked on it: give it the detail its neighbours get, and put it where it belongs. Prefer a sentence in the existing text to a new section, callout, or list. Do not repeat it elsewhere unless a reader there needs it.
