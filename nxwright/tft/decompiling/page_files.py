"""Writes a decoded page's two source files, pages/<name>.page.toml and
pages/<name>.nx, in strict Nextion syntax, as nxwright's library writes
them (source/page_source.page_to_source), from what the page's and its
components' decoders read back (page.py, objects.py) and the lines of code
the decoder of code reads (code.py).

The decoder builds the page block nxwright would read from a dump: each
object's type, ID, and name, then its type's attributes in their order, at
their defaults where the file keeps no value, with the decoded values over
them, and its events. nxwright's library then writes the page file, leaving
out what equals its type's default, as it does for a dump.

Each run of code leaves out the blocks the Nextion Editor added for an
object (ObjectValues.added): at a run's start or its end, as a key's lines;
what the components add at the start of the page's load section, which the
page's load and loadend code follow (page.page_load_runs); and what they
add at the end of the page's unload event, as a file stream's close.
"""
from functools import lru_cache

from nxwright.project.attribute_values import number_to_bytes
from nxwright.project.component_defaults import DEFAULTS_FILE, defaults_from_toml
from nxwright.project.device_settings import TextCodec, encoding_code
from nxwright.project.page_block import (HEADER_SIZE, Attribute, Event, Marker, PageBlock,
                                         PageObject)
from nxwright.project.page_header import SYSTEM_PAGES, PageHeader, header_16, header_40
from nxwright.project.page_text import expected_width, is_string_attribute
from nxwright.source.page_source import page_to_source

from nxwright.tft.component_types import KEYBOARD_PAGES
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.code import decoded_lines
from nxwright.tft.decompiling.decoded_file import CodeRun, DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import decoded_values, record_head
from nxwright.tft.decompiling.page import decoded_page_values, page_load_runs
from nxwright.tft.frame import DISUP

# The page's events in its load section, and the one components add to at
# its end.
_LOAD, _LOADEND, _UNLOAD = "load", "loadend", "unload"
_PAGE_UNLOAD = "page unload"
# The system page of each of nxwright's keyboard pages, by its name.
_SYSTEM_PAGES = {KEYBOARD_PAGES[number]: kind for kind, number in SYSTEM_PAGES.items()
                 if number in KEYBOARD_PAGES}


def page_files(decoded_page: DecodedPage, decoded_file: DecodedFile, names) -> tuple:
    """Returns (the text of the page file, the text of its code file) of
    `decoded_page`, as nxwright's library writes them, with `names`, the
    folder's ResourceNames, naming its fonts and pictures. Raises
    DecodeError for what a decoder cannot read, and NxwrightError for what
    nxwright's page files cannot keep."""
    defaults = component_defaults()
    codec = TextCodec(decoded_file.encoding)
    values = [decoded_page_values(decoded_page, decoded_file)] + [
        decoded_values(each, decoded_page, decoded_file) for each in decoded_page.objects[1:]]
    runs = _runs(decoded_page, decoded_file, values)
    objects = []
    for decoded_object, object_values in zip(decoded_page.objects, values):
        lines = {event: [codec.encode_keeping_bytes(line, "%s.%s" % (decoded_object.name.text,
                                                                     event))
                         for line in decoded_lines(run, decoded_page.page_id, decoded_file)]
                 for event, run in runs[decoded_object.object_id].items()}
        objects.append(page_block_object(decoded_object, object_values.attributes, lines,
                                         defaults[decoded_object.type_number]))
    name = decoded_page.objects[0].name.text
    header = PageHeader(system_page=_SYSTEM_PAGES.get(name))
    page = PageBlock(name, HEADER_SIZE, header_16(header),
                     header_40(encoding_code(decoded_file.encoding)), objects)
    source = page_to_source(page, names, defaults, decoded_file.encoding)
    return source.toml, source.events


@lru_cache(maxsize=None)
def component_defaults() -> dict:
    """Returns nxwright's component defaults, {type number: TypeDefaults},
    read once."""
    return defaults_from_toml(DEFAULTS_FILE.read_text(encoding="utf-8"), DEFAULTS_FILE.name)


def _runs(decoded_page: DecodedPage, decoded_file: DecodedFile, values: list) -> dict:
    """Returns {object's ID: {event's name: its CodeRun}} of `decoded_page`,
    each without the blocks the Nextion Editor added (`values`, each
    object's ObjectValues), the page's load and loadend among its own."""
    runs = {}
    for decoded_object, object_values in zip(decoded_page.objects, values):
        runs[decoded_object.object_id] = {
            event: _without(run, *object_values.added.get(event, (0, 0)))
            for event, run in decoded_object.events.items()}
    load_blocks = sum(object_values.added.get(_LOAD, (0, 0))[0] for object_values in values[1:])
    closing = sum(object_values.added.get(_PAGE_UNLOAD, (0, 0))[1]
                  for object_values in values[1:])
    page_runs = runs[0]
    page_runs[_LOAD], page_runs[_LOADEND] = page_load_runs(decoded_page, decoded_file,
                                                           load_blocks)
    if _UNLOAD in page_runs:
        page_runs[_UNLOAD] = _without(page_runs[_UNLOAD], 0, closing)
    return runs


def _without(run: CodeRun, start: int, end: int) -> CodeRun:
    """Returns `run` without its first `start` blocks and its last `end`.
    Raises DecodeError when it has fewer blocks than that."""
    if start + end > len(run.blocks):
        raise DecodeError("a run of %d blocks has fewer than the %d the Nextion Editor added "
                          "to it" % (len(run.blocks), start + end), run.place,
                          b"".join(run.blocks))
    places = run.block_places()
    kept = run.blocks[start:len(run.blocks) - end]
    place = places[start] if start < len(places) else run.place + sum(
        4 + len(block) for block in run.blocks)
    return CodeRun(place, kept)


def page_block_object(decoded_object: DecodedObject, attributes: dict, lines: dict,
                      type_defaults) -> PageObject:
    """Returns the page block's object of `decoded_object`: its type, ID,
    and name, its type's attributes in their order, each its decoded value
    from `attributes` or else its default, its right and bottom edges after
    its h, then its type's events, with `lines`, each event's lines of code
    as bytes. Raises DecodeError for code in an event its type has not."""
    type_number = decoded_object.type_number
    stored = [Attribute("type", bytes([type_number])),
              Attribute("id", bytes([decoded_object.object_id])),
              Attribute("objname", decoded_object.name.text.encode("latin-1"))]
    for name, default in type_defaults.attributes:
        value = attributes.get(name)
        if value is None:
            stored.append(Attribute(name, default))
        elif is_string_attribute(type_number, name):
            stored.append(Attribute(name, value))
        else:
            stored.append(Attribute(name, number_to_bytes(value, expected_width(type_number,
                                                                                name))))
        # A disup, which only a file made by the Nextion Editor 1.63.3 or an
        # older one gives, goes right after the drag, as nxwright's page
        # files keep it.
        if name == "drag" and DISUP in attributes:
            stored.append(Attribute(DISUP, number_to_bytes(attributes[DISUP],
                                                           expected_width(type_number, DISUP))))
        if name == "h":
            x, y, w, h = (attributes.get(each, 0) for each in ("x", "y", "w", "h"))
            stored += [Attribute(end, ((start + size - 1) & 0xFFFF).to_bytes(2, "little"))
                       for end, start, size in (("endx", x, w), ("endy", y, h))]
    unknown = [event for event, run in lines.items() if run and event not in type_defaults.events]
    if unknown:
        raise DecodeError("%s has code in %s, which its type has no event of"
                          % (decoded_object.name.text, ", ".join(unknown)),
                          record_head(decoded_object).drawing_place, decoded_object.record)
    events = [Event(event, lines.get(event, [])) for event in type_defaults.events]
    return PageObject([Marker(b"att-%d" % len(stored))] + stored + events)
