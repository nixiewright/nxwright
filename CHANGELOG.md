# Changelog

The toolchain and the VS Code extension have [separate version numbers](CONTRIBUTING.md#versions), so each has its own list here. To see which version of the toolchain you have, run `nxwright --version`.

## Toolchain

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
