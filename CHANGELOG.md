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
- `compile`, `upload`, and `ports` can print JSON with `--json`, so that programs such as the VS Code extension can read their results.

Existing commands also behave differently:

- `extract` and `import` now refuse a source folder in nxlang, because the code the build writes cannot faithfully be turned back into nxlang and the conversion would be lossy. An nxlang project can still be extracted into a new folder.
- A project file built from a folder in nxlang now has its pages locked, with no password, to show in the Nextion Editor that it is not meant for editing. `--no-lock` turns this off, and unlocking from the Nextion Editor takes a couple of clicks if you need to.
- `build`, `write`, `compile`, and `rescue` now keep a file they replace as a backup beside the new one, such as `app.HMI.2026-11-06-143205.bak`, if it changed since nxwright wrote it. `--no-backup` turns this off.

### 0.1.0

First public release.

## VS Code extension

### 0.3.0

Adds support for Compile TFT, Upload TFT, and Decompile. Needs nxwright 0.2.0 or later.

### 0.2.0

First public release. Needs nxwright 0.1.0 or later.
