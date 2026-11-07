# Moving nxwright to a new Nextion Editor release

Follow these steps to check nxwright against a new release of the Nextion Editor, and then to make it the release nxwright is tested with. See [the Editor tool's README](README.md#new-nextion-editor-releases) for what each script does.

## 1. The check finds a new release

A GitHub workflow runs `tools/editor/latest_release.py` every Monday. The run fails when Nextion offers a version other than the one in `tools/editor/tested_editor.toml`, and the run's log shows that version and its release notes.

Read the release notes to see what changed, and look for those changes first in the reports of step 3.

## 2. Download the two releases

Download the zip of the new release, and the zip of the release nxwright is tested with. Nextion serves each zip at the address of the release's installer, with `.zip` in place of `.exe`. For 1.68.2, that is `https://nextion.tech/download/nextion-setup-v1-68-2.zip`.

Unpack each zip into a new folder of its own. The Nextion Editor runs from that folder without being installed, so the copy you have installed does not change.

Step 3 needs the path of the program in each folder. The program is `Nextion Editor.exe` in the zips of 1.68.1 and 1.68.2, and `NextionEditor.exe` in older zips.

## 3. Run the comparisons

Four comparisons show what the new release changes. Run them with nxwright's own Python, from nxwright's folder, with `--old` for the release nxwright is tested with and `--new` for the new release:

```
python tools/editor/release_pass.py round-trip --old <old program> --new <new program> <output folder>
python tools/editor/release_pass.py catalog --old <old program> --new <new program> <output folder>
python tools/editor/release_pass.py models --old <old program> --new <new program> <output folder>
python tools/editor/release_pass.py files --old <old folder> --new <new folder> <report.md>
```

The round trip, catalog, and models comparisons start their own Nextion Editors, and do not touch yours. The files comparison does not start one. Each Nextion Editor that a comparison starts comes to the front while it runs, so do not use the computer until the comparison ends. Do not minimize it either, because the Editor tool cannot drive a minimized one. Plan ahead for the catalog comparison, which takes about two hours for each release.

Each comparison writes a `report.md`, which lists these findings about the new release:

- **The round trip:** what the new release alone changes when it opens, compiles, and saves the projects nxwright builds.
- **The catalogs:** component types and attributes added or removed, and hints, lists of choices, and name colours that changed.
- **The screen models:** models that nxwright's table of screen models lacks, models the new release lacks, and models the new release lists at another size.
- **The files:** the files that changed in the new release. A change to `model0.sa` or `model1.sa` suggests that the screen models changed.

If the screen models report gives an error instead, the comparison could not read the device settings of one of the releases. Open that release's device settings by hand, with the Device button on its toolbar, and compare each series' models with nxwright's table.

## 4. Deal with each finding

- **A new attribute or component type:** open an issue so that nxwright can support it later. Until then, a project that uses it still comes back unchanged after extract and build, because extract keeps an unknown attribute as its stored bytes and a component of an unknown type exactly as it is.
- **A new screen model:** save one project of that model in the new release, and add the project's manifest to `tests/fixtures/manifests/`. Then add the model to the table in `nxwright/project/screen_models.py`. Its device ID and stamp number come from the saved project, and its diagonal, flash, RAM, and frequency come from its tile in the device settings.
- **Any other finding:** fix nxwright, with a test that fails before the fix.

## 5. Run the TFT compile probes

Whatever the comparisons found, run the [TFT compile probes](../tft/README.md) against the new release, and fix the compile wherever nxwright's TFT files differ from the new release's.

## 6. Move to the new release

- Change the version nxwright is tested with in `tools/editor/tested_editor.toml`, nxwright's README, the Editor tool's README, `docs/screens.md`, and `docs/commands.md`. A test checks that they all agree.
- Put the new release's firmware and installer hashes in `nxwright/tft/firmware_versions.py`. See step 4 of [the TFT compile probes' steps](../tft/README.md#the-steps) for how.
- Have the change reviewed, then publish it.

You can install the new release of the Nextion Editor whenever you like. Until you do, the Editor tool keeps driving the copy you have installed, unless `NXWRIGHT_EDITOR` gives the path of another program.
