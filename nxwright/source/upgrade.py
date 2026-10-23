"""Converting a source folder to the current format.

A source folder's app.toml names the format its files are in (`format = 1`).
When a version of nxwright changes the format, it adds a migration step: a
function that converts a folder in place from one format to the next, and
ends by writing the new format number into app.toml. upgrade runs every step
from the folder's format to the current one, so a folder from any earlier
version can be brought up to date. Once a step is released, it is never
removed.

The current format is the first: no step exists yet. The first change of
the layout after nxwright's launch adds the first one.
"""
from pathlib import Path
import tomllib

from nxwright import NxwrightError
from nxwright.source.source_folder import SOURCE_FORMAT


# The migration steps: MIGRATIONS[n] converts a folder from format n to n + 1.
MIGRATIONS = {}


def folder_format(source_folder: Path) -> int:
    """Returns the format number in the folder's app.toml. Raises
    NxwrightError when app.toml is missing, is not TOML, or has no number."""
    path = Path(source_folder) / "app.toml"
    try:
        found = tomllib.loads(path.read_text(encoding="utf-8-sig")).get("format")
    except OSError as error:
        raise NxwrightError("%s: %s" % (path, error.strerror)) from None
    except tomllib.TOMLDecodeError as error:
        raise NxwrightError("%s: %s" % (path, error)) from None
    # TOML's true is Python's True, which equals 1: only a real number counts.
    if not isinstance(found, int) or isinstance(found, bool) or found < 1:
        raise NxwrightError("%s: format must be a number from 1" % path)
    return found


def upgrade(source_folder: Path) -> list:
    """Converts `source_folder` in place to the current format, one step at a
    time. Returns the formats it went through, after the first; an empty list
    when the folder was already current.

    Raises NxwrightError for a folder in a newer format than this nxwright
    reads, and when a step is missing or leaves the format unchanged.
    """
    found = folder_format(source_folder)
    if found > SOURCE_FORMAT:
        raise NxwrightError("%s is in source format %d, which needs a newer nxwright; this "
                            "one reads format %d" % (source_folder, found, SOURCE_FORMAT))
    reached = []
    while found < SOURCE_FORMAT:
        step = MIGRATIONS.get(found)
        if step is None:
            raise NxwrightError("no step converts source format %d to %d" % (found, found + 1))
        step(Path(source_folder))
        after = folder_format(source_folder)
        if after != found + 1:
            raise NxwrightError("the step from source format %d left the folder in format %d"
                                % (found, after))
        found = after
        reached.append(found)
    return reached
