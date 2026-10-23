# nxwright

A toolchain for Nextion Editor projects (`.HMI` files): it turns a project into a source folder of text files and back, and compiles nxlang into strict Nextion syntax. `README.md` introduces it, `docs/` describes it, and [CONTRIBUTING.md](CONTRIBUTING.md#where-things-are) gives the repository's layout.

## Building and testing

- Python 3.11 or later. Use well-known, maintained libraries for standard formats and protocols, never a hand-written implementation. Ask the user before adding a dependency.
- Run the command from this folder: `python run.py <subcommand>`.
- After every change: `python -m unittest discover -s tests -t .`. After changing the package or the demo, also `python run.py test examples/thermostat/tests`.
- After changing the extension's client: `npm run compile` in `editors/vscode`. `npm install` comes first, once, with the user's go.
- The tests compare written project files byte for byte. A change to what nxwright writes is a change of behavior: say so in the commit message, and never adjust a test to hide it.
- Versions follow CONTRIBUTING.md, Versions. Only the user publishes, so raise a version only when the user says a publish is coming, or asks for it. Then, for each part whose code changed since its last version, raise the version and add its `CHANGELOG.md` entry, in a commit of its own. Ask the user which number to raise unless the change is plainly a fix. Whenever the extension starts relying on something only a newer toolchain has, raise `OLDEST_TOOLCHAIN` in the same change, as that section says.

## Writing

- Comments, docstrings, docs, and every word users read follow `docs/STYLE.md`. Messages, questions, and VS Code's pages and side bars follow its People using nxwright section.
- Check each claim against the code or a test before writing it.
- Write full sentences and real examples, not labels or shorthand only their author can read.

**When adding to a doc, keep its voice. This is not optional.** Match its sentence length, tone, and level of detail. Do not overrate what you add because you worked on it: give it the detail its neighbours get, and put it where it belongs. Prefer a sentence in the existing text to a new section, callout, or list. Do not repeat it elsewhere unless a reader there needs it.
