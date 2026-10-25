# Driving the Nextion Editor

An optional tool for contributors who have the Nextion Editor: a script that drives the Nextion Editor, to see what it does without doing it by hand. It opens projects, compiles them and writes their TFT files, takes screenshots of the Nextion Editor's windows, and reports what the Nextion Editor shows. nxwright itself neither needs nor runs it, and its tests do not touch it.

It needs Windows, and the Nextion Editor 3.1.73.

## Its rules

- **A dedicated Editor.** The tool starts a Nextion Editor of its own, the dedicated Editor, and reuses it at each later run. It never touches a Nextion Editor you have open.
- **No keyboard or mouse input.** The tool drives the dedicated Editor through UI Automation, Windows' interface for driving another program's controls, and through messages to its windows. Your mouse and keyboard are not used.
- **The Nextion Editor comes in front of your window** during `open` and `simulate`, so your typing would go to it. Click back where you were before typing. Bringing it in front yourself, to watch, changes nothing for the tool.
- **Copies only.** The tool opens a copy of each project, and never saves.
- **It stops rather than guess.** A command stops, and reports what it found, when it meets a control it cannot drive, the Nextion Editor's unhandled exception dialog, or a window shown over the simulator.
- **It stops after five minutes without progress,** as when a call into the Nextion Editor never returns. It prints "Timeout" and where each of its threads was, and frees the lock.
- **It deletes no folder.** A project's copy replaces the earlier copy of the same name. The Nextion Editor keeps the project it shows locked, so a copy of that project goes beside it, as `demo (2).HMI`.
- **Make a data record's folder first.** A data record whose `path` gives a folder its SD card lacks, such as `sd0/probe/d.data` while `sdcard0` has no `probe` folder, makes the Nextion Editor hang as it opens the project: it draws no page, and does not close when asked. Make the folder on the card before opening such a project.
- **Give a data record its file.** A data record whose file is missing, with `mode` 0, which makes no file, stops the simulator answering as its page opens. The simulator's window stays, and the Nextion Editor does not close until its process is ended. Give such a record a file, or `mode` 1.

### Several Nextion Editors

The environment variable `NXWRIGHT_EDITOR_NAME` sets which dedicated Editor to drive, so that each agent, or each person, drives a Nextion Editor of its own, and none waits for another's:

```
NXWRIGHT_EDITOR_NAME=agent-c python tools/editor/editor.py open demo.HMI
```

- A name is letters, digits, `-`, and `_`, at most 32. Any other is refused before anything is touched.
- Scripts that run the tool's commands, such as `catalog_variants.py`, pass it on to them.
- With no name, the tool drives the shared Editor: one per Windows user, whichever checkout's script drives it.
- `status`, and every command that stops, report which Nextion Editor it drove, as "agent-c's Editor" or "the shared Editor".

Each dedicated Editor's records live in `%LOCALAPPDATA%\nxwright\editor-<name>\`, or `%LOCALAPPDATA%\nxwright\editor\` for the shared one:

- `editor.json` records its process;
- `lock` lets one command at a time drive it, and `holder.json` records which command has the lock;
- `hold.json` records a hold across commands;
- `work\` contains the copies of the projects it opened;
- `shown.json` records the copy opened last, with its screen's size;
- `placement.json` records where its window was, so that a fresh Nextion Editor opens there, rather than filling the screen.

Every Nextion Editor of one Windows user still shares the Nextion Editor's own files, in `%APPDATA%\Nextion Editor\`:

- its settings, which each rewrites;
- the folders its simulator takes as SD cards, `sdcard0` and `sdcard1`;
- its simulator's EEPROM, `eeprom\eeprom.bin`;
- the values its simulator keeps from one start to the next, such as `dims`.

So name the files a probe writes on a card after whoever writes them, and tell the others before a probe of the EEPROM or of a kept value.

Each Nextion Editor compiles into a folder of its own, and takes up to 1.1 GB of memory before `open` restarts it. No command closes a Nextion Editor otherwise, so close its window once you are done with it.

## Setting it up

Its packages, pinned in `requirements.txt`, go in a virtual environment of their own, apart from nxwright's:

```
python tools/editor/bootstrap.py
```

This makes `tools/editor/build/venv`, from the Python that runs it. It refuses when that folder exists.

From then on, run the tool with that environment's Python, called the tool's Python below: activate the environment, or call `tools/editor/build/venv/Scripts/python`. The commands below write it `python`.

`requirements.txt` also pins the packages of the nxwright modules the tool imports. So when it changes, update the environment with the tool's Python:

```
python -m pip install -r tools/editor/requirements.txt
```

The Nextion Editor is found where its installer recorded it, or at the path the environment variable `NXWRIGHT_EDITOR` gives.

## Its commands

Run them with the tool's Python, from nxwright's folder:

```
python tools/editor/editor.py open examples/thermostat/thermostat.HMI
python tools/editor/editor.py screenshot editor.png
python tools/editor/editor.py attributes home title
python tools/editor/editor.py simulate schedule.png --send "page schedule"
python tools/editor/editor.py simulate after.png --touch "press 200,150; release"
python tools/editor/editor.py catalog tools/editor/build/catalog.json
python tools/editor/editor.py compile
python tools/editor/editor.py tft tools/editor/build/tft
python tools/editor/editor.py status
python tools/editor/editor.py close-simulator
python tools/editor/editor.py close-file-dialog
python tools/editor/editor.py hold agent-b --minutes 15
python tools/editor/editor.py open demo.HMI --as agent-b
python tools/editor/editor.py release agent-b
```

A command waits for the lock while another command holds it, then gives up, reporting which process holds it.

### `open <project.HMI>`

Copies the project into the work folder, and opens the copy through the Nextion Editor's Open button.

- It records the copy, and its screen's size, which `simulate --touch` needs.
- When the project shown has changes not saved, the Nextion Editor first asks whether to save them. The tool answers No when that project is one of its own copies in the work folder, as it never saves. Otherwise it stops before pressing Open, so that no one else's changes are dropped. Any other question stops it, unanswered.
- When the dedicated Editor uses more than 1.1 GB, `open` restarts it first, since the Nextion Editor runs out of memory near 1.4 GB. It does not restart one with a window over its main window, or with changes not saved.

### `screenshot <file.png>`

Saves a picture of the Nextion Editor's main window, drawn by the window itself, so a window over it does not show.

### `attributes <page> <component>`

Prints, as JSON, a component of the project shown, as the Attribute panel lists it: `{"page", "component", "type", "attributes": [{"name", "value", "hint"}]}`.

- Its type is as the component list gives it, such as `"Text"`.
- Each attribute comes with its value, the hint the Nextion Editor shows for it, and `code_can_change`: whether its name shows green, which code can change, or black, which it cannot.
- A page's own attributes come with the page's name as the component.
- It takes about a second per attribute.

### `simulate <file.png> [--send <instruction> [--hex]]`

Starts the Nextion Editor's simulator on the project shown, by the toolbar's Debug button, saves a picture of the simulator's window, and closes it.

- With `--send`, it first types the instruction in the simulator's instruction box, line by line, and runs it.
- It then waits until the simulator has run the instruction: it adds a last line, `get 1`, and waits for the first answer. If a line of the instruction answers too, as `get` and `print` do, the wait may end there, before the lines after it have run.
- An instruction that resets the simulator, such as `rest`, may lose that answer. The command then stops after waiting.
- With `--hex` too, each line is hexadecimal bytes, such as `68 65 6C 6C 6F`, sent as they are, without the FF FF FF a line of text gets. Use it for bytes that are not an instruction, such as a transfer's data. If those bytes leave an instruction unfinished or a transfer short, the last `get 1` becomes part of them, and the command stops after waiting.
- A simulator already open stops the command. One still showing when the command stops is closed.
- A window shown over the simulator, such as "File Header Data Error" for a data record's file, stops the command at once, which prints the window's text. The simulator does not close until that window is answered, so both are left open: answer it, then run `close-simulator`.

### `simulate <file.png> --touch <steps>`

Touches the simulator's screen after the instruction, if any, and before the picture. The steps are separated by semicolons:

- `press X,Y` presses the screen at its pixel (X, Y), as a page file gives a component's `x` and `y`;
- `release` releases the press where it was made;
- `wait MS` waits that many milliseconds;
- `picture FILE` saves a picture of the simulator's window there, as the last one is saved.

So `"press 200,150; picture held.png; release; wait 500"` takes a picture of a component held down, then lets go.

- The steps are checked before the simulator starts, against the screen's size `open` recorded. A point off the screen, a press while one is held, or a release while none is, stops the command, and the message gives the step. So does a project shown that `open` did not open.
- Each press and release is followed by a pause of 50 ms. Each picture waits until the simulator has run what the touches before it started, as `--send` waits.
- No step moves a held press: the Nextion Editor's simulator takes no drag from window messages. Do a drag in the simulator by hand.
- Typing in the instruction box slows the simulator's timers. To time an interval with `wait`, keep `--send` lines and `picture` steps out of it, since a picture waits by typing `get 1`.

### `catalog <file.json> [--variant <name>] [--known <file.json>]`

Reads every component of every page of the project shown, the pages included, as `attributes` does, and writes them as JSON: `{"variant", "project", "objects": [{"page", "component", "type", "attributes"}]}`, `type` being the number the project stores.

- `--variant` gives the catalog's name once merged with others.
- With `--known` and an earlier catalog, the rows whose hint that catalog already has for the same type are not clicked, and get no hint.
- Keep the files under `tools/editor/build/`, which git ignores: they contain the Nextion Editor's hints, which are not nxwright's to publish.
- A project of 32 objects takes about 12 minutes, and nearly as long with `--known`, which saves only the clicks for hints.

### `compile`

Compiles the project shown, by the toolbar's Compile button. It prints a line giving the project, then the Nextion Editor's Output panel once the compile has ended: the screen's memory, the global memory, each page's memory, and what the compile refused.

- The panel is emptied first, so that it shows only this compile's text.
- A compile that fails still ends the command well: its Output says why.

### `tft <folder>`

Compiles the project shown, and writes its TFT file in the folder, named after the project, over any file of that name. It prints the file's path, then the Nextion Editor's Output panel.

- If the compile fails, the command stops without writing the file.
- The command closes the Explorer window the Nextion Editor opens on the folder.
- Your own Nextion Editor shares the dedicated Editor's settings, so it will offer this folder next time.

### `status`

Reports whether the dedicated Editor runs, which project it shows, and who holds it.

### `hold <name> [--minutes N]` and `release <name>`

Holds the dedicated Editor for one holder across its commands, as a probe of `open` then `simulate` needs: each command takes the lock alone, so another's command could land between them.

- Each other command gives its holder with `--as <name>`.
- While the hold stands, its holder's commands run, and renew it for its minutes: 10 by default, 60 at most.
- Anyone else's commands are refused, with who holds it and until when, and exit with 3, so that a script can wait and try again. `status` still runs.
- `release <name>` ends the hold, and so does its time.
- Anyone may release a hold by its holder's name, for example to end a forgotten one. The hold keeps two probes from crossing, not anyone from misusing it.

### `close-simulator`

Closes the simulator the dedicated Editor shows: one a `simulate` left when it was itself stopped, as by closing its terminal, or one that showed only after `simulate` stopped. When the simulator does not close, it lists the windows shown over it. It starts no Nextion Editor.

### `close-file-dialog`

Cancels a file dialog the dedicated Editor shows: one an `open` left when it was itself stopped, as by closing its terminal. While a file dialog is open, the other commands stop on it. An `open` that fails once its dialog shows cancels the dialog itself. It starts no Nextion Editor.

## Every attribute of every type

`tools/editor/catalog_variants.py`, run with the tool's Python from nxwright's folder, catalogs every attribute the Nextion Editor shows, of every component type. It runs for about two hours: twelve projects of about eleven minutes each.

1. It builds the every-component project from `tests/fixtures/every-component`, as nxwright's tests do, opens it, and catalogs it.
2. The Attribute panel shows only the attributes that apply under the current choices, so it then builds variants. Variant k sets every choice attribute of every component to its choice k, where its hint lists one. Each is catalogued with `--known`.
   - Only the choices the project as built shows are varied. A choice attribute that a variant reveals, such as `pic` once `sta` is "image", keeps its value in the others.
3. It merges the catalogs (`catalog.py`), compares them with nxwright's component defaults, and writes `report.md`:
   - the attributes nxwright lists that the Nextion Editor never showed;
   - those it showed that nxwright does not list;
   - those whose name showed in both colours;
   - the defaults that differ;
   - every attribute, with its hint.
4. Last, it checks that none of nxwright's own descriptions of attributes (`nxwright/project/attribute_descriptions.toml`) equals one of the Nextion Editor's hints, and lists those that do: a tripwire for a hint pasted by mistake.

- Everything goes in `tools/editor/build/catalog/`, or the folder given.
- It stops if another command opened another project in the dedicated Editor between two of its steps.
- A project or catalog left in the folder by a run that stopped is used again. Remove it to make it again.

## The memory each page takes

`tools/editor/memory_probe.py`, run with the tool's Python from nxwright's folder, measures what the Nextion Editor's compile counts in memory on each series of screens. It writes the table nxwright's build checks pages against, `nxwright/project/memory_costs.toml` (`docs/format.md`, The Nextion Editor's memory).

It builds probe projects with nxwright, compiles each in the dedicated Editor, and fits a rule to each attribute's costs. Its docstring lists what it measures. It writes only the series that agree in full with every page and project it compiled, and reports what it could not measure.

- `--series T,P` measures those series only. The others keep what the table contains.
- Each project and its compile are kept in `tools/editor/build/memory/`, or the folder given, so that a run that stopped goes on where it was. Remove a project's folder to compile it again.
- It holds the dedicated Editor for its run, as `memory-probe-<its process ID>`, and stops at once when another holds it.
- A run ended from outside, its process killed, cannot give its hold back. `editor.py release memory-probe-<its process ID>` does, as `status` reports it.
- It opens many projects, so it may restart the Nextion Editor past 1.1 GB.

## Its tests

The tests of its records, its lock, its catalog's logic, its memory probe's, and how it finds a window of the Nextion Editor need neither the Nextion Editor nor pywinauto. They run with nxwright's own Python, on Windows. The tests of its open and tft commands import the tool itself, against stand-ins for the Nextion Editor's windows, so they need the tool's packages too, from `requirements.txt`:

```
python -m unittest discover -s tools/editor/tests -t .
```

The memory probe's tests run it against a stand-in for the Nextion Editor, which counts as a known table does: the probe must find that table again.
