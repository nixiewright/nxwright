# A probe of `ram/` files for a real screen

`ram_probe.py` checks whether a real screen follows the rules that nxwright's simulator took from the Nextion Editor's simulator for files in `ram/`, for the names of the SD cards, and for a data record or a file browser whose path is in `ram/`. The probe sends the screen the instructions that the Nextion Editor's simulator was given, and writes a report that shows where the screen answers differently. No real screen has been checked yet.

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

## What the probe changes on the screen

The probe creates files in `ram/`, which the screen loses when it is switched off, and files on the SD card whose names start with `nxprobe`. It deletes each file it creates, but if a run is cut short, a file whose name starts with `nxprobe` may stay on the SD card.

The probe also sets `bkcmd` to 2, which is the screen's own value when it is switched on.

## The probe's tests

`tests/test_screen_probe.py` runs the checks against nxwright's simulator in place of a screen. It fails when nxwright's simulator stops giving the answers of the Nextion Editor's simulator.
