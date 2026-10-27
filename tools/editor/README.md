# Driving the Nextion Editor

The Editor tool is an optional script that drives the Nextion Editor for you, so that you can see what the Nextion Editor does without clicking through it by hand. The tool opens projects, compiles them, writes their TFT files, takes screenshots of the Nextion Editor's windows, and reports what the Nextion Editor shows. The tool is for contributors who have the Nextion Editor: nxwright itself never runs the tool, and neither do nxwright's tests.

You need Windows and the Nextion Editor 3.1.73.

## Its rules

- **A dedicated Editor.** The tool starts its own Nextion Editor, called the dedicated Editor, and reuses it on every later run. The tool never touches a Nextion Editor you opened yourself.
- **No keyboard or mouse input.** The tool drives the dedicated Editor through UI Automation, the Windows interface for controlling another program, and by sending messages to its windows. Your mouse and keyboard are not used.
- **The Nextion Editor comes to the front** during `open` and `simulate`, so anything you type would go to the Nextion Editor. Click back into your own window before you type. Bringing the Nextion Editor to the front yourself, to watch, does not disturb the tool.
- **Copies only.** The tool opens a copy of each project, and never saves.
- **The tool stops rather than guess.** A command stops and reports what it found when it meets a control it cannot drive, the Nextion Editor's unhandled exception dialog, or a window over the simulator.
- **A command gives up after five minutes without progress,** for example when a call into the Nextion Editor never returns. The command then prints "Timeout" and where each of its threads was, and releases the lock.
- **The tool never deletes a folder.** A new copy of a project replaces the old copy of the same name. The Nextion Editor locks the project it shows, though, so a copy of that project goes next to the locked one, under a name like `demo (2).HMI`.
- **Make a data record's folder first.** If a data record's `path` points to a folder missing from its SD card, such as `sd0/probe/d.data` when `sdcard0` has no `probe` folder, the Nextion Editor hangs while opening the project: it draws no page, and does not close when asked. Create the folder on the card before you open the project.
- **Give a data record its file.** If a data record's file is missing and its `mode` is 0, which creates no file, the simulator stops responding when the record's page opens. The simulator's window stays up, and the Nextion Editor does not close until you end its process. Give the record a file, or set its `mode` to 1.

### Several Nextion Editors

The environment variable `NXWRIGHT_EDITOR_NAME` picks which dedicated Editor the tool drives. Each agent or person can then have a Nextion Editor of their own, and nobody waits for anyone else:

```
NXWRIGHT_EDITOR_NAME=agent-c python tools/editor/editor.py open demo.HMI
```

- A name is up to 32 letters, digits, `-`, or `_`. The tool refuses any other name before doing anything.
- Scripts that run the tool's commands, such as `catalog_variants.py`, pass the name on.
- Without a name, the tool drives the shared Editor. Each Windows user has one shared Editor, used by the scripts of every checkout.
- `status`, and every command that stops, says which Nextion Editor it used, such as "agent-c's Editor" or "the shared Editor".

Each dedicated Editor keeps its records in `%LOCALAPPDATA%\nxwright\editor-<name>\`, or in `%LOCALAPPDATA%\nxwright\editor\` for the shared one:

- `editor.json` records the Nextion Editor's process;
- `lock` lets only one command at a time drive the Nextion Editor, and `holder.json` records which command has the lock;
- `hold.json` records a hold that lasts across commands;
- `work\` contains the copy of the project being shown, and `open` deletes older copies once a new one opens;
- `shown.json` records the copy opened last, and its screen size;
- `placement.json` records where the window was, so that a restarted Nextion Editor opens in the same place instead of filling the screen.

All the Nextion Editors of one Windows user still share the Nextion Editor's own files, in `%APPDATA%\Nextion Editor\`:

- the settings, which every Nextion Editor rewrites;
- the folders the simulator uses as SD cards, `sdcard0` and `sdcard1`;
- the simulator's EEPROM, `eeprom\eeprom.bin`;
- the values the simulator keeps from one run to the next, such as `dims`.

Name any files your probe writes on a card after yourself, so that they do not clash with anyone else's. Tell the others before you probe the EEPROM or a kept value.

Each Nextion Editor compiles into its own folder. A Nextion Editor can grow to 1.1 GB of memory before `open` restarts it, and that restart is the only time the tool closes one. Close a Nextion Editor's window yourself when you are done with it.

## Setting it up

The tool's packages are pinned in `requirements.txt`, and go in their own virtual environment, separate from nxwright's:

```
python tools/editor/bootstrap.py
```

`bootstrap.py` creates the environment in `tools/editor/build/venv`, using the Python you run it with, and refuses if that folder already exists.

From then on, run the tool with that environment's Python, called the tool's Python below. Either activate the environment, or call `tools/editor/build/venv/Scripts/python`. The commands below just write `python`.

`requirements.txt` also pins the packages needed by the nxwright modules the tool imports. Whenever `requirements.txt` changes, update the environment with the tool's Python:

```
python -m pip install -r tools/editor/requirements.txt
```

The tool looks for the Nextion Editor at the path in the environment variable `NXWRIGHT_EDITOR`, if set, and otherwise where the Nextion Editor's installer recorded it.

## Its commands

Run the commands with the tool's Python, from nxwright's folder:

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

If another command has the lock, a command waits for it, then gives up and prints which process has it.

### `open <project.HMI>`

`open` copies the project into the work folder, then opens the copy with the Nextion Editor's Open button.

- `open` records the copy and its screen size, which `simulate --touch` needs.
- Once the copy is open, `open` deletes the other `.HMI` files in the work folder, which are copies of earlier projects. A copy the Nextion Editor still has open is kept, as is every file that is not an `.HMI` file.
- If the project shown has unsaved changes, the Nextion Editor first asks whether to save them. When that project is one of the tool's own copies, `open` answers No, since the tool never saves. Otherwise `open` stops before pressing Open, so that nobody's changes are lost. Any other question stops `open` without an answer.
- If the dedicated Editor uses more than 1.1 GB, `open` restarts it first, since the Nextion Editor runs out of memory near 1.4 GB. `open` skips the restart if a window is open over the main window, or if there are unsaved changes.

### `screenshot <file.png>`

`screenshot` saves a picture of the Nextion Editor's main window. The window draws the picture itself, so other windows on top of it do not appear.

### `attributes <page> <component>`

`attributes` prints, as JSON, what the Nextion Editor's Attribute panel lists for one component of the project shown: `{"page", "component", "type", "attributes": [{"name", "value", "hint", "code_can_change"}]}`.

- `type` is the name of the component's type, such as `"Text"`.
- Each attribute comes with its value, the hint the Nextion Editor shows for it, and `code_can_change`. `code_can_change` is true when the attribute's name is green, meaning code can change the attribute, and false when the name is black.
- To get a page's own attributes, give the page's name as the component.
- Reading takes about a second per attribute.

### `simulate <file.png> [--send <instruction> [--hex]]`

`simulate` starts the simulator on the project shown with the toolbar's Debug button, saves a picture of the simulator's window, and closes the simulator.

- With `--send`, `simulate` first types the instruction into the simulator's instruction box, line by line, and runs it.
- To know when the instruction has finished, the command adds a last line, `get 1`, and waits for the first answer. If an earlier line answers too, as `get` and `print` do, the wait can end at that answer, before the later lines have run.
- An instruction that resets the simulator, such as `rest`, can lose the answer to `get 1`. The command then stops once its wait runs out.
- With `--hex` as well, each line is hexadecimal bytes, such as `68 65 6C 6C 6F`, sent exactly as written, without the FF FF FF that ends a line of text. Use `--hex` for bytes that are not an instruction, such as the data of a transfer. If the bytes leave an instruction unfinished or a transfer short, the final `get 1` is swallowed into them, and the command stops once its wait runs out.
- If a simulator is already open, the command stops. Whenever the command stops, it closes any simulator still showing.
- If a window appears over the simulator, such as "File Header Data Error" for a data record's file, the command stops at once and prints the window's text. The simulator cannot close until someone answers that window, so the command leaves both open. Answer the window, then run `close-simulator`.

### `simulate <file.png> --touch <steps>`

`simulate --touch` touches the simulator's screen after any instruction, and before the picture. Separate the steps with semicolons:

- `press X,Y` presses the screen at pixel (X, Y), in the same coordinates as a component's `x` and `y`;
- `release` lifts the press where it was made;
- `wait MS` waits that many milliseconds;
- `picture FILE` saves a picture of the simulator's window to FILE, just like the final picture.

For example, `"press 200,150; picture held.png; release; wait 500"` takes a picture of a component while it is held down, then lets go.

- The steps are checked before the simulator starts, against the screen size `open` recorded. The command stops, and says which step is wrong, for a point off the screen, a press while another press is held, or a release with no press held. The command also stops if `open` did not open the project shown.
- The command pauses 50 ms after each press and release. Before each picture, the command waits until the simulator has run what the earlier touches set off, by typing `get 1` the way `--send` does.
- No step can move a held press, because the simulator does not accept drags through window messages. Drag in the simulator by hand.
- Typing in the instruction box slows the simulator's timers. To time an interval with `wait`, keep `--send` lines and `picture` steps out of that interval, since a picture waits by typing `get 1`.

### `catalog <file.json> [--variant <name>] [--known <file.json>]`

`catalog` reads the attributes of every component on every page of the project shown, and of the pages themselves, the same way `attributes` does. The result is written as JSON: `{"variant", "project", "objects": [{"page", "component", "type", "attributes"}]}`, where `type` is the number the project stores for the component's type.

- `--variant` names the catalog, so that merged catalogs can be told apart.
- `--known` takes an earlier catalog. Rows whose hint that catalog already has for the same type are not clicked, and get no hint.
- Keep catalogs under `tools/editor/build/`, which git ignores, because they contain the Nextion Editor's hints, and those are not nxwright's to publish.
- Cataloguing a project of 32 objects takes about 12 minutes, and nearly as long with `--known`, which saves only the clicks for hints.

### `compile`

`compile` compiles the project shown with the toolbar's Compile button. When the compile ends, the command prints which project it compiled, then the contents of the Nextion Editor's Output panel: the screen's memory, the global memory, each page's memory, and anything the compile refused.

- The command clears the Output panel first, so that the panel shows only this compile.
- If the compile fails, the command still succeeds, and the Output panel says why.

### `tft <folder>`

`tft` compiles the project shown, and writes its TFT file into the folder, named after the project, replacing any file with that name. The command prints the file's path, then the contents of the Output panel.

- If the compile fails, the command stops without writing the file.
- The command closes the Explorer window that the Nextion Editor opens on the folder.
- Your own Nextion Editor shares the dedicated Editor's settings, so it will suggest the same folder the next time you write a TFT file.

### `status`

`status` reports whether the dedicated Editor is running, which project it shows, and who has a hold on it, if anyone.

### `hold <name> [--minutes N]` and `release <name>`

`hold` reserves the dedicated Editor for one holder across several commands. A probe that runs `open` and then `simulate` needs a hold, because each command takes the lock only for itself, and someone else's command could slip in between the two.

- Every command except `hold` and `release` gives its holder's name with `--as <name>`.
- While the hold lasts, the holder's commands run, and each one renews the hold for its full length: 10 minutes by default, at most 60, set with `--minutes`.
- Everyone else's commands are refused with the holder's name and the time the hold ends, and exit with 3, so that a script can wait and retry. `status` still works for everyone.
- `release <name>` ends the hold early. Otherwise the hold ends when its time runs out.
- Anyone can release a hold by giving its holder's name, for example to end a forgotten hold. A hold keeps two probes from colliding, but does not protect against misuse.

### `close-simulator`

`close-simulator` closes a simulator that the dedicated Editor is showing. A simulator can be left behind when `simulate` is stopped from outside, for example by closing its terminal, or when the simulator appears only after `simulate` has stopped. If the simulator will not close, the command lists the windows over it. The command never starts a Nextion Editor.

### `close-file-dialog`

`close-file-dialog` cancels a file dialog left open in the dedicated Editor by an `open` that was stopped from outside, for example by closing its terminal. While a file dialog is open, every other command stops on it. If `open` fails after its file dialog appears, `open` cancels the dialog itself. The command never starts a Nextion Editor.

## Every attribute of every type

`tools/editor/catalog_variants.py` catalogs every attribute the Nextion Editor shows, for every component type. Run the script with the tool's Python, from nxwright's folder. A run takes about two hours: twelve projects at about eleven minutes each.

1. The script builds the every-component project from `tests/fixtures/every-component` with nxwright, then opens and catalogs it.
2. The Attribute panel only shows the attributes that apply under the current choices, so variants of the project come next. Variant k sets every choice attribute of every component to choice k, where the attribute's hint lists a choice k. Each variant is catalogued with `--known`.
   - Only the choice attributes shown in the project as built are varied. A choice attribute that appears only in a variant, such as `pic` once `sta` is "image", keeps its value in every variant.
3. The catalogs are then merged with `catalog.py` and compared with nxwright's component defaults. `report.md` lists:
   - the attributes nxwright lists but the Nextion Editor never showed;
   - the attributes the Nextion Editor showed but nxwright does not list;
   - the attributes whose name showed in both colours;
   - the defaults that differ;
   - every attribute, with its hint.
4. Finally, nxwright's own attribute descriptions (`nxwright/project/attribute_descriptions.toml`) are checked against the Nextion Editor's hints. Any description that matches a hint is listed, to catch a hint pasted in by mistake.

- Everything is written to `tools/editor/build/catalog/`, or to the folder given.
- If another command opened another project in the dedicated Editor between two of the script's steps, it stops.
- The script reuses any project or catalog that a stopped run left in the folder. Delete a project or catalog to have the script make a fresh one.

## The memory each page takes

`tools/editor/memory_probe.py` measures how much memory the Nextion Editor's compile counts on each series of screens. Run the script with the tool's Python, from nxwright's folder. The results go in `nxwright/project/memory_costs.toml`, the table that nxwright's build checks pages against. `docs/format.md` explains the table, under The Nextion Editor's memory.

The script builds probe projects with nxwright, compiles each one in the dedicated Editor, and fits a rule to each attribute's costs. `memory_probe.py`'s docstring lists what is measured. Only the series whose rules match every page and project compiled go in the table, and anything that could not be measured is reported.

- `--series T,P` measures only series T and P. The other series keep their values in the table.
- Each project and its compile output are kept in `tools/editor/build/memory/`, or in the folder given, so that a stopped run picks up where it left off. Delete a project's folder to compile it again.
- The script holds the dedicated Editor for its whole run, as `memory-probe-<process ID>`, and stops at once if someone else holds it.
- If the script's process is killed, the script cannot release its hold. Release the hold yourself with `editor.py release memory-probe-<process ID>`, using the name `status` shows.
- Because the script opens many projects, `open` may restart the Nextion Editor along the way, once it passes 1.1 GB.

## Its tests

The tests of the tool's records, its lock, the logic of its catalog and memory probe, and how it finds a Nextion Editor window need neither the Nextion Editor nor pywinauto. These tests run with nxwright's own Python, on Windows. The tests of the `open` and `tft` commands import the tool itself and run against stand-ins for the Nextion Editor's windows, so they also need the tool's packages from `requirements.txt`:

```
python -m unittest discover -s tools/editor/tests -t .
```

The memory probe's tests run the probe against a stand-in Nextion Editor, whose compile counts memory from a known table. The probe must find that table again.
