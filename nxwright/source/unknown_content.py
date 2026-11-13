"""Finds the things in a project that nxwright does not know. A newer
Nextion Editor may write any of them:
  - a block of a kind nxwright does not handle;
  - a manifest entry or a manifest header byte that nxwright does not expect;
  - a picture's header that the build would write differently;
  - a resized picture's source that nxwright cannot keep;
  - a screen model or a character encoding that nxwright has no entry for;
  - a page that nxwright cannot read, such as one whose header has a
    size nxwright does not know;
  - a page header's value or form that nxwright has not seen;
  - a page whose text form does not give back its bytes;
  - a component type or an attribute that nxwright's tables do not list.

Each thing has one of four sorts, by what the source folder does with it:
  - kept exactly: the source folder keeps the thing, and the build writes
    it back unchanged. A component type nxwright does not know is an
    example.
  - written otherwise: the source folder keeps the thing in a form nxwright
    knows, and the build writes that form. For example, the build writes
    the current page header in place of a form not seen. Extract gives a
    warning for the change, and goes on without a question.
  - may be lost: the source folder does not keep the thing. The build
    leaves it out, or writes the value nxwright knows in its place, and the
    original value is lost. Extract prompts before it goes on.
  - cannot be kept: the source folder cannot keep the project around the
    thing without guessing. Extract refuses the project.

Extract, the dump command, and the report all use this module, so they
agree on what nxwright does not know. The module checks a page's
attributes with the same tests as the conversion of page files
(page_source.py), so those two cannot disagree either.
"""
from dataclasses import dataclass
from pathlib import Path

from nxwright import NxwrightError
from nxwright.project.container import HmiContainer, numbered_block
from nxwright.project.device_settings import ENCODINGS, HEADER_SIZE, TextCodec, encoding_name
from nxwright.project.dump_folder import dump_header_bytes, dump_manifest_header, page_text_files
from nxwright.project.dumper import handles_block, kept_picture_sources, page_text_difference
from nxwright.project.editor_version import CURRENT_VERSION, is_checked_version
from nxwright.project.object_types import TYPE_NAMES
from nxwright.project.page_block import Attribute, parse_page
from nxwright.project.page_header import (HEADER_21, SYSTEM_PAGES, header_40_form_known,
                                         header_44_known)
from nxwright.project.page_text import expected_width, is_string_attribute, page_from_text
from nxwright.project.pictures import picture_data_size
from nxwright.project.resources import (LISTED_IN_ORDER, SOURCE_EXTENSION, ImageSource,
                                        decodes_picture, encode_image_source, parse_image_source,
                                        parse_manifest)
from nxwright.project.screen_models import model_with_id
# Other modules import the sorts from this module.
from nxwright.source.content_sorts import CANNOT_BE_KEPT, KEPT, MAY_BE_LOST, WRITTEN_OTHERWISE
from nxwright.source.page_source import object_irregularities, reference_kind
# The place given for an unknown screen model.
UNKNOWN_MODEL_PLACE = "manifest header, bytes 16 to 19"

# The bytes of the manifest header that the build writes as constants
# (device_settings.manifest_header), by place. Bytes 9 and 36 are the second
# and third numbers of the Nextion Editor's version (editor_version.py).
CURRENT_FORM = {8: 0x01, 9: CURRENT_VERSION[0], 10: 0x21, 14: 0x4f, 36: CURRENT_VERSION[1],
                65: 3}
# The places of the version's two numbers among those constants.
_VERSION_BYTES = (9, 36)
# The values that byte 65 has in the projects of the Nextion Editors from
# 1.60.1 on: 0 up to 1.65.1, 2 in 1.67.1 and 1.68.1, and 3 in 1.68.2.
_KNOWN_BYTE_65 = (0, 2, 3)
# The places of the bytes that contain the device settings, the header's own
# size, the place of the table, the resource count, and the stamp. The build
# writes every other byte as 0, except for the constants above.
_SETTINGS_BYTES = frozenset(list(range(0, 8)) + [11, 12, 13, 15] + list(range(16, 36))
                            + [38, 39])


@dataclass(frozen=True)
class UnknownContent:
    """One thing in a project that nxwright does not know. `what` describes
    the thing in a few words. `where` gives its place, such as a block's
    name, or a page's block and an object's index, but never a name that the
    user chose. `data` is the thing's bytes. `sort` is KEPT,
    WRITTEN_OTHERWISE, MAY_BE_LOST, or CANNOT_BE_KEPT."""
    what: str
    where: str
    data: bytes
    sort: str


def unknown_in_project_file(project: Path) -> list:
    """Returns the UnknownContent of the project file `project`. The
    function only reads the file."""
    blocks = HmiContainer.from_file(project).blocks
    manifest = parse_manifest(blocks["main.HMI"])
    pages, unreadable = {}, []
    for name in manifest.block_names("pa"):
        try:
            pages[name] = parse_page(blocks[name])
        except NxwrightError:
            # List the page rather than raise, so that the report can
            # still be written. A newer Nextion Editor may store pages in a
            # form nxwright cannot read, and the report is how the user
            # tells nxwright's maintainers about it.
            # The report shows the page's first 16 bytes. They include the
            # header size, and stop before the page's name, because the
            # report never shows a name the user chose.
            unreadable.append(UnknownContent("a page nxwright cannot read",
                                             "block %s" % name, blocks[name][:16],
                                             CANNOT_BE_KEPT))
    return (unknown_in_project(blocks, manifest,
                               {"block %s" % name: page for name, page in pages.items()})
            + unreadable + unknown_in_page_texts({name: blocks[name] for name in pages}))


def unknown_in_page_texts(blocks: dict) -> list:
    """Returns the UnknownContent of the page blocks `blocks`, {name: bytes}.
    A page whose text form does not give back its bytes may be lost
    (dumper.page_text_difference). The dump would write that page from its
    text form, and nxwright does not know what the difference contains. A
    page that nxwright cannot write as text at all cannot be kept. The
    function lists that page rather than raising, so that the report and
    the error's list still show the other unknown content."""
    found = []
    for name, block in blocks.items():
        try:
            first = page_text_difference(block)
        except NxwrightError:
            # The description is fixed text, because the error may contain
            # the name of the page or of a component. The report never shows
            # those names.
            found.append(UnknownContent("a page nxwright cannot write as text",
                                        "block %s" % name, block[:16], CANNOT_BE_KEPT))
            continue
        if first is not None:
            found.append(UnknownContent("a page whose text form does not give back its bytes, "
                                        "from byte %d" % first, "block %s" % name,
                                        block[first:first + 16], MAY_BE_LOST))
    return found


def unknown_in_project(blocks: dict, manifest, pages: dict) -> list:
    """Returns the UnknownContent of a project file. `blocks` is the file's
    live blocks, {name: bytes}, and `manifest` its parsed manifest. `pages`
    maps the place of each page, such as "block 0.pa", to its PageBlock."""
    header = blocks["main.HMI"][:manifest.header_size]
    return (unknown_in_blocks(blocks) + unknown_in_manifest_entries(manifest)
            + unknown_in_manifest_header(header) + unknown_in_picture_headers(blocks)
            + unknown_in_picture_sources(blocks, manifest)
            + unknown_in_pages(pages, header[13] if len(header) > 13 else None))


def unknown_in_blocks(blocks: dict) -> list:
    """Returns the UnknownContent of each block of a kind nxwright does not
    handle. The build leaves these blocks out."""
    return [UnknownContent("a block of a kind nxwright does not handle", "block %s" % name,
                           data, MAY_BE_LOST)
            for name, data in blocks.items() if not handles_block(name)]


def unknown_in_manifest_entries(manifest) -> list:
    """Returns the UnknownContent of each entry in the manifest's list that
    is of a kind nxwright does not know. The build leaves these entries
    out."""
    return [UnknownContent("a manifest entry of a kind nxwright does not know",
                           "manifest entry %d" % index,
                           kind.encode("latin-1") + b"\0" + name.encode("latin-1"), MAY_BE_LOST)
            for index, (kind, name) in enumerate(manifest.resources)
            if kind not in LISTED_IN_ORDER]


def unknown_in_manifest_header(header: bytes) -> list:
    """Returns the things in the manifest header `header` that nxwright
    does not know. A header whose size is not HEADER_SIZE may be lost, and
    so may a screen model that nxwright does not know. A character encoding
    that nxwright does not know is kept exactly, as its number. But if the
    screen model is unknown too, app.toml has no screen settings to keep the
    number with, and the encoding may be lost. A byte that the build writes
    as a constant may be lost if it has a value that no Nextion Editor from
    1.60.1 to the current one writes there (_older_editor_writes)."""
    if len(header) != HEADER_SIZE:
        # nxwright cannot read the device settings from a header of another
        # size. The result is the same as for an unknown screen model.
        return [UnknownContent("a manifest header of %d bytes, not %d: app.toml will have no "
                               "screen settings, and the build refuses the folder until you "
                               "add them"
                               % (len(header), HEADER_SIZE), "manifest header", header[:16],
                               MAY_BE_LOST)]
    found = []
    if header[13] not in ENCODINGS and model_with_id(header[16:20]) is None:
        # app.toml will have no device settings to keep the encoding's
        # number with. The note gives the number, so that the user can add
        # it back with the settings.
        found.append(UnknownContent("a character encoding nxwright does not know, which app.toml "
                                    "cannot keep without the screen settings: when you add them, "
                                    "add encoding = %d too" % header[13],
                                    "manifest header, byte 13",
                                    header[13:14], MAY_BE_LOST))
    elif header[13] not in ENCODINGS:
        # app.toml keeps the encoding as its number (encoding_name), and
        # nxwright reads the project's texts one byte per character.
        found.append(UnknownContent("a character encoding nxwright does not know: its texts are "
                                    "read one byte per character, and may show as the wrong "
                                    "characters until nxwright knows the encoding",
                                    "manifest header, byte 13", header[13:14], KEPT))
    if model_with_id(header[16:20]) is None:
        found.append(UnknownContent("a screen model nxwright does not know: app.toml will have no "
                                    "screen settings, and the build refuses the folder until "
                                    "nxwright knows the model",
                                    UNKNOWN_MODEL_PLACE, header[16:20],
                                    MAY_BE_LOST))
    expected = {place: CURRENT_FORM.get(place, 0) for place in range(HEADER_SIZE)
                if place not in _SETTINGS_BYTES}
    found += [UnknownContent("a manifest header byte the build writes as %d" % value,
                             "manifest header, byte %d" % place, header[place:place + 1],
                             MAY_BE_LOST)
              for place, value in expected.items()
              if header[place] != value and not _older_editor_writes(header, place)]
    return found


def _older_editor_writes(header: bytes, place: int) -> bool:
    """Returns whether the byte at `place` of the manifest header `header`
    has a value that a Nextion Editor from 1.60.1 to the current one writes
    there. Each of them writes its own version in bytes 9 and 36, and one of
    three values in byte 65. Nothing is lost when the build replaces these
    values with the current ones, because an older Nextion Editor writes its
    own values again when it saves the project."""
    if place in _VERSION_BYTES:
        return is_checked_version(*(header[each] for each in _VERSION_BYTES))
    return place == 65 and header[place] in _KNOWN_BYTE_65


def unknown_in_picture_headers(blocks: dict) -> list:
    """Returns the UnknownContent of the pictures' files (".is" blocks). A
    picture in a file of a type nxwright does not decode is kept exactly,
    with its screen copy. A suffix in capitals is written otherwise, in
    lower case. A header that differs from the one the build writes may be
    lost, because the build writes its own header in its place."""
    found = []
    for name, block in blocks.items():
        if numbered_block(name, "is") is None:
            continue
        source = parse_image_source(block)
        if not decodes_picture(source.suffix):
            found.append(UnknownContent("a picture in a %s file, which nxwright does not decode: "
                                        "the source folder keeps the project's screen copy of the "
                                        "picture, and the build uses that copy as it is"
                                        % source.suffix,
                                        "block %s" % name, block[:16], KEPT))
        if source.suffix != source.suffix.lower():
            found.append(UnknownContent("a picture's suffix %s in capitals, which the build "
                                        "writes in lower case" % source.suffix,
                                        "block %s" % name, block[:16], WRITTEN_OTHERWISE))
        size = len(block) - len(source.data)
        if block[:size] != encode_image_source(source)[:size]:
            found.append(UnknownContent("a picture's header that differs from the build's",
                                        "block %s" % name, block[:size], MAY_BE_LOST))
    return found


def unknown_in_picture_sources(blocks: dict, manifest) -> list:
    """Returns the UnknownContent of the sources of resized pictures (".ib"
    blocks). The dump leaves out a source that kept_picture_sources does not
    keep, because its picture is not listed or nxwright cannot read it. That
    source may be lost. A source that is kept may be lost too, if its header
    differs from the one the build writes. The build makes its own header
    from the width and height of the source's file."""
    kept = {name: source for name, source in kept_picture_sources(blocks, manifest).values()}
    found = []
    for name, block in blocks.items():
        if numbered_block(name, SOURCE_EXTENSION) is None:
            continue
        source = kept.get(name)
        if source is None:
            found.append(UnknownContent("a picture's source the build leaves out",
                                        "block %s" % name, block, MAY_BE_LOST))
            continue
        size = len(block) - len(source.data)
        built = encode_image_source(ImageSource(*picture_data_size(source.data), source.data,
                                                source.suffix))
        if block[:size] != built[:size]:
            found.append(UnknownContent("a picture's header that differs from the build's",
                                        "block %s" % name, block[:size], MAY_BE_LOST))
    return found


def unknown_in_pages(pages: dict, encoding_code: int = None) -> list:
    """Returns the UnknownContent of `pages`, which maps the place of each
    page, such as "block 0.pa", to its PageBlock. The function finds:
      - each value of a page header that nxwright has not seen
        (unknown_in_page_header);
      - each part of an object that the page files do not keep as it is
        (page_source.object_irregularities). If `encoding_code` is given,
        the object's texts are checked in the encoding of that number;
      - each component type that nxwright does not know, which the source
        folder keeps exactly;
      - each attribute that has no width in nxwright's tables, or a width
        other than the one stored. The source folder keeps that attribute
        as its stored bytes."""
    codec = None if encoding_code is None else TextCodec(encoding_name(encoding_code))
    found = []
    for page_place, page in pages.items():
        found += unknown_in_page_header(page, page_place)
        for index, page_object in enumerate(page.objects):
            where = "%s, object %d, " % (page_place, index)
            irregular = [UnknownContent(what, where + place, data, sort)
                         for sort, what, place, data
                         in object_irregularities(page_object, index, page.name, codec)]
            found += irregular
            if any(each.sort == CANNOT_BE_KEPT for each in irregular):
                # The other checks need an object that nxwright can read.
                continue
            # If an object has its type twice, the conversion keeps the last
            # one, and so does this check.
            object_type = [item for item in page_object.items
                           if isinstance(item, Attribute) and item.name == "type"][-1].value[0]
            where = "%s, object %d" % (page_place, index)
            if object_type not in TYPE_NAMES:
                found.append(UnknownContent("a component type nxwright does not know", where,
                                            bytes([object_type]), KEPT))
            # If an object has an attribute twice, the conversion keeps the
            # last one, and so does this check.
            for item in {item.name: item for item in page_object.items
                         if isinstance(item, Attribute)}.values():
                found += _unknown_attribute(item, object_type, where)
    return found


def unknown_in_page_header(page, page_place: str) -> list:
    """Returns the values in the header of `page` that nxwright has not seen
    (page_header.py). `page_place` is the page's place, such as "block
    0.pa". A lock value, bytes 21 and 22, or a system page mark that
    nxwright has not seen is kept exactly, in its own key of the page file.
    Bytes 40 to 43 in a form not seen are written otherwise, because the
    build writes the current form in their place. The Nextion Editor also
    writes the current form. Bytes 44 to 55 may be lost if they are not
    zero, because the build writes zeros."""
    field_16, field_40 = page.unknown_16, page.unknown_40
    where = "%s, page header " % page_place
    found = []
    if field_16[4] not in (0, 1):
        found.append(UnknownContent("a page lock value nxwright has not seen", where + "byte 20",
                                    field_16[4:5], KEPT))
    if field_16[5:7] != HEADER_21:
        found.append(UnknownContent("page header bytes nxwright has seen only as 4f 21",
                                    where + "bytes 21 and 22", field_16[5:7], KEPT))
    if field_16[7] not in (0, *SYSTEM_PAGES.values()):
        found.append(UnknownContent("a system page mark nxwright does not know", where + "byte 23",
                                    field_16[7:8], KEPT))
    if not header_40_form_known(field_40):
        found.append(UnknownContent("a page header form nxwright has not seen",
                                    where + "bytes 40 to 43", field_40[:4], WRITTEN_OTHERWISE))
    if not header_44_known(field_40):
        found.append(UnknownContent("page header bytes nxwright has seen only as zeros",
                                    where + "bytes 44 to 55", field_40[4:], MAY_BE_LOST))
    return found


def _unknown_attribute(attribute: Attribute, object_type: int, where: str) -> list:
    """Returns the UnknownContent of the attribute `attribute`, on an object
    of type `object_type`, if the page files keep it in its raw form. They
    do for an attribute that has no width in nxwright's tables, or one
    stored at a width other than the tables give.
    page_source._attribute_to_value makes the same tests."""
    if is_string_attribute(object_type, attribute.name):
        return []
    width = expected_width(object_type, attribute.name)
    where = "%s, attribute %s" % (where, attribute.name)
    type_name = TYPE_NAMES.get(object_type, "type %d" % object_type)
    # The page file keeps both kinds of attribute as their stored bytes, in
    # their raw form (page_source.RAW_KEY).
    if width is None:
        return [UnknownContent("an attribute nxwright does not know, %s, on a %s"
                               % (attribute.name, type_name), where, attribute.value, KEPT)]
    if width != len(attribute.value):
        # A reference to a picture or a font stores the resource's ID, not
        # the resource's name.
        by_id = (", whose bytes give a resource's ID, so they stay correct only while the "
                 "resources keep their order"
                 if reference_kind(object_type, attribute.name) else "")
        return [UnknownContent("an attribute stored in %d bytes, where nxwright knows %d, "
                               "%s, on a %s%s"
                               % (len(attribute.value), width, attribute.name, type_name,
                                  by_id), where, attribute.value, KEPT)]
    return []


class UnknownContentError(NxwrightError):
    """Raised for content that nxwright does not know and that the next
    build may lose, when the user has not chosen to go on past it. `found`
    is a list of that UnknownContent. The error has its own class, apart
    from other refusals, so that a command can prompt the user to go on or
    to stop."""

    def __init__(self, origin: Path, found: list, project: Path = None):
        """`origin` is the project file or the dump that contains `found`.
        `project` is the project file, if known, for `nxwright report` to
        read."""
        self.found = found
        super().__init__(
            "%s contains things nxwright does not know, which the next build may lose:\n%s\n"
            "The built project may then lack parameters that the Nextion Editor needs, and may "
            "not be the same as this one. %s"
            % (origin, listed(found), report_hint(project)))


def report_hint(project: Path = None) -> str:
    """Returns the sentence that suggests `nxwright report` to the user. If
    `project` is given, the sentence includes the project file's path."""
    named = "the project file" if project is None else str(project)
    return ("`nxwright report` writes a report on %s to send to nxwright's maintainers."
            % named)


def listed(found: list) -> str:
    """Returns the UnknownContent of `found` as a list, one line each."""
    return "\n".join("  - %s (%s)" % (each.what, each.where) for each in found)


def checked(origin: Path, found: list, continue_with_unknown: bool,
            project: Path = None) -> list:
    """Checks `found`, the UnknownContent of `origin`, by sort. Raises
    NxwrightError for content nxwright cannot keep. Raises
    UnknownContentError for content the next build may lose, unless
    `continue_with_unknown` is true. Otherwise returns a note for each thing
    kept exactly, and a warning for each thing written otherwise, which
    does not need a question. It also returns a warning for each thing that
    may be lost, when the user chose to go on past it. `project` is passed to
    UnknownContentError."""
    cannot = [each for each in found if each.sort == CANNOT_BE_KEPT]
    if cannot:
        raise NxwrightError("%s contains things nxwright cannot keep:\n%s\nA newer Nextion "
                            "Editor may have added them. %s" % (origin, listed(cannot),
                                                       report_hint(project)))
    lost = [each for each in found if each.sort == MAY_BE_LOST]
    if lost and not continue_with_unknown:
        raise UnknownContentError(origin, lost, project)
    notes = ["%s (%s), which the source folder keeps exactly" % (each.what, each.where)
             for each in found if each.sort == KEPT]
    notes += ["%s (%s), which the next build writes as nxwright knows it" % (each.what, each.where)
              for each in found if each.sort == WRITTEN_OTHERWISE]
    notes += ["went on past %s (%s), which the next build may lose"
              % (each.what, each.where) for each in lost]
    if notes:
        # nxwright does not yet support this content properly, so the notes
        # end by pointing the user to the report.
        notes.append(report_hint(project))
    return notes


def unknown_in_dump(dump_folder: Path) -> list:
    """Returns the UnknownContent that a dump's files show: in its manifest
    header, which project.txt shows, and in its pages. A dump leaves out the
    blocks of other kinds, the manifest's list, and the pictures' headers,
    so this function cannot check them. `nxwright dump` gave a warning for
    each of them when it wrote the dump."""
    shown = dump_header_bytes(dump_folder)
    header = dump_manifest_header(dump_folder)
    if shown is None:
        # A dump written from a source folder does not show a header to check.
        found = []
    elif header is None:
        found = [UnknownContent("a manifest header of a size other than %d bytes: app.toml will "
                                "have no screen settings, and the build refuses the folder until "
                                "you add them" % HEADER_SIZE, "manifest header", shown[:16],
                                MAY_BE_LOST)]
    else:
        found = unknown_in_manifest_header(header)
    pages = {"page file %s" % path.name: page_from_text(path.read_text(encoding="utf-8"))
             for _, path in sorted(page_text_files(dump_folder).items())}
    return found + unknown_in_pages(pages, None if header is None else header[13])
