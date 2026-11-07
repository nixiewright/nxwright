"""A stand-in for what the search for firmware reads (tft/firmware.py), so
that a test needs neither the vendor's firmware nor the user's real cache,
nor the Nextion Editor installed on the computer running it.

The stand-in's matched version is 1.68.2, and its hashes are those of the
made-up firmware files of made_tft.py. Each file name has the same made-up
bytes in every series, as each has one file in a Nextion Editor's folder.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
from unittest import mock

from nxwright.tft import firmware, firmware_versions
from nxwright.tft.tft_file import SERIES
from tests.tft.made_tft import made_tft

STAND_IN_VERSION = (1, 68, 2)


def made_firmware_files() -> dict:
    """Returns the made-up firmware files of every series, by name."""
    files = {}
    for series in SERIES.values():
        files.update(firmware.firmware_from_tft(made_tft(series), "made.tft", series).files)
    return files


def write_editor_folder(folder: Path) -> Path:
    """Writes the made-up firmware files of every series into `folder`, as a
    Nextion Editor folder has them, and returns `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in made_firmware_files().items():
        (folder / name).write_bytes(data)
    return folder


@contextmanager
def stand_in_firmware(cache: Path = None, installed: Path = None,
                      installed_version: tuple = STAND_IN_VERSION):
    """While it lasts, the only matched version is 1.68.2, with the hashes of
    made_tft's firmware files. NXWRIGHT_CACHE names `cache`, or turns the
    cache off when `cache` is None. The installed Nextion Editor is the
    folder `installed`, of `installed_version`, or there is none when
    `installed` is None."""
    hashes = {name: hashlib.sha256(data).hexdigest()
              for name, data in made_firmware_files().items()}
    environment = {"NXWRIGHT_CACHE": str(cache) if cache is not None else "off"}
    with mock.patch.object(firmware_versions, "MATCHED_VERSIONS", {STAND_IN_VERSION: hashes}), \
            mock.patch.dict(os.environ, environment), \
            mock.patch.object(firmware, "installed_editor_folder", lambda: installed), \
            mock.patch.object(firmware, "program_version",
                              lambda program: tuple(installed_version) + (0,)):
        yield
