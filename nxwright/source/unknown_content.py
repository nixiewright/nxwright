"""Finds what a project holds that nxwright does not know: a block of
another kind, a manifest entry or header byte it does not expect, a
picture's header the build would write otherwise, a screen model or a
character encoding it has no entry for, and a component type or an
attribute its tables do not name. A newer Nextion Editor may write any of
them.

Each is sorted one of three ways, by what the source folder does with it:
  - kept exactly: the source folder holds it, and the build writes it back
    unchanged, as a component type nxwright does not know;
  - may be lost: the source folder does not hold it, so the build leaves it
    out or writes the value nxwright knows instead;
  - cannot be kept: the source folder cannot hold the project around it
    without guessing.

Extract, the dump command, and the report all ask this module, so they
agree. Its checks of a page's attributes are the tests the page files'
conversion makes (page_source.py), so the two cannot disagree either.
"""
from dataclasses import dataclass
from pathlib import Path

from nxwright import NxwrightError
from nxwright.project.container import HmiContainer, numbered_block
from nxwright.project.device_settings import ENCODINGS, HEADER_SIZE
from nxwright.project.dump_folder import dump_header_bytes, dump_manifest_header, page_text_files
from nxwright.project.dumper import handles_block
from nxwright.project.object_types import TYPE_NAMES
from nxwright.project.page_block import Attribute, parse_page
from nxwright.project.page_text import expected_width, is_string_attribute, page_from_text
from nxwright.project.resources import (LISTED_IN_ORDER, encode_image_source,
                                        parse_image_source, parse_manifest)
from nxwright.project.screen_models import model_with_id
from nxwright.source.page_source import reference_kind

KEPT, MAY_BE_LOST, CANNOT_BE_KEPT = "kept exactly", "may be lost", "cannot be kept"
# Where an unknown screen model is, by which extract tells it from the rest.
UNKNOWN_MODEL_PLACE = "manifest header, bytes 16 to 19"

# The manifest header's bytes the build writes as constants
# (device_settings.manifest_header), by place, in the current form. The
# older form, which projects saved by an older Nextion Editor hold, has
# other values at three of them; the build turns it into the current one.
_CURRENT_FORM = {8: 0x01, 9: 0x44, 10: 0x21, 14: 0x4f, 36: 2, 65: 3}
_OLDER_FORM = {**_CURRENT_FORM, 9: 0x43, 36: 1, 65: 2}
# The places of the bytes that hold the device settings, the header's own
# size and the table's place, the resource count, and the stamp. Every other
# byte, but the constants above, the build writes as 0.
_SETTINGS_BYTES = frozenset(list(range(0, 8)) + [11, 12, 13, 15] + list(range(16, 36))
                            + [38, 39])


@dataclass(frozen=True)
class UnknownContent:
    """One thing a project holds that nxwright does not know: what it is,
    in a few words; where it is, by a block's name, or a page's block and
    an object's index, never by a name of the user's; its bytes; and how it
    is sorted, KEPT, MAY_BE_LOST, or CANNOT_BE_KEPT."""
    what: str
    where: str
    data: bytes
    sort: str


def unknown_in_project_file(project: Path) -> list:
    """Returns the UnknownContent of the project file `project`, which is
    only read."""
    blocks = HmiContainer.from_file(project).blocks
    manifest = parse_manifest(blocks["main.HMI"])
    pages = {"block %s" % name: parse_page(blocks[name]) for name in manifest.block_names("pa")}
    return unknown_in_project(blocks, manifest, pages)


def unknown_in_project(blocks: dict, manifest, pages: dict) -> list:
    """Returns the UnknownContent of a project file: of its live blocks,
    `blocks`, {name: bytes}; of its parsed manifest, `manifest`; and of its
    pages, {block name: PageBlock}."""
    header = blocks["main.HMI"][:manifest.header_size]
    return (unknown_in_blocks(blocks) + unknown_in_manifest_entries(manifest)
            + unknown_in_manifest_header(header) + unknown_in_picture_headers(blocks)
            + unknown_in_pages(pages))


def unknown_in_blocks(blocks: dict) -> list:
    """Returns each block of a kind nxwright does not handle, which the
    build leaves out."""
    return [UnknownContent("a block of a kind nxwright does not handle", "block %s" % name,
                           data, MAY_BE_LOST)
            for name, data in blocks.items() if not handles_block(name)]


def unknown_in_manifest_entries(manifest) -> list:
    """Returns each entry of the manifest's list of a kind nxwright does
    not know, which the build leaves out."""
    return [UnknownContent("a manifest entry of a kind nxwright does not know",
                           "manifest entry %d" % index,
                           kind.encode("latin-1") + b"\0" + name.encode("latin-1"), MAY_BE_LOST)
            for index, (kind, name) in enumerate(manifest.resources)
            if kind not in LISTED_IN_ORDER]


def unknown_in_manifest_header(header: bytes) -> list:
    """Returns what the manifest header `header` holds that nxwright does
    not know: a header of another size, or a character encoding it does not
    know, which it cannot keep; a screen model it does not know; and bytes
    the build writes as constants that hold other values, unless the header
    is the older form as a whole. Those last two may be lost."""
    if len(header) != HEADER_SIZE:
        return [UnknownContent("a manifest header of %d bytes, not %d" % (len(header), HEADER_SIZE),
                               "manifest header", header[:16], CANNOT_BE_KEPT)]
    found = []
    if header[13] not in ENCODINGS:
        found.append(UnknownContent("a character encoding nxwright does not know",
                                    "manifest header, byte 13", header[13:14], CANNOT_BE_KEPT))
    if model_with_id(header[16:20]) is None:
        found.append(UnknownContent("a screen model nxwright does not know: app.toml gets no "
                                    "screen settings, and the build refuses the folder until "
                                    "nxwright knows the model",
                                    UNKNOWN_MODEL_PLACE, header[16:20],
                                    MAY_BE_LOST))
    if not _is_form(header, _OLDER_FORM):
        expected = {place: _CURRENT_FORM.get(place, 0) for place in range(HEADER_SIZE)
                    if place not in _SETTINGS_BYTES}
        found += [UnknownContent("a manifest header byte the build writes as %d" % value,
                                 "manifest header, byte %d" % place, header[place:place + 1],
                                 MAY_BE_LOST)
                  for place, value in expected.items() if header[place] != value]
    return found


def _is_form(header: bytes, form: dict) -> bool:
    """Whether every byte the build writes as a constant holds `form`'s
    value, or 0 where `form` gives none."""
    return all(header[place] == form.get(place, 0) for place in range(HEADER_SIZE)
               if place not in _SETTINGS_BYTES)


def unknown_in_picture_headers(blocks: dict) -> list:
    """Returns each picture's file (".is" block) whose header differs from
    the one the build writes for it, which the build would write instead."""
    found = []
    for name, block in blocks.items():
        if numbered_block(name, "is") is None:
            continue
        source = parse_image_source(block)
        size = len(block) - len(source.data)
        if block[:size] != encode_image_source(source)[:size]:
            found.append(UnknownContent("a picture's header that differs from the build's",
                                        "block %s" % name, block[:size], MAY_BE_LOST))
    return found


def unknown_in_pages(pages: dict) -> list:
    """Returns, of the pages {where each is: PageBlock}, such as "block
    0.pa", each component type
    nxwright does not know, which the source folder keeps exactly; and each
    attribute its tables give no width, or another width than the one
    stored, which it cannot keep."""
    found = []
    for page_place, page in pages.items():
        for index, page_object in enumerate(page.objects):
            object_type = page_object.attribute("type")[0]
            where = "%s, object %d" % (page_place, index)
            if object_type not in TYPE_NAMES:
                found.append(UnknownContent("a component type nxwright does not know", where,
                                            bytes([object_type]), KEPT))
            for item in page_object.items:
                if isinstance(item, Attribute):
                    found += _unknown_attribute(item, object_type, where)
    return found


def _unknown_attribute(attribute: Attribute, object_type: int, where: str) -> list:
    """Returns the attribute `attribute` of an object of type `object_type`
    when the page files' conversion cannot keep it: one with no width, or
    another width than stored, as page_source._attribute_to_value tests."""
    if is_string_attribute(object_type, attribute.name):
        return []
    width = expected_width(object_type, attribute.name)
    where = "%s, attribute %s" % (where, attribute.name)
    type_name = TYPE_NAMES.get(object_type, "type %d" % object_type)
    # The page file keeps either as its stored bytes, in its raw form
    # (page_source.RAW_KEY).
    if width is None:
        return [UnknownContent("an attribute nxwright does not know, %s, on a %s, kept as its "
                               "stored bytes" % (attribute.name, type_name), where,
                               attribute.value, KEPT)]
    if width != len(attribute.value):
        # Its bytes keep a picture's or a font's ID, not its name.
        by_id = (", which keep a resource's ID, right only while the resources keep their order"
                 if reference_kind(object_type, attribute.name) else "")
        return [UnknownContent("an attribute stored in %d bytes, where nxwright knows %d, "
                               "%s, on a %s, kept as its stored bytes%s"
                               % (len(attribute.value), width, attribute.name, type_name,
                                  by_id), where, attribute.value, KEPT)]
    return []


class UnknownContentError(NxwrightError):
    """Content that nxwright does not know and that the next build may lose,
    `found`, a list of UnknownContent, which nobody chose to go on past. It
    is told apart from other refusals so that a command can ask the user
    whether to go on."""

    def __init__(self, origin: Path, found: list, project: Path = None,
                 removed_settings: Path = None):
        """`origin` is the project file or the dump that holds `found`, and
        `project` the project file, when known, which `nxwright report`
        reads. `removed_settings` is the source folder whose app.toml's
        screen settings going on would remove, as the project's screen
        model is one nxwright does not know, or None."""
        self.found = found
        removal = ("" if removed_settings is None else
                   "Going on removes the screen settings of %s.\n"
                   % (Path(removed_settings) / "app.toml"))
        super().__init__(
            "%s holds what nxwright does not know, which the next build may lose:\n%s\n%s"
            "The project may then miss parameters the Nextion Editor needs, and may not come "
            "back the same from the Nextion Editor. %s"
            % (origin, listed(found), removal, report_hint(project)))


def report_hint(project: Path = None) -> str:
    """Returns the sentence that points the user at `nxwright report`, for
    the project file `project` when it is known."""
    named = "the project file" if project is None else str(project)
    return ("`nxwright report` with %s writes a report of it to send to nxwright's "
            "maintainers." % named)


def listed(found: list) -> str:
    """Returns each UnknownContent of `found` as a line of a list."""
    return "\n".join("  - %s (%s)" % (each.what, each.where) for each in found)


def checked(origin: Path, found: list, continue_with_unknown: bool, project: Path = None,
            removed_settings: Path = None) -> list:
    """Applies the rule to `found`, the UnknownContent of `origin`: raises
    NxwrightError for content nxwright cannot keep, and UnknownContentError
    for content the next build may lose, unless `continue_with_unknown`.
    Otherwise returns a note of each content kept exactly, and a warning of
    each gone past. `project` and `removed_settings` are UnknownContentError's."""
    cannot = [each for each in found if each.sort == CANNOT_BE_KEPT]
    if cannot:
        raise NxwrightError("%s holds what nxwright cannot keep:\n%s\nA newer Nextion Editor "
                            "may have added it. %s" % (origin, listed(cannot),
                                                       report_hint(project)))
    lost = [each for each in found if each.sort == MAY_BE_LOST]
    if lost and not continue_with_unknown:
        raise UnknownContentError(origin, lost, project, removed_settings)
    notes = ["%s (%s), which the source folder keeps exactly" % (each.what, each.where)
             for each in found if each.sort == KEPT]
    if notes:
        # Content kept exactly is still to be supported properly later, so
        # the user is pointed at the report to send.
        notes.append(report_hint(project))
    return notes + ["went on past %s (%s), which the next build may lose"
                    % (each.what, each.where) for each in lost]


def unknown_in_dump(dump_folder: Path) -> list:
    """Returns the UnknownContent of a dump that its files show: of its
    manifest header, which project.txt shows, and of its pages. A dump
    leaves out the blocks of other kinds, the manifest's list, and the
    pictures' headers, which `nxwright dump` warned of."""
    shown = dump_header_bytes(dump_folder)
    header = dump_manifest_header(dump_folder)
    if shown is None:
        # A dump written from a source folder shows no header to check.
        found = []
    elif header is None:
        found = [UnknownContent("a manifest header of another size than %d bytes" % HEADER_SIZE,
                                "manifest header", shown[:16], CANNOT_BE_KEPT)]
    else:
        found = unknown_in_manifest_header(header)
    pages = {"page file %s" % path.name: page_from_text(path.read_text(encoding="utf-8"))
             for _, path in sorted(page_text_files(dump_folder).items())}
    return found + unknown_in_pages(pages)
