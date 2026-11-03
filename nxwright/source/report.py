"""The report that `nxwright report` writes. The report lists the things
in a project file that nxwright does not know (unknown_content.py). It gives
nxwright's maintainers enough detail to look into them, without the
project's own content.

The report contains:

- the versions of nxwright, Python, and Windows;
- the project file's blocks, by name and size;
- the manifest header, with the password's hash blanked;
- the device settings that nxwright reads from the manifest header;
- for each unknown thing: where it is, its sort (content_sorts.py), its
  size, and at most its first 16 bytes.

The report gives the place of an unknown thing by a block's name, an
object's index, or an attribute's name, never by the name of a page or a
component. The first bytes of a thing may contain some of the project's
texts, and a warning at the top of the report points this out. The report
leaves blanks for the user to fill in: the Nextion Editor's version, and
what the user did in the Nextion Editor. It leaves out the project's code, texts, names
of pages or components, pictures, fonts, and sounds.
"""
from pathlib import Path
import platform
import sys
import tomllib

from nxwright import NxwrightError, installed_version
from nxwright.project.container import HmiContainer
from nxwright.project.device_settings import NO_PASSWORD, read_device_settings
from nxwright.project.resources import parse_manifest
from nxwright.source.unknown_content import unknown_in_project_file

# The path of nxwright's pyproject.toml when nxwright runs from a copy of its
# source. The file is beside the package's folder.
_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
# The number of bytes the report shows of each unknown thing.
SHOWN_BYTES = 16
# The places of the password's hash in the manifest header (device_settings.py).
# The report blanks these bytes.
_PASSWORD_BYTES = range(20, 24)


def write_report(project: Path, output: Path):
    """Writes the report of `project` to `output`, which must not exist
    yet. Raises NxwrightError if `output` already exists. Reading the
    project can raise errors too."""
    text = report_text(project)
    try:
        with open(output, "x", encoding="utf-8", newline="\n") as file:
            file.write(text)
    except FileExistsError:
        raise NxwrightError("%s already exists; nothing was written" % output) from None


def report_text(project: Path) -> str:
    """Returns the report of the project file `project`, in Markdown."""
    blocks = HmiContainer.from_file(project).blocks
    manifest = parse_manifest(blocks["main.HMI"])
    header = blocks["main.HMI"][:manifest.header_size]
    found = unknown_in_project_file(Path(project))
    lines = [
        "# nxwright report",
        "",
        "This report gives the things in a project file that nxwright does not know, so that "
        "nxwright's maintainers can look into them. The project's code, texts, names of pages "
        "or components, pictures, fonts, animations, videos, and sounds are left out. The "
        "project's password is left out too, and the report gives only whether the project "
        "has one.",
        "",
        "For each thing nxwright does not know, the report gives at most its first %d bytes, "
        "which may contain some of the project's texts. Read the report before you send it."
        % SHOWN_BYTES,
        "",
        "## Versions",
        "",
        "- nxwright: %s" % _nxwright_version(),
        "- Python: %s" % platform.python_version(),
        "- Windows: %s" % (platform.platform() if sys.platform == "win32" else "not Windows, %s"
                           % platform.platform()),
        "- The Nextion Editor: _fill in the version from its Help menu_",
        "",
        "## What you did",
        "",
        "_Fill in what you did in the Nextion Editor before you saved the project._",
        "",
        "## What nxwright does not know",
        "",
    ]
    if found:
        lines += ["| What | Where | Kept by nxwright | Bytes | First bytes |",
                  "| --- | --- | --- | --- | --- |"]
        lines += ["| %s | %s | %s | %d | %s |" % (each.what, each.where, each.sort,
                                                  len(each.data), _hex(each.data[:SHOWN_BYTES]))
                  for each in found]
    else:
        lines.append("nxwright knows everything in this project.")
    lines += ["", "## The project file's blocks", "", "| Block | Bytes |", "| --- | --- |"]
    lines += ["| %s | %d |" % (name, len(block)) for name, block in blocks.items()]
    lines += ["", "## The manifest header", "", "```", _blanked_hex(header), "```", "",
              "`--` marks the bytes of the password's hash, which are left out.", ""]
    lines += _settings_lines(header)
    return "\n".join(lines) + "\n"


def _nxwright_version() -> str:
    """Returns nxwright's version. That is the installed package's version
    or, when nxwright runs from a copy of its source, the version in its
    pyproject.toml."""
    installed = installed_version()
    if installed is not None:
        return installed
    try:
        with open(_PYPROJECT, "rb") as file:
            return "%s, from source" % tomllib.load(file)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "from source, of an unknown version"


def _hex(data: bytes) -> str:
    """Returns `data` as hexadecimal, with a space between bytes."""
    return " ".join("%02x" % byte for byte in data)


def _blanked_hex(header: bytes) -> str:
    """Returns the manifest header as hexadecimal, 16 bytes on each line,
    with each byte of the password's hash shown as --."""
    shown = ["--" if place in _PASSWORD_BYTES else "%02x" % byte
             for place, byte in enumerate(header)]
    return "\n".join(" ".join(shown[start:start + 16]) for start in range(0, len(shown), 16))


def _settings_lines(header: bytes) -> list:
    """Returns the report's lines on the device settings that nxwright reads
    from the manifest header. If nxwright reads none, the lines give the
    reason."""
    # The password's hash is in the same bytes for every screen model.
    password = ("- Password: %s" % ("yes" if header[20:24] != NO_PASSWORD else "no")
                if len(header) >= 24 else "- Password: not known, as the header is short")
    try:
        settings = read_device_settings(header)
    except NxwrightError as error:
        return ["The device settings could not be read: %s." % error, "", password]
    if settings is None:
        return ["The screen model is not one nxwright knows, so it reads no other device "
                "settings.", "", password]
    return ["- Screen: %s" % settings.model.name,
            "- Rotation: %d" % settings.rotation,
            "- Encoding: %s" % settings.encoding,
            password]
