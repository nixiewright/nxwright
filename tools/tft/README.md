# TFT compile probes

nxwright's compile matches one release of the Nextion Editor at a time, the one listed in `MATCHED_VERSIONS` (`nxwright/tft/firmware_versions.py`). The probes check that nxwright writes the same TFT files as that release. Each probe is a small project. The probe tool compiles it with both the Nextion Editor and nxwright, and compares the two files.

Some probes also keep fixtures, so that nxwright's tests can make the same check without the Nextion Editor. These probes cut the Nextion Editor's file into pieces, such as one page's code, and save them in `tests/tft/fixtures/`. The tests then compare the compile's output with these pieces.

The probe tool is for contributors who have the Nextion Editor. It drives the Nextion Editor through the [Editor tool](../editor/README.md), so it needs Windows and the Editor tool's Python.

To use it, set `NXWRIGHT_EDITOR_NAME` to a name for the [dedicated Editor](../editor/README.md) it will drive, then run every command from nxwright's folder with that Python. This command runs one module of probes:

```
tools\editor\build\venv\Scripts\python.exe -m tools.tft.probe run first_probes
```

Later commands on this page shorten that path to `python`.

Run `python -m tools.tft.probe --help` for the list of commands, and see the docstring of `tools/tft/probe.py` for what each one does. The tool writes what it builds, and the files it keeps, into `tools/tft/build/`.

## Moving to a new release of the Nextion Editor

The weekly release check reports each new release of the Nextion Editor, with its release notes (`tools/editor/latest_release.py`). The probes then show where nxwright's TFT files differ from the new release's. Once nxwright is fixed and every probe you ran matches, nxwright moves to the new release.

### Before you start

1. Download the new release's zip. Nextion serves it at a predictable address, such as `https://nextion.tech/download/nextion-setup-v1-68-2.zip`.
2. Unpack the zip into a new folder. Do not install the new release.
3. Set `NXWRIGHT_EDITOR` to the unpacked `Nextion Editor.exe`, and `NXWRIGHT_EDITOR_NAME` to a new name for its [dedicated Editor](../editor/README.md), such as `release-1691`. The probes will then drive the new release, and nxwright's compile will read its firmware from the new release's folder.

### Three ways to run the probes

Start with the release sample, and run a larger set only if the release reaches further. To run a single module, give its name in place of `release_sample`.

- **The release sample.** On each series, it covers every command, system variable, colour, and component type, plus the layouts, the timers, and the resources (`tools/tft/probing/release_sample.py`). Against the Nextion Editor 1.68.2, its 43 probes took about 10 minutes.

  ```
  python -m tools.tft.probe run release_sample --again
  ```

- **The probes that keep fixtures**, about 700. Run them when the sample or the release notes point at many [areas](#areas), the subjects that the probes cover.

  ```
  python -m tools.tft.probe run --fixtures
  ```

- **Every probe that compares with nxwright's compile**, about 4,000 from all the modules. Run them when a change could reach every part of a file.

  ```
  python -m tools.tft.probe run --all
  ```

Each run lists, by module, the probes that did not match and the probes that could not run.

- For a probe that did not match, the run keeps the new release's file as `tools/tft/build/kept/<probe>.tft`.
- A probe cannot run when the Nextion Editor refuses its project, or when the new release's folder lacks a firmware file that the probe's series needs.
- When a probe that keeps fixtures matches the new release, it writes its fixtures again, so that nxwright's tests compare with the new release's bytes.

### The steps

1. Read the release notes that the check printed. Find each area they mention, such as the timers or a component type, in the [list of areas](#areas).
2. Run the release sample, then the probe modules of each area the notes mention, each with `--again` so that probes already matched run again. When the release has no notes, or the notes mention no area, run the sample alone.
3. Where a probe does not match, run every probe module of its area too. File each probe that does not match or could not run as a bug, and fix the bugs.
4. Once the sample and every module you ran match the new release, put the new release in place of the old one in `nxwright/tft/firmware_versions.py`:
   - In `MATCHED_VERSIONS`, give the SHA-256 hash of each firmware file, read from the new release's zip.
   - In `INSTALLER_HASHES`, give the hash of the new release's installer. nxwright's firmware download runs only an installer whose hash is listed here. Download the installer, at the address of the zip with `.exe` in place of `.zip`, only to get this hash, and never run it yourself.
5. Move the rest of nxwright to the new release in the same change. See [tools/editor/RELEASES.md](../editor/RELEASES.md) for how.

After the move, the compile takes only the new release's firmware. A user who has only the old release's firmware is offered the download of the new one, like a user who has no firmware.

## Areas

An area is a subject that the probes cover. All the modules below are in `tools/tft/probing/`.

| Area | Probe modules |
| --- | --- |
| The whole compile, the layouts, and the headers | `compile_probes`, `first_probes`, `frame_probes`, `packaging_probes`, `page_probes`, `page_place_probes`, `entry_limit_probes`, `room_probes`, `text_room_probes` |
| Device settings, screen models, rotations, and encodings | `device_setting_probes`, `model_probes`, `rotation_probes`, `encoding_probes`, `text_character_probes` |
| Animations, videos, and sounds | `media_probes`, `resampled_sound_probes` |
| Statements, operands, and attributes in code | `statement_probes`, `command_operand_probes`, `hex_number_probes`, `indirect_probes`, `code_form_probes`, `text_assignment_probes`, `attribute_probes`, `other_attribute_probes`, `other_page_probes`, `key_probes` |
| Control statements and macros | `if_probes`, `while_probes`, `for_probes`, `goto_probes`, `condition_probes`, `text_condition_probes`, `macro_probes` |
| Commands | `release_command_probes`, `crc_command_probes`, `device_and_buffer_command_probes`, `drawing_probes`, `eeprom_and_gpio_probes`, `page_command_probes`, `pinyin_probes`, `screen_command_probes`, `serial_command_probes`, `text_command_probes`, `undocumented_command_probes`, `waveform_command_probes` |
| Timers | `timer_probes` |
| A component type | its own module, such as `text_probes` or `gmov_probes`. The text, the number, and the button also have others, such as `text_border_and_picture_probes`. |
| Attributes that every component has, and components that overlap | `shared_attribute_probes`, `overlap_probes` |
| One series alone | `k_probes`, `p_probes`, `e_probes`, or `f_probes` |

The compiler was built on the T series first, so the T series' probes are in each area's modules. The series come in two families, each with a base set of probes for a base series, called the leader. T leads K and F, and P leads E. A follower writes a project's code as its leader does, apart from a few differences. The K, F, and P modules each run T's probes on their own series, and add their own, and the E module runs P's. Run a series' module when a change concerns that series.
