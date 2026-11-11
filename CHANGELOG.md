# Changelog

The toolchain and the VS Code extension have [separate version numbers](CONTRIBUTING.md#versions), so each has its own list here. To see which version of the toolchain you have, run `nxwright --version`.

## Toolchain

### [0.3.19] - 2026-11-12

- The simulator now shows a video's frames when its file is in `ram/` or on an SD card with no folder.

### [0.3.18] - 2026-11-12

- An external picture now shows a picture file in `ram/`, or on an SD card that has no folder.
- An external picture whose file is missing now answers 0x06.
- The simulator's log now shows when an external picture's file is missing, or is not a picture.

### [0.3.17] - 2026-11-11

- A data record whose file is missing on an SD card now shows "File Lost:" and the file's path.
- `rdfile`, `delfile`, `refile`, and `newfile` are now ignored on a file a data record keeps open.
- A file stream no longer opens a file that a data record keeps open.

### [0.3.16] - 2026-11-11

- `sd0/` and `sd1/` must now be in lower case, matching the behavior of screens.
- A data record now creates its data file in `ram/` only if the file fits there.
- A data record with no file in `ram/` now shows "File Lost:" and the file's path.
- Setting a data record's `path` now creates a missing data file at once, if `mode` is 1.

### [0.3.15] - 2026-11-11

- `newfile`, `delfile`, `refile`, `newdir`, and `deldir` now need a path on an SD card or in `ram/`.
- The simulator's log now gives the reason when a file command is ignored in `ram/`.

### [0.3.14] - 2026-11-11

- Added `nxwright.testing.run_with_emulator`, for a test to run an app with its MCU emulator.

### [0.3.13] - 2026-11-11

- Files in `ram/` now need `memory_file_storage_size` in `app.toml`, in the simulator and in tests.
- `twfile` can now write a file in `ram/`.

### [0.3.12] - 2026-11-10

- With the Emulator port, the app now waits for the MCU emulator to connect before it starts.
- Added `wait` to the `[mcu]` table of `app.toml`, to set how long the app waits.

### [0.3.11] - 2026-11-10

- A misspelled component or page name now gets a "Did you mean" hint and a quick fix.

### [0.3.10] - 2026-11-10

- File paths in simulator startup errors are now clickable.

### [0.3.9] - 2026-11-10

- Faster language server updates.

### [0.3.8] - 2026-11-10

- Added an MCU emulator for the thermostat demo.

### [0.3.7] - 2026-11-10

- The simulator can now listen for a connection from a project's MCU emulator.

### [0.3.6] - 2026-11-10

- Faster language server updates.

### [0.3.5] - 2026-11-10

- Added MCU emulators: Python programs that emulate the microcontroller for the screen.
- Added `nxwright new-emulator`, which writes a first MCU emulator for a project.
- Added the `nxwright.mcu` library, for an MCU emulator to read and write the screen's serial line.
- `app.toml` can now have an `[mcu]` table, with the path of the project's MCU emulator.

### [0.3.4] - 2026-11-10

- The simulator's serial line can now connect to a program that listens on a TCP port.

### [0.3.3] - 2026-11-10

- Added conditions to the simulator's value generators, which send instructions when the value crosses a level.

### [0.3.2] - 2026-11-10

- Fixed setting the initial value of an `int` from a constant.
- The build now reports an error for an `int` whose initial value is not a number.
- The build now reports an error for a malformed `int` line, such as `int a b`.

### [0.3.1] - 2026-11-10

- Added value generators to the simulator's signal generator, which send instructions that carry a value.
- Fixed the simulator never ending a step when a timer's event runs `rest`.

### [0.3.0] - 2026-11-10

- `nxwright remove` no longer looks for uses first unless `--checked` is specified.
- `nxwright rename` no longer checks that the folder builds unless `--checked` is specified.
- `nxwright replace --name` no longer looks for uses first unless `--checked` is specified.
- The language server no longer checks renames, added components, or pastes unless a setting turns those checks on.
- The build now reports an error when the name given to `page` is not a page or a variable.
- The `nxwright` command now starts about twice as fast.
- `nxwright remove` and `nxwright replace --name` now look for uses faster in nxlang projects.

### [0.2.16] - 2026-11-10

- Renamed waveform generator to signal generator, added ability to runs multiple generators at once.

### [0.2.15] - 2026-11-10

- Fixed waveforms of global scope losing their points when the page changes.

### [0.2.14] - 2026-11-10

- Added a waveform generator to the simulator.

### [0.2.13] - 2026-11-09

- Added support in the simulator for bridging an MCU and a real screen, logging their communications.

### [0.2.12] - 2026-11-09

- Added support in the simulator for connecting a real screen on a serial port of its own.

### [0.2.11] - 2026-11-09

- Improved performance of page preview and simulator drawing.

### [0.2.10] - 2026-11-09

- Limit values in `defaults.toml` to their valid ranges.

### [0.2.9] - 2026-11-09

- Added support for SVG as a first class citizen of nxwright projects (with defines as var(--ACCENT)).
- A simulation's launch configuration can now override defines.
- The thermostat demo's pictures now use both SVG and PNG files.

### [0.2.8] - 2026-11-09

- `nxwright report` now works on a project with a page nxwright cannot read.
- Extract and dump now say which page block they cannot read, and suggest `nxwright report`.

### [0.2.7] - 2026-11-09

- Better message for unexpected compilation errors due to unsupported code.

### [0.2.6] - 2026-11-09

- Added caching for resource name hints.

### [0.2.5] - 2026-11-08

- The build now rejects another page's own attributes, and its components of local scope.

### [0.2.4] - 2026-11-08

- Pages can now include a `.nx` file with events for components they don't have. 
- Adds the include options `partial` and `strict` to control this
- The page preview can now delete a component whose code is in a shared file.

### [0.2.3] - 2026-11-08

- `nxwright rename` and `nxwright remove` now work on pages too.

### [0.2.2] - 2026-11-08

- Adds `nxwright replace`, which replaces a resource's file and keeps its ID.
- Adds `nxwright rename`, which renames a resource and each use of its name.
- Adds `nxwright remove --keep-ids`, which keeps the IDs of the resource by using a tiny placeholder replacement.
- Shows a resource's name beside a number in your code that stands for it.

### [0.2.1] - 2026-11-08

- Adds defines, values in `app.toml` that you can change for one build with `--define`.
- Adds completion of event headings in `.nx` files.
- Compresses the pictures of F-series projects, which makes their TFT files about 30 percent smaller.
- Fixes overlapping components redrawing each other in a different order from the Nextion Editor.

### [0.2.0] - 2026-11-07

nxwright now takes your app all the way to the screen, on Windows, Linux, and macOS.

- `nxwright compile` turns a source folder or a project file into the TFT file a screen runs. It needs the screen's firmware, which it can get from an existing TFT file, the Nextion Editor, or Nextion's site.
- `nxwright upload` sends a TFT file to a screen over a serial port, and `nxwright ports` lists your computer's serial ports.
- `nxwright rescue` writes a TFT file for an SD card, to recover a screen that a bad setting has left black or unresponsive.
- `nxwright decompile` turns a TFT file back into a source folder, in case you no longer have the project.
- `nxwright tft-read`, `tft-listing`, and `tft-compare` show what is inside TFT files.
- `nxwright diff` shows what differs between a source folder and a project file, or between two project files.
- `compile`, `upload`, and `ports` can print JSON with `--json`, so that programs such as the VS Code extension can read their results.
- `extract` and `import` now write only to a new or empty folder, because updating an existing source folder could lose data.
- Project files that nxwright builds now have their pages locked (no password) to show that they are not meant to be edited: edit the nxwright project folder and rebuild the HMI instead (or simply compile and upload directly from nxwright).
- `dump` can now replace an earlier dump.
- Extracted code now refers to pictures and fonts by name instead of by number, wherever the number can only mean that picture or font.
- nxwright now keeps a backup when it replaces a project file or TFT file that was changed outside nxwright.

### [0.1.0] - 2026-10-23

First public release.

## VS Code extension

### [0.3.19] - 2026-11-11

- The command Add a launch configuration now also adds one for the project's MCU emulator.

### [0.3.18] - 2026-11-10

Needs nxwright 0.3.12 or later.

- With the Python Debugger extension, the MCU emulator now starts with the simulation.
- Added the button Start the emulator again to the Simulator section.
- Added `emulatorWait` to launch configurations, to set how long the app waits for the MCU emulator.

### [0.3.17] - 2026-11-10

Needs nxwright 0.3.7 or later.

- Added Emulator to the Simulator section's MCU port list, for a project that has an MCU emulator.
- Simulations of a project that has an MCU emulator now start with the Emulator port by default.
- Added the command Add an MCU emulator.

### [0.3.16] - 2026-11-10

Needs nxwright 0.3.4 or later.

- Added TCP and None to the Simulator section's MCU port list.
- The MCU port chosen in the Simulator section is now remembered for each project.

### [0.3.15] - 2026-11-10

- Fixed the Components list emptying while a file that pages include has focus.

### [0.3.14] - 2026-11-10

Needs nxwright 0.3.3 or later.

- The Signal generator panel can add conditions to a value generator, which send instructions when the value crosses a level.

### [0.3.13] - 2026-11-10

Needs nxwright 0.3.1 or later.

- The Signal generator panel can add value generators, which send instructions that carry a value.

### [0.3.12] - 2026-11-10

Needs nxwright 0.3.0 or later.

- Delete now confirms immediately, and by default deletes a page or resource that is still used.
- New setting `nxwright.checks.delete` adds an opt-in check for page or resource uses before deleting.
- By default, Rename, Replace, adding a component, and pasting no longer check the project first.
- New settings `nxwright.checks.rename`, `.replace`, `.addComponent`, and `.paste` turn those checks back on.
- Fixed Rename in the Components list and preview menu failing when a TOML extension is installed.
- Decompile now writes the folder even if the round trip check fails, and warns instead of asking.

### [0.3.11] - 2026-11-10

Needs nxwright 0.2.16 or later.

- The Waveform generator panel is now the Signal generator panel, and runs several generators at once.

### [0.3.10] - 2026-11-10

Needs nxwright 0.2.14 or later.

- Added the Waveform generator panel, opened from the Simulator section.

### [0.3.9] - 2026-11-09

Needs nxwright 0.2.13 or later.

- The Simulator section can join the MCU port to a real screen, in place of the simulator.

### [0.3.8] - 2026-11-09

Needs nxwright 0.2.12 or later.

- The Simulator section can connect a real screen, and send typed instructions to it.

### [0.3.7] - 2026-11-09

- An SVG picture now shrinks to fit a small editor.

### [0.3.6] - 2026-11-09

Needs nxwright 0.2.9 or later.

- The Media section can now add SVG pictures.
- Launch configurations can now take the `defines` parameter.
- SVG pictures can now be opened to show how nxwright draws them (with default define values).

### [0.3.5] - 2026-11-08

- Better delete confirmation, and naming skip notification.
- Colors `partial` and `strict` in include lines.

### [0.3.4] - 2026-11-08

Needs nxwright 0.2.3 or later.

- Adds Rename and Delete to the right-click menu of a page, and Rename to a component's.
- Replace Numbers with Names now also covers page numbers.
- Asks first when changing components would change their IDs.
- Fixes a cancelled Cut changing the clipboard.

### [0.3.3] - 2026-11-08

- Shows progress during Build HMI, changing the screen settings, and adding, deleting, replacing, or renaming a resource.

### [0.3.2] - 2026-11-08

Needs nxwright 0.2.2 or later.

- Adds Replace, Rename, and Delete to the right-click menu of the Media section's resources.

### [0.3.1] - 2026-11-08

Needs nxwright 0.2.1 or later.

- Adds Lock page, Lock page with password, and Unlock page.
- Replaces Go to Event... with a submenu that marks the events that have code.
- Adds spacing commands and an arranging toolbar to the page preview.
- Fixes events being added to a locked component or page.

### [0.3.0] - 2026-11-07

Adds support for Compile TFT, Upload TFT, and Decompile. Needs nxwright 0.2.0 or later.

### [0.2.0] - 2026-10-23

First public release. Needs nxwright 0.1.0 or later.
