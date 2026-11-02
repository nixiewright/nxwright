# Moving nxwright to a new Nextion Editor release

This runbook gives the steps for checking nxwright against a new release of the Nextion Editor, from the weekly check to the release nxwright is then tested with. The tool's [README](README.md#new-nextion-editor-releases) describes each script.

## 1. The check finds a new release

`tools/editor/latest_release.py` prints the version Nextion offers, with its release notes. A GitHub workflow runs it every Monday, and fails its run when Nextion offers a version other than the one in `tools/editor/tested_editor.toml`.

Read the release notes. They say what changed, which tells you what to look for first in the reports of step 3.

## 2. Download the two releases

Nextion serves each release as a zip, at the address of its installer with `.zip` in place of `.exe`. For 1.68.2, that is `https://nextion.tech/download/nextion-setup-v1-68-2.zip`.

- Download the zip of the new release, and the zip of the release nxwright is tested with.
- Unpack each into a new folder of its own. The Nextion Editor runs from such a folder without being installed, so the Nextion Editor you have installed is not changed.
- The zips of 1.68.1 and 1.68.2 name the program `Nextion Editor.exe`, and older zips name it `NextionEditor.exe`.

## 3. Run the comparisons

Run each comparison with nxwright's own Python, from nxwright's folder. Give the program of the release nxwright is tested with as `--old`, and the new release's as `--new`:

```
python tools/editor/release_pass.py round-trip --old <old program> --new <new program> <output folder>
python tools/editor/release_pass.py catalog --old <old program> --new <new program> <output folder>
python tools/editor/release_pass.py models --old <old program> --new <new program> <output folder>
python tools/editor/release_pass.py files --old <old folder> --new <new folder> <report.md>
```

- The round trip, catalog, and models comparisons drive the two releases under Editor names of their own, so your own Nextion Editor is left alone. The files comparison drives no Nextion Editor.
- The Nextion Editor comes to the front while the comparisons run, so leave the computer to them. Do not minimize a Nextion Editor they started: the Editor tool cannot drive a minimized one.
- The catalog comparison takes about two hours for each release.
- Each comparison writes `report.md`. With the same release as both sides, each report lists nothing.

The findings are what the reports list for the new release:

- **The round trip:** what the new release alone changes when it opens, compiles, and saves the projects nxwright builds.
- **The catalogs:** component types and attributes added or removed, and hints, lists of choices, and name colours that changed.
- **The screen models:** models the new release adds to nxwright's table of screen models, models of the table it lacks, and models it lists at another size. If the tool cannot read a release's device settings, the report gives the error instead. Then open the device settings of that release by hand, with its toolbar's Device button, and compare each series' models with the table.
- **The files:** the files of the release that changed. A changed `model0.sa` or `model1.sa` points at a change to the screen models.

## 4. Deal with each finding

- **A new attribute or component type:** open an issue for it, so that it can be supported properly later. Meanwhile, a project that uses it still comes back the same: extract keeps an attribute nxwright does not know as its stored bytes, and keeps a component of a type nxwright does not know exactly.
- **A new screen model:** save one project of that model in the new release. Its device ID and its stamp number come from that project. Its diagonal, flash, RAM, and frequency come from its tile in the device settings. Add the project's manifest to `tests/fixtures/manifests/`, and the model to the table in `nxwright/project/screen_models.py`.
- **Any other finding:** fix nxwright, with a test that fails before the fix.

## 5. Move to the new release

- Change the version in `tools/editor/tested_editor.toml`, and in the two places that name it as the version nxwright is tested with: nxwright's README and the tool's README. A test checks that the three agree.
- Have the change reviewed, then publish it.
- Install the new release of the Nextion Editor when you choose. The Editor tool drives the installed Nextion Editor unless `NXWRIGHT_EDITOR` names another program.
