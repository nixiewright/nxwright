"""The report that `nxwright report` writes. The report lists the things
in a project file that nxwright does not know (unknown_content.py). It gives
nxwright's maintainers enough detail to look into them, without the
project's own content.

The report contains:

- the versions of nxwright, Python, and Windows;
- two blanks for the user to fill in: the Nextion Editor's version, and what
  the user did in the Nextion Editor;
- for each unknown thing: where it is, its sort (content_sorts.py), its
  size, and at most its first 16 bytes;
- the Nextion Editor's version that the manifest header and each page's
  header record (editor_version.py);
- the blocks that differ in a rebuild, with their sizes and where their
  bytes differ. A rebuild is the project file that nxwright builds from the
  folder it extracted the project into;
- the project file's blocks, by name and size;
- the manifest header, with the password's hash blanked;
- the device settings that nxwright reads from the manifest header.

The report leaves out the project's code, texts, names of pages or
components, pictures, fonts, and sounds. It gives the place of an unknown
thing by a block's name, an object's index, or an attribute's name, never by
the name of a page or a component. The rebuild's part gives where bytes
differ, and never the bytes. The first bytes of an unknown thing may still
contain some of the project's texts, and a warning at the top of the report
points this out.
"""
from collections import Counter
from pathlib import Path
import platform
import sys
import tempfile
import tomllib

from nxwright import NxwrightError, installed_version
from nxwright.project.byte_differences import (ADDED, REMOVED, compare_by_name,
                                               differing_ranges, ranges_text)
from nxwright.project.container import HmiContainer, numbered_block
from nxwright.project.device_settings import NO_PASSWORD, read_device_settings
from nxwright.project.editor_version import (CURRENT_VERSION, OLDEST_VERSION,
                                             is_checked_version, version_text)
from nxwright.project.page_block import parse_page
from nxwright.project.resources import parse_manifest
from nxwright.source.project_files import build, extract
from nxwright.source.unknown_content import unknown_in_project_file

# The path of nxwright's pyproject.toml when nxwright runs from a copy of its
# source. The file is beside the package's folder.
_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
# The number of bytes the report shows of each unknown thing.
SHOWN_BYTES = 16
# The places of the password's hash in the manifest header (device_settings.py).
# The report blanks these bytes.
_PASSWORD_BYTES = range(20, 24)
# The bytes in which the build always writes its own values, in the manifest
# and in a page: the stamp, in bytes 0 to 3, and the bytes that depend on the
# Nextion Editor's version. In the manifest, those are bytes 9, 36, and 65.
# In a page, they are bytes 41 to 43 (page_header.py).
_MANIFEST_BYTES_WRITTEN_ANEW = frozenset((0, 1, 2, 3, 9, 36, 65))
_PAGE_BYTES_WRITTEN_ANEW = frozenset((0, 1, 2, 3, 41, 42, 43))
# The most ranges of differing bytes that the report gives for one block.
_SHOWN_RANGES = 12


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
        "nxwright's maintainers can look into them. It also gives the Nextion Editor's version "
        "that the project file records, and the blocks that change when nxwright extracts the "
        "project and builds it again. The project's code, texts, names of pages or components, "
        "pictures, fonts, animations, videos, and sounds are left out. The project's password "
        "is left out too, and the report gives only whether the project has one.",
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
    lines += [""] + _version_lines(header, blocks, manifest)
    lines += [""] + _rebuild_lines(Path(project), blocks)
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


def _version_lines(header: bytes, blocks: dict, manifest) -> list:
    """Returns the report's lines on the Nextion Editor's version, as the
    project file records it (editor_version.py). `header` is the manifest
    header, `blocks` the file's live blocks, and `manifest` its parsed
    manifest. The lines give the version in the manifest header, then how
    many pages have each form of the page header's bytes 40 to 43."""
    lines = ["## The Nextion Editor's version in the project file", "",
             "From %s to %s, the Nextion Editor writes the second and third numbers of its "
             "version in the manifest header when it saves a project, and in a page's header "
             "when it writes that page. A page that it did not write keeps the version it had."
             % (version_text(*OLDEST_VERSION), version_text(*CURRENT_VERSION)), ""]
    if len(header) > 65:
        lines.append("- The manifest header: %s (bytes 9, 36, and 65 are `%s`)"
                     % (_version(header[9], header[36]),
                        _hex(bytes([header[9], header[36], header[65]]))))
    else:
        lines.append("- The manifest header is too short to give a version.")
    forms, unreadable = Counter(), 0
    for name in manifest.block_names("pa"):
        try:
            forms[bytes(parse_page(blocks[name]).unknown_40[:4])] += 1
        except NxwrightError:
            unreadable += 1
    lines += ["- %s: %s (page header bytes 40 to 43 are `%s`)"
              % (_counted(count, "page"), _version(form[1], form[2]), _hex(form))
              for form, count in sorted(forms.items())]
    if unreadable:
        lines.append("- %s that nxwright cannot read" % _counted(unreadable, "page"))
    return lines


def _version(second: int, third: int) -> str:
    """Returns the version with the numbers `second` and `third` as the
    report gives it. A version that nxwright was not checked with is marked
    as such, because its bytes may mean something else."""
    text = version_text(second, third)
    return text if is_checked_version(second, third) else (
        "%s, if these bytes still give the version" % text)


def _counted(count: int, noun: str) -> str:
    """Returns `count` and `noun`, with the noun in the plural unless the
    count is 1: "1 page", "3 pages"."""
    return "%d %s%s" % (count, noun, "" if count == 1 else "s")


def _rebuild_lines(project: Path, blocks: dict) -> list:
    """Returns the report's lines on what a rebuild changes. The function
    extracts `project` into a temporary folder, builds that folder again,
    and compares the result with `blocks`, the live blocks of `project`.

    The extract goes on past content that may be lost, which the report
    lists in another section. It also keeps each page's lock, so that the
    comparison shows only what nxwright does not give back. The build does
    not check the pages against the memory table, because only bytes are
    compared. If the extract or the build fails, the lines say so in fixed
    words, because the error's own text may contain a name from the
    project."""
    lines = ["## What a rebuild changes", ""]
    with tempfile.TemporaryDirectory() as name:
        folder, rebuilt = Path(name) / "folder", Path(name) / "rebuilt.HMI"
        try:
            extract(project, folder, continue_with_unknown=True,
                    keep_locks_without_password=True)
        except NxwrightError:
            return lines + ["nxwright could not extract this project, so there is no rebuild "
                            "to compare. Run `nxwright extract` to see the reason."]
        try:
            build(folder, rebuilt, refuse_by_table=False)
        except NxwrightError:
            return lines + ["nxwright extracted this project, but could not build the folder "
                            "again, so there is no rebuild to compare. Run `nxwright extract`, "
                            "then `nxwright build`, to see the reason."]
        return lines + comparison_lines(blocks, HmiContainer.from_file(rebuilt).blocks)


def comparison_lines(blocks: dict, rebuilt: dict) -> list:
    """Returns the report's lines on how `rebuilt`, the live blocks of a
    rebuild, differ from `blocks`, the live blocks of the project file. The
    lines count the blocks that are the same, and those that differ in the
    stamp and version bytes alone. They give each block that differs in a
    table: its size on each side, and where its bytes differ. They never
    give the bytes, which may be the project's own content."""
    made = ("nxwright extracted the project into a temporary folder, and built that folder "
            "again.")
    found = compare_by_name(blocks, rebuilt)
    if not found:
        return ["%s Every block of the project file, %d in all, is the same in this rebuild."
                % (made, len(blocks))]
    rows, same, only_anew = [], len(blocks), 0
    for each in found:
        if each.kind == ADDED:
            rows.append("| %s | not in the project file | %d | | |"
                        % (each.where, len(rebuilt[each.where])))
            continue
        same -= 1
        if each.kind == REMOVED:
            rows.append("| %s | %d | not in the rebuild | | |"
                        % (each.where, len(blocks[each.where])))
            continue
        anew, others = _ranges_apart(differing_ranges(each.runs), _written_anew(each.where))
        if not others:
            only_anew += 1
        rows.append("| %s | %d | %d | %s | %s |"
                    % (each.where, len(blocks[each.where]), len(rebuilt[each.where]),
                       ranges_text(anew) or "none", _ranges_cell(others)))
    return ["%s The table gives each block that differs between the project file and this "
            "rebuild, with where its bytes differ, and never the bytes themselves. The build "
            "always writes its own values for a block's stamp, in bytes 0 to 3, and for the "
            "bytes that depend on the Nextion Editor's version. The table lists those bytes in "
            "a column of their own." % made,
            "",
            "Of the project file's %s:" % _counted(len(blocks), "block"),
            "",
            "- The same in the rebuild: %d" % same,
            "- Different in the stamp and version bytes alone: %d" % only_anew,
            "- Different in other bytes, or not in the rebuild: %d"
            % (len(blocks) - same - only_anew),
            "",
            "| Block | Bytes in the project file | Bytes in the rebuild | Stamp and version "
            "bytes that differ | Other bytes that differ |",
            "| --- | --- | --- | --- | --- |"] + rows


def _written_anew(block: str) -> frozenset:
    """Returns the places of the bytes in which the build always writes its
    own values, in the block named `block`: the stamp and the version bytes
    of the manifest or of a page, and none in a block of another kind."""
    if block == "main.HMI":
        return _MANIFEST_BYTES_WRITTEN_ANEW
    return _PAGE_BYTES_WRITTEN_ANEW if numbered_block(block, "pa") is not None else frozenset()


def _ranges_apart(ranges: list, places: frozenset) -> tuple:
    """Splits the ranges of byte places `ranges` in two, and returns both
    as lists of ranges: the places that are in `places`, then the others.
    Each range is (its first place, its last place)."""
    inside, outside = [], []
    for first, last in ranges:
        start = first
        for place in sorted(place for place in places if first <= place <= last):
            if place > start:
                outside.append((start, place - 1))
            inside.append((place, place))
            start = place + 1
        if start <= last:
            outside.append((start, last))
    return inside, outside


def _ranges_cell(ranges: list) -> str:
    """Returns the table cell for the ranges of byte places `ranges`: how
    many bytes they cover, and at most _SHOWN_RANGES of them."""
    if not ranges:
        return "none"
    return "%s: %s" % (_counted(sum(last - first + 1 for first, last in ranges), "byte"),
                       ranges_text(ranges, most=_SHOWN_RANGES))


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
