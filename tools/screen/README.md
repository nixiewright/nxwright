# Probes for a real screen

This folder has two probes for a real screen. Both run on the same project, `tools/screen/project`.

`ram_probe.py` checks a real screen against the rules that nxwright's simulator follows for files in `ram/`, for the names of the SD cards, and for a data record or a file browser whose path is in `ram/`. The simulator took those rules from the Nextion Editor's simulator. The probe sends the screen the instructions that the Nextion Editor's simulator was given, and writes a report that shows where the screen answers differently.

The probe's checks of a data record cannot run on a real screen yet. The project's data records have `init` 1. On an NX8048P070, the screen showed "Fat cache error" and stopped answering as soon as a check set a data record's `path`. Those checks need the project's data records to have `init` 0.

`firmware_bug_probe.py` checks whether a screen's firmware still has the bugs that nxwright's simulator matches. See [The firmware's bugs](#the-firmwares-bugs) for how to run it. The sections before that one are about `ram_probe.py`.

## What you need

- A screen of the Intelligent or the Edge series, on a serial port of your computer. The other series have no `ram/` files.
- An SD card in the screen, for the checks about the card.
- The screen's firmware, which `nxwright compile` needs ([commands.md, The firmware](../../docs/commands.md#the-firmware)).

## Running it

Run each command from nxwright's folder.

1. Set the project to your screen's model, if it is not an NX8048P050. The project's page is 800 by 480 pixels, so for a smaller screen `device` lists the components that you need to move. This step changes the project's files, so leave the changes out of your commits.

   ```
   python run.py device tools/screen/project --screen NX1060P070
   ```

2. Compile the project, and upload it to the screen. The TFT file contains the firmware, so write it to a folder outside the repository, such as your temporary folder.

   ```
   python run.py compile tools/screen/project <folder>/probe.tft
   python run.py upload <folder>/probe.tft --port COM5
   ```

3. Run the probe, with the screen's port. It asks you four questions about what the screen shows.

   ```
   python -m tools.screen.ram_probe COM5
   ```

The probe writes its report to `ram-probe-report.md` in the folder you ran it from, or to the file given with `--report`. The Nextion Editor's simulator does not take data for `twfile`, so for three checks the report shows "not run" in that simulator's column, and gives the screen's answer alone.

## The checks with no space set aside

The project sets 4096 bytes aside for `ram/` files. Three more checks need a project that sets none aside:

1. Set `memory_file_storage_size = 0` in `tools/screen/project/app.toml`.
2. Compile and upload the project again.
3. Run the probe with `--no-space`.

Set the value back to 4096 afterwards, since the probe's tests need it.

## The firmware's bugs

nxwright's simulator does what a real screen does, even where that is a bug. `matched_firmware_bugs.py` lists the firmware's bugs that the simulator matches, each with the checks that show it and the code that matches it. When you make nxwright's simulator match another bug in the firmware, add the bug to the list, with a check that expects what a real screen answered. A bug goes in the list only once a real screen has shown it.

A later firmware may fix one of these bugs, and nxwright's simulator should then stop matching it. `firmware_bug_probe.py` runs the list's checks on a screen, and reports the bugs that the screen no longer shows. Each check expects what an NX8048P070 answered, so use a screen of the Intelligent series. Follow steps 1 and 2 of [Running it](#running-it), then run the probe with the screen's port.

```
python -m tools.screen.firmware_bug_probe COM5
```

The probe writes its report to `firmware-bug-probe-report.md`, or to the file given with `--report`. For each bug that the screen no longer shows, the report gives the code to change.

Two of the bugs are in how the screen counts and splits the characters of a text in shift-jis. Their checks need the project built in that encoding:

1. Change the project's encoding. This step changes `app.toml` and the project's font, so leave the changes out of your commits.

   ```
   python run.py device tools/screen/project --encoding shift-jis
   ```

2. Compile and upload the project again.
3. Run the probe with `--encoding shift-jis`.

### With a new release of the Nextion Editor

Each release of the Nextion Editor brings its own firmware, and `nxwright compile` takes only the firmware of the release that nxwright is tested with. So have the new release compile the project:

1. Set the project to your screen's model, then build it into a project file outside the repository.

   ```
   python run.py build tools/screen/project <folder>/probe.HMI
   ```

2. Open `probe.HMI` in the new release of the Nextion Editor, and have it write the TFT file.
3. Upload that TFT file, and run the probe.

For the checks in shift-jis, change the project's encoding before step 1, and run the probe with `--encoding shift-jis`.

## What the probes change on the screen

Both probes create files in `ram/`, which the screen loses when it is switched off. `ram_probe.py` also creates files on the SD card whose names start with `nxprobe`. Each probe deletes the files it creates, but if a run of `ram_probe.py` is cut short, a file whose name starts with `nxprobe` may stay on the SD card.

Both probes also set `bkcmd` to 2, which is the screen's own value when it is switched on.

## The probes' tests

`tests/test_screen_probe.py` runs the checks of `ram_probe.py` against nxwright's simulator in place of a screen. It fails when nxwright's simulator stops giving the answers of the Nextion Editor's simulator.

`tests/test_firmware_bug_probe.py` does the same with the checks of the firmware's bugs. It fails when nxwright's simulator stops matching one of the bugs.
