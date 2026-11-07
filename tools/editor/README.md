# Driving the Nextion Editor

The Editor tool is an optional script for contributors who have the Nextion Editor. It opens projects, compiles them, writes their TFT files, takes screenshots, and reports what the Nextion Editor shows, so you can see how the Nextion Editor behaves without clicking through it by hand. nxwright and its tests never run the tool.

You need Windows and the Nextion Editor 1.68.2, the version nxwright is tested with.

## The tool's rules

- **A dedicated Editor.** The tool starts its own Nextion Editor, called the dedicated Editor, and reuses it on every later run. The tool never touches a Nextion Editor you opened yourself.
- **No keyboard or mouse input.** The tool drives the dedicated Editor through UI Automation, the Windows interface for controlling another program, and by sending messages to its windows.
- **The Nextion Editor comes to the front** during `open` and `simulate`, so anything you type would go to the Nextion Editor. Click back into your own window before you type. Bringing the Nextion Editor to the front yourself, to watch, does not disturb the tool.
- **Copies only.** The tool opens a copy of each project, and a new copy replaces the old copy of the same name. The Nextion Editor locks the project it shows, though, so a copy of that project goes next to the locked one, under a name like `demo (2).HMI`. `save` saves the copy, never a project of yours, and writes the result to a new file. The tool never deletes a folder.
- **The tool stops rather than guess.** A command stops and reports what it found when it meets a control it cannot drive, the Nextion Editor's unhandled exception dialog, or a window over the simulator.
- **A command gives up after five minutes without progress,** for example when a call into the Nextion Editor never returns. The command then prints "Timeout" and where each of its threads was, and releases the lock that lets only one command at a time drive the Nextion Editor.

Two problems with a data record can hang the Nextion Editor, so fix them before you open the project:

- **A missing folder.** If a data record's `path` points to a folder missing from its SD card, such as `sd0/probe/d.data` when `sdcard0` has no `probe` folder, the Nextion Editor hangs while opening the project, does not draw a page, and cannot be closed normally. Create the folder on the card first.
- **A missing file.** If a data record's file is missing and its `mode` is 0, the simulator stops responding when the record's page opens, and the Nextion Editor does not close until you end its process. Give the record a file, or set its `mode` to 1, which creates one.

### Several Nextion Editors

The environment variable `NXWRIGHT_EDITOR_NAME` picks which dedicated Editor the tool drives. Each agent or person can then have a Nextion Editor of their own, and nobody waits for anyone else:

```
NXWRIGHT_EDITOR_NAME=agent-c python tools/editor/editor.py open demo.HMI
```

- A name is up to 32 letters, digits, `-`, or `_`. The tool refuses any other name before doing anything.
- Scripts that run the tool's commands, such as `catalog_variants.py`, pass the name on.
- Without a name, the tool drives the shared Editor. Each Windows user has one shared Editor, used by the scripts of every checkout.
- `status` and every command that stops print which Nextion Editor they used, such as "agent-c's Editor" or "the shared Editor".

Each dedicated Editor keeps its records in `%LOCALAPPDATA%\nxwright\editor-<name>\`, or in `%LOCALAPPDATA%\nxwright\editor\` for the shared one. The `work\` folder inside contains the copy of the project being shown.

All the Nextion Editors of one Windows user still share the Nextion Editor's own files, in `%APPDATA%\Nextion Editor\`:

- the settings, which every Nextion Editor rewrites;
- the folders the simulator uses as SD cards, `sdcard0` and `sdcard1`;
- the simulator's EEPROM, `eeprom\eeprom.bin`;
- the values the simulator keeps from one run to the next, such as `dims`.

Name any files your probe writes on a card after yourself, so that they do not clash with anyone else's. Tell the others before you probe the EEPROM or a kept value.

Each Nextion Editor compiles into its own folder.

A Nextion Editor stays open until `save` or `quit` closes it, except that `open` restarts one that has grown past 1.1 GB of memory. When you are done with one, run `quit`, or close its window yourself.

## Setting up the tool

The tool's packages are pinned in `requirements.txt`, and go in their own virtual environment, separate from nxwright's:

```
python tools/editor/bootstrap.py
```

`bootstrap.py` creates the environment in `tools/editor/build/venv`, using the Python you run it with, and refuses if that folder already exists.

From then on, run the tool with that environment's Python, called the tool's Python below. Either activate the environment, or call `tools/editor/build/venv/Scripts/python`. The commands below just write `python`.

Whenever `requirements.txt` changes, update the environment with the tool's Python:

```
python -m pip install -r tools/editor/requirements.txt
```

The tool looks for the Nextion Editor at the path in the environment variable `NXWRIGHT_EDITOR`, if set, and otherwise where the Nextion Editor's installer recorded it. To use an older release, unpack it from its zip and set `NXWRIGHT_EDITOR` to its program, such as `NextionEditor.exe` in the folder unpacked from `nextion-setup-v1-63-3.zip`. Give each release its own `NXWRIGHT_EDITOR_NAME`, because `open` and the other commands that would reuse a dedicated Editor stop if it is already running another program.

## The tool's commands

Run the commands with the tool's Python, from nxwright's folder:

```
python tools/editor/editor.py open examples/thermostat/thermostat.HMI
python tools/editor/editor.py screenshot editor.png
python tools/editor/editor.py attributes home title
python tools/editor/editor.py simulate schedule.png --send "page schedule"
python tools/editor/editor.py simulate after.png --touch "press 200,150; release"
python tools/editor/editor.py catalog tools/editor/build/catalog.json
python tools/editor/editor.py models tools/editor/build/models.json
python tools/editor/editor.py compile
python tools/editor/editor.py tft tools/editor/build/tft
python tools/editor/editor.py save tools/editor/build/saved.HMI
python tools/editor/editor.py quit
python tools/editor/editor.py status
python tools/editor/editor.py close-simulator
python tools/editor/editor.py close-file-dialog
python tools/editor/editor.py close-message
python tools/editor/editor.py hold agent-b --minutes 15
python tools/editor/editor.py open demo.HMI --as agent-b
python tools/editor/editor.py release agent-b
```

If another command has the lock, a command waits for it, then gives up and prints which process has it.

### `open <project.HMI>`

`open` copies the project into the work folder, then opens the copy with the Nextion Editor's Open button.

- Once the copy is open, `open` deletes the other `.HMI` files in the work folder, which are copies of earlier projects. A copy the Nextion Editor still has open is kept, and so is every file that is not an `.HMI` file.
- If the project shown has unsaved changes, the Nextion Editor first asks whether to save them. When that project is one of the tool's own copies, `open` answers No, and the changes are dropped. Otherwise `open` stops before pressing Open, so that nobody's changes are lost. Any other question stops `open` without an answer.
- If the dedicated Editor uses more than 1.1 GB, `open` restarts it first, since the Nextion Editor runs out of memory near 1.4 GB. `open` skips the restart if a window is open over the main window, or if there are unsaved changes.

### `screenshot <file.png>`

`screenshot` saves a picture of the Nextion Editor's main window. The window draws the picture itself, so other windows on top of it do not appear.

### `attributes <page> <component>`

`attributes` prints, as JSON, what the Nextion Editor's Attribute panel lists for one component of the project shown: `{"page", "component", "type", "attributes": [{"name", "value", "hint", "code_can_change"}]}`.

- `type` is the name of the component's type, such as `"Text"`.
- `code_can_change` is true when the attribute's name is green, meaning code can change the attribute, and false when the name is black.
- To get a page's own attributes, give the page's name as the component.
- Reading takes about a second per attribute.

### `simulate <file.png> [--send <instruction> [--hex]]`

`simulate` starts the simulator on the project shown with the toolbar's Debug button, saves a picture of the simulator's window, and closes the simulator.

- With `--send`, `simulate` first types the instruction into the simulator's instruction box, line by line, and runs it.
- To know when the instruction has finished, the command adds a last line, `get 1`, and waits for the first answer. If an earlier line such as `get` or `print` also answers, the wait can end at that answer, before the later lines have run.
- An instruction that resets the simulator, such as `rest`, can lose the answer to `get 1`. The command then stops once its wait runs out.
- With `--hex` as well, each line is hexadecimal bytes, such as `68 65 6C 6C 6F`, sent exactly as written, without the FF FF FF that ends a line of text. Use `--hex` for bytes that are not an instruction, such as the data of a transfer. If the bytes leave an instruction unfinished or a transfer short, the final `get 1` is swallowed into them, and the command stops once its wait runs out.
- If a simulator is already open, the command stops, and leaves that simulator open. If the command stops for any other reason, it closes the simulator, unless a window has appeared over it.
- If a window appears over the simulator, such as "File Header Data Error" for a data record's file, the command stops at once and prints the window's text. The simulator cannot close until someone answers that window, so the command leaves both open. Answer the window, then run `close-simulator`.

### `simulate <file.png> --touch <steps>`

`simulate --touch` touches the simulator's screen after any instruction, and before the picture. Separate the steps with semicolons:

- `press X,Y` presses the screen at pixel (X, Y), in the same coordinates as a component's `x` and `y`;
- `release` lifts the press where it was made;
- `wait MS` waits that many milliseconds;
- `picture FILE` saves a picture of the simulator's window to FILE, just like the final picture.

For example, `"press 200,150; picture held.png; release; wait 500"` takes a picture of a component while it is held down, then lets go.

- The command checks the steps against the screen size `open` recorded, before the simulator starts. It stops for a point off the screen, a press while another press is held, or a release with no press held. The command also stops if `open` did not open the project shown.
- The command pauses 50 ms after each press and release. Before each picture, the command waits until the simulator has run what the earlier touches set off, by typing `get 1` the way `--send` does.
- No step can move a held press, because the simulator does not accept drags through window messages. Drag in the simulator by hand.
- Typing in the instruction box slows the simulator's timers. To time an interval with `wait`, keep `--send` lines and `picture` steps out of that interval, since a picture waits by typing `get 1`.

### `catalog <file.json> [--variant <name>] [--known <file.json>]`

`catalog` reads the attributes of every component on every page of the project shown, and of the pages themselves, the same way `attributes` does. The result is written as JSON: `{"variant", "project", "editor_version", "objects": [{"page", "component", "type", "attributes"}]}`. `editor_version` is the version that the Nextion Editor's program file gives, such as `1.68.2.3035`, and `type` is the number the project stores for the component's type.

- `--variant` names the catalog, so that merged catalogs can be told apart.
- `--known` takes an earlier catalog. If that catalog already has the hint for an attribute of the same component type, the tool does not click the attribute's row, and the new catalog leaves out the hint.
- Keep catalogs under `tools/editor/build/`, which git ignores, because they contain the Nextion Editor's hints, and those are not nxwright's to publish.
- Cataloguing a project of 32 objects takes about 12 minutes, and nearly as long with `--known`, which saves only the clicks for hints.

### `models <file.json>`

`models` reads the screen models that the Nextion Editor's device settings offer, and writes them as JSON: `{"editor_version", "models": [{"series", "inch", "width", "height", "flash", "ram", "frequency"}]}`. The command opens the settings with the toolbar's Device button, and cancels them once it has read them, so the project keeps its model.

- A project must be open, since the Device button is greyed out otherwise.
- UI Automation does not give a model's name, only the text of its tile. So each model is given by its series, its diagonal in inches, and its size in pixels, along with its memory and frequency. The Nextion Editor 1.68.2 lists NX3224T024 as series `T`, 2.4 inches, 240 by 320.
- The settings' series buttons show only pictures, so the command takes the series from their order: Basic (T), Discovery (F), Enhanced (K), Intelligent (P), and Edge (E). If the settings show another number of series, or a tile whose text is not in the form the tool expects, the command stops, and its error gives that number or text.
- From the second series on, the command stops if pressing a series' button leaves the previous series' tiles on screen, which happens when the press does not register.
- The device settings of the Nextion Editor 1.63.3 are laid out differently, and the command stops on them.

### `compile`

`compile` compiles the project shown with the toolbar's Compile button. When the compile ends, the command prints which project it compiled, then the contents of the Nextion Editor's Output panel: the screen's memory, the global memory, each page's memory, and anything the compile refused.

- The command clears the Output panel first, so that the panel shows only this compile.
- If the compile fails, the command still succeeds, and the Output panel says why.
- If the compile has not ended after 120 seconds, the command stops, and its error quotes what the Output panel showed, if anything. `tft` stops the same way.

### `tft <folder>`

`tft` compiles the project shown, and writes its TFT file into the folder, named after the project, replacing any file with that name. The command prints the file's path, then the contents of the Output panel.

- If the compile fails, the command stops without writing the file.
- The command closes the Explorer window that the Nextion Editor opens on the folder.
- Your own Nextion Editor shares the dedicated Editor's settings, so it will suggest the same folder the next time you write a TFT file.

### `save <file.HMI>`

`save` saves the project shown with File > Save as, closes the dedicated Editor, and copies the saved project to the file given. The project shown must be a copy that `open` made.

- The command refuses a file that already exists, before it touches the Nextion Editor.
- The Nextion Editor saves into the work folder, under the copy's name with " (saved)" added.
- The dedicated Editor has to close first, because the Nextion Editor keeps the file it shows locked against reading until it closes.

### `quit`

`quit` closes the dedicated Editor. If the project shown is one of the tool's own copies and has unsaved changes, the Nextion Editor asks whether to save them, and `quit` answers No.

The command stops, leaving the Nextion Editor open, if the project shown is not one of the tool's copies and has unsaved changes, or if a dialog or message is open. Any other question the Nextion Editor asks when it closes stops the command too, unanswered.

### `status`

`status` reports whether the dedicated Editor is running, the program it runs and that program's version, the project it shows, and any hold on it.

### `hold <name> [--minutes N]` and `release <name>`

`hold` reserves the dedicated Editor for one holder across several commands. A probe that runs `open` and then `simulate` needs a hold, because each command takes the lock only for itself, and someone else's command could slip in between the two.

- To run any command except `hold` and `release` as the holder, add `--as <name>`.
- A hold lasts 10 minutes by default and at most 60, set with `--minutes`. Each of the holder's commands renews the hold for its full length.
- Everyone else's commands are refused with the holder's name and the time the hold ends, and exit with 3, so that a script can wait and retry. `status` still works for everyone.
- `release <name>` ends the hold early. Anyone can do this by giving the holder's name, for example to end a forgotten hold. A hold keeps two probes from colliding, but does not protect against misuse.

### `close-simulator`

`close-simulator` closes a simulator that the dedicated Editor is showing. A simulator can be left behind when `simulate` is stopped from outside, for example by closing its terminal, or when the simulator appears only after `simulate` has stopped. If the simulator will not close, the command lists the windows over it.

### `close-file-dialog`

`close-file-dialog` cancels a file dialog left open in the dedicated Editor by an `open` or a `save` that was stopped from outside, for example by closing its terminal. While a file dialog is open, every other command stops on it.

### `close-message`

`close-message` closes any messages left open in the dedicated Editor, and prints each message's text. When a command stops on a message, such as "First character of a Name can not be number" as a project opens, it leaves the message open. Every later command then stops on that message too, until you close it.

- The command also closes the Nextion Editor's other dialogs. It leaves a file dialog to `close-file-dialog`, which cancels it.
- The command closes each message with its close box, and never presses a button such as OK or Yes.
- A message still open after 15 seconds is listed with "(still open)" after its text.
- A window over the simulator, such as "File Header Data Error", has not been tried with this command.

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
- If another command opened another project in the dedicated Editor between two of the script's steps, the script stops.
- The script reuses any project or catalog that a stopped run left in the folder. Delete a project or catalog to have the script make a fresh one.

## The memory each page takes

`tools/editor/memory_probe.py` measures how much memory the Nextion Editor's compile counts on each series of screens. Run the script with the tool's Python, from nxwright's folder. The results go in `nxwright/project/memory_costs.toml`, the table that nxwright's build checks pages against. See [The Nextion Editor's memory](../../docs/format.md#the-nextion-editors-memory) for what the compile counts, and `memory_table.py`'s docstring for how the table works.

The script builds probe projects with nxwright, compiles each one in the dedicated Editor, and fits a rule to each attribute's costs. `memory_probe.py`'s docstring lists what is measured. Only the series whose rules match every page and project compiled go in the table, and anything that could not be measured is reported.

- `--series T,P` measures only series T and P. The other series keep their values in the table.
- Each project and its compile output are kept in `tools/editor/build/memory/`, or in the folder given, so that a stopped run picks up where it left off. Delete a project's folder to compile it again.
- The script holds the dedicated Editor for its whole run, as `memory-probe-<process ID>`, and stops at once if someone else holds it.
- If the script's process is killed, the script cannot release its hold. Release the hold yourself with `editor.py release memory-probe-<process ID>`, using the name `status` shows.

## New Nextion Editor releases

`tools/editor/tested_editor.toml` records the Nextion Editor release that nxwright is tested with. `tools/editor/latest_release.py` asks Nextion's server whether it offers another. Run the script with nxwright's own Python:

```
python tools/editor/latest_release.py
```

- Nextion's server gets the same request that the Nextion Editor sends when it checks for a newer version, without the identifier of your computer.
- The script prints the version Nextion offers, with the release notes of a new one. It exits with 0 when Nextion offers the version tested with, and with 1 when it offers another. It exits with 2 when the server cannot be reached, or its answer is not in the form the script reads.
- A GitHub workflow runs `latest_release.py` every Monday (`.github/workflows/release-check.yml`). The run fails when the script exits with 1 or 2, and its log shows what the script printed.

The comparisons below show how a new release differs from the one nxwright is tested with. Run them with nxwright's own Python, from nxwright's folder. A run of the Nextion Editor 1.68.2 against itself has no findings in the round trip, catalog, or models report, so anything they find comes from the new release. See [RELEASES.md](RELEASES.md) for the steps to move nxwright to a new release.

### The round trip

`tools/editor/release_pass.py round-trip` shows how a new Nextion Editor treats the projects nxwright builds, compared with the Nextion Editor nxwright is tested with:

```
python tools/editor/release_pass.py round-trip --old <old program> --new <new program> <output folder>
```

- The projects are the demo, a fixture of the tests, a project of one component of each type, and one small project for each screen series. `tools/editor/round_trip/` contains their pictures and sound, which nothing else uses.
- Each Nextion Editor, named `release-old` or `release-new`, opens each project, compiles it in its simulator, and saves it. A step that fails is tried once more, in a fresh Nextion Editor.
- The script then extracts each saved project into a new folder, and compares it with the project as nxwright built it, extracted the same way: the folders file by file, and the project files block by block.
- `report.md` in the output folder lists what the old Nextion Editor's save changes, then the findings: what only the new Nextion Editor changes.
- The Nextion Editor comes to the front during each `open` and `simulate`, so the run is best left to itself.

### The catalogs of two Nextion Editors

`tools/editor/release_pass.py catalog` shows how the Attribute panel of a new Nextion Editor differs from the old one's:

```
python tools/editor/release_pass.py catalog --old <old program> --new <new program> <output folder>
```

- The script runs `catalog_variants.py` on each Nextion Editor in turn, named `release-old` and `release-new`. Each run takes about two hours. See [Every attribute of every type](#every-attribute-of-every-type) for what `catalog_variants.py` does.
- Each Nextion Editor's catalogs, and the log of its run, are written to `old` and `new` in the output folder.
- `report.md` in the output folder lists the component types and the attributes added or removed. For an attribute both Nextion Editors show, it also lists a changed hint, a changed list of choices, and a name that changed colour.

### The screen models of two Nextion Editors

`tools/editor/release_pass.py models` compares each Nextion Editor's list of screen models with nxwright's table of them, `nxwright/project/screen_models.py`:

```
python tools/editor/release_pass.py models --old <old program> --new <new program> <output folder>
```

- Each Nextion Editor, named `release-old` or `release-new`, opens a small project, and lists the screen models it offers with the tool's `models` command. The lists are written to `old.json` and `new.json` in the output folder.
- `report.md` in the output folder lists, for each Nextion Editor, the models missing from nxwright's table, and the table's models that Nextion Editor does not list. If a table's model is missing from a Nextion Editor, and that Nextion Editor lists one other model of the same series and diagonal at another size, the report lists that other model as resized.
- If one Nextion Editor's list cannot be read, the report gives the error, and the other's list is still compared.

### The files of two releases

`tools/editor/release_pass.py files` lists the files that differ between the folders of two releases, each unpacked from its zip:

```
python tools/editor/release_pass.py files --old <old folder> --new <new folder> <report.md>
```

A changed `model0.sa` or `model1.sa` points at a change to the list of screen models. Between 1.60.1 and 1.63.3, for example, both changed, and the keyboards gained a fourth page for each screen size.

## The tool's tests

The tool's tests do not need the Nextion Editor. Run them on Windows, from nxwright's folder:

```
python -m unittest discover -s tools/editor/tests -t .
```

Most of them run with nxwright's own Python. The tests that import the tool itself, such as those of the `open` and `tft` commands, run against stand-ins for the Nextion Editor's windows, and also need the tool's packages from `requirements.txt`.
