# Changelog

The toolchain and the VS Code extension have [separate version numbers](CONTRIBUTING.md#versions), so each has its own list here. To see which version of the toolchain you have, run `nxwright --version`.

## Toolchain

### 0.2.0

nxwright now takes your app all the way to the screen, on Windows, Linux, and macOS.

- `nxwright compile` turns a source folder or a project file into the TFT file a screen runs. It needs the screen's firmware, which it can get from an existing TFT file, the Nextion Editor, or Nextion's site.
- `nxwright upload` sends a TFT file to a screen over a serial port, and `nxwright ports` lists your computer's serial ports.
- `nxwright rescue` writes a TFT file for an SD card, to recover a screen that a bad setting has left black or unresponsive.
- `nxwright decompile` turns a TFT file back into a source folder, in case you no longer have the project.
- `nxwright tft-read`, `tft-listing`, and `tft-compare` show what is inside TFT files.
- `nxwright diff` shows what differs between a source folder and a project file, or between two project files.
- `compile`, `upload`, and `ports` can print JSON with `--json`, so that programs such as the VS Code extension can read their results.

Existing commands also changed:

- `extract` and `import` now write only to a new or empty folder, because updating an existing source folder could lose data.
- Project files that nxwright builds now have their pages locked (no password) to show that they are not meant to be edited: edit the nxwright project folder and rebuild the HMI instead (or simply compile and upload directly from nxwright).
- `dump` can now replace an earlier dump.
- Extracted code now refers to pictures and fonts by name instead of by number, wherever the number can only mean that picture or font.
- nxwright now keeps a backup when it replaces a project file or TFT file that was changed outside nxwright.

### 0.1.0

First public release.

## VS Code extension

### 0.3.0

Adds support for Compile TFT, Upload TFT, and Decompile. Needs nxwright 0.2.0 or later.

### 0.2.0

First public release. Needs nxwright 0.1.0 or later.
