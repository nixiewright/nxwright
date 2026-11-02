"""The report `nxwright report` writes: the things in a project file that
nxwright does not know (unknown_content.py), with enough detail for
nxwright's maintainers to look into them, and none of the project's own
content.

It gives nxwright's, Python's, and Windows' versions, the project file's
blocks by name and size, its manifest header with the password's hash
blanked, the device settings nxwright reads from it, and each unknown
content: where it is, by a block's name, an object's index, or an
attribute's name, never a page's or a component's; how it is sorted; its
size; and at most its first 16 bytes, which may contain a text of the
project's, as its first lines warn. It leaves blanks for the user: the
Nextion Editor's version, and what they did in it. It leaves out the
project's code, texts, names of pages or components, pictures, fonts, and
sounds.
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

# nxwright's pyproject.toml, beside its package, in a copy of its source.
_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
# How many of each unknown content's bytes the report gives.
SHOWN_BYTES = 16
# The bytes of the manifest header that contain the password's hash, which the
# report blanks (device_settings.py).
_PASSWORD_BYTES = range(20, 24)


def write_report(project: Path, output: Path):
    """Writes the report of `project` to `output`, a file that does not
    exist yet. Raises NxwrightError when it does, and as reading the
    project does."""
    text = report_text(project)
    try:
        with open(output, "x", encoding="utf-8", newline="\n") as file:
            file.write(text)
    except FileExistsError:
        raise NxwrightError("%s exists already; nothing was written" % output) from None


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
        "which may contain a text of the project's. Read the report before you send it."
        % SHOWN_BYTES,
        "",
        "## Versions",
        "",
        "- nxwright: %s" % _nxwright_version(),
        "- Python: %s" % platform.python_version(),
        "- Windows: %s" % (platform.platform() if sys.platform == "win32" else "not Windows, %s"
                           % platform.platform()),
        "- The Nextion Editor: _fill in the version its Help menu gives_",
        "",
        "## What you did",
        "",
        "_Fill in what you did in the Nextion Editor before you saved the project._",
        "",
        "## What nxwright does not know",
        "",
    ]
    if found:
        lines += ["| What | Where | Sorted | Bytes | First bytes |",
                  "| --- | --- | --- | --- | --- |"]
        lines += ["| %s | %s | %s | %d | %s |" % (each.what, each.where, each.sort,
                                                  len(each.data), _hex(each.data[:SHOWN_BYTES]))
                  for each in found]
    else:
        lines.append("nxwright knows everything in this project.")
    lines += ["", "## The project file's blocks", "", "| Block | Bytes |", "| --- | --- |"]
    lines += ["| %s | %d |" % (name, len(block)) for name, block in blocks.items()]
    lines += ["", "## The manifest header", "", "```", _blanked_hex(header), "```", ""]
    lines += _settings_lines(header)
    return "\n".join(lines) + "\n"


def _nxwright_version() -> str:
    """Returns nxwright's version: the installed package's, or else, for a
    copy of its source, the one its pyproject.toml gives."""
    installed = installed_version()
    if installed is not None:
        return installed
    try:
        with open(_PYPROJECT, "rb") as file:
            return "%s, from source" % tomllib.load(file)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "from source, of a version not known"


def _hex(data: bytes) -> str:
    """Returns `data` as hexadecimal, a byte apart from the next."""
    return " ".join("%02x" % byte for byte in data)


def _blanked_hex(header: bytes) -> str:
    """Returns the manifest header as hexadecimal, 16 bytes a line, with the
    password's hash blanked as --."""
    shown = ["--" if place in _PASSWORD_BYTES else "%02x" % byte
             for place, byte in enumerate(header)]
    return "\n".join(" ".join(shown[start:start + 16]) for start in range(0, len(shown), 16))


def _settings_lines(header: bytes) -> list:
    """Returns the lines that give the device settings nxwright reads from
    the manifest header, or why it reads none."""
    # The password's hash lies in the same bytes whatever the model.
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
