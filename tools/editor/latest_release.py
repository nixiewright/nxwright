"""Says whether Nextion offers a newer Nextion Editor than the one nxwright
is tested with (tested_editor.toml).

    python tools/editor/latest_release.py

Run it with nxwright's own Python. It asks Nextion's server which release
is the newest, as the Nextion Editor's own check for a newer version does
(ResearchNotes/editor-version-check.md). It sends the tested version as
`dver`, as the Editor sends its own: a request without it once got 1.68
rather than 1.68.2, though whether that came from leaving `dver` out was
not tried again. It sends no identifier of the computer.

The answer is a series of fields, each starting with &*@, then its name,
=, and its value. `ver` gives the newest version, `exeadd` its installer's
address, whose file name gives the version again, and `uptext` the release
notes, which may run over several lines. Both `ver` and `exeadd` must give
the same version, so that a change to the answer's form is reported, not
taken for "no new release".

It prints what it found, with the release notes when the release is new,
and exits with:
  - 0 when Nextion offers the tested version;
  - 1 when it offers another;
  - 2 when the server cannot be reached, or its answer does not give a
    version both ways.
"""
from pathlib import Path
import re
import sys
import tomllib
import urllib.error
import urllib.request

TESTED_FILE = Path(__file__).resolve().with_name("tested_editor.toml")
# The address of the Editor's check for a newer version, given the version
# asking.
VERSION_CHECK = "https://nextion.tech/ver/ver.php?state=0&dver=%s"
# Nextion's server refuses Python's own User-Agent (403 Forbidden), so the
# request names nxwright.
USER_AGENT = "nxwright"
# How long the server may take to answer, in seconds.
ANSWER_WAIT = 30
_FIELD_START = "&*@"
_VERSION = re.compile(r"\d+\.\d+\.\d+")
_INSTALLER = re.compile(r"nextion-setup-v(\d+)-(\d+)-(\d+)\.exe")


def tested_version() -> str:
    """Returns the version nxwright is tested with, as tested_editor.toml
    records it, such as "1.68.2"."""
    return tomllib.loads(TESTED_FILE.read_text(encoding="utf-8"))["version"]


def check(text: str, tested: str) -> tuple:
    """Returns (the exit code, what to print) for Nextion's answer `text`,
    decoded, given the `tested` version."""
    fields = _fields(text)
    version = fields.get("ver", "").strip()
    installer = _INSTALLER.search(fields.get("exeadd", ""))
    if not _VERSION.fullmatch(version) or installer is None:
        return 2, ("Nextion's answer could not be read: it gives no version in `ver` and in "
                   "its installer's name in `exeadd`.")
    if ".".join(installer.groups()) != version:
        return 2, ("Nextion's answer could not be read: `ver` gives %s, but the installer's "
                   "name gives %s." % (version, ".".join(installer.groups())))
    if version == tested:
        return 0, ("Nextion offers the Nextion Editor %s, the version nxwright is tested with."
                   % version)
    notes = fields.get("uptext", "").replace("\r\n", "\n").strip()
    return 1, ("Nextion offers the Nextion Editor %s; nxwright is tested with %s.%s"
               % (version, tested, " Its release notes:\n" + notes if notes
                  else " Its answer gives no release notes."))


def _fields(text: str) -> dict:
    """Returns {name: value} of the fields of Nextion's answer `text`. A
    part without = is passed over, as are the byte order marks before the
    first field."""
    fields = {}
    for part in text.split(_FIELD_START)[1:]:
        name, equals, value = part.partition("=")
        if equals:
            fields[name] = value
    return fields


def main() -> int:
    # Nextion's release notes, and the network's errors, may hold characters
    # Windows' console cannot encode.
    sys.stdout.reconfigure(encoding="utf-8")
    tested = tested_version()
    request = urllib.request.Request(VERSION_CHECK % tested, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=ANSWER_WAIT) as response:
            text = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as error:
        print("Nextion's server could not be reached: %s" % error)
        return 2
    code, said = check(text, tested)
    print(said)
    return code


if __name__ == "__main__":
    sys.exit(main())
