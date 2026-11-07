"""The component types nxwright compiles, one module each, named after the type
as nxwright names it (project/object_types.py): text.py for a text.

A page's objects are the page itself, ID 0, then its components, in ID
order. Every object has data entries (frame.py gives their form), numbered
across the project: a page's first, then its components', then the next
page's. Code refers to an attribute by its entry's number, so the frame and
the statement encoder both number them here (first_entries), once a
compile, through the compile's context (compile_context.py).

Each module has:

  - MATCHED, the list of what it matched with probes (matching.py);
  - ENTRIES, the number of its data entries;
  - EVENTS, the names of its events, in the order its blocks give them;
  - drawing(page_object, project, place) -> list: the blocks of the
    object's drawing, each without its size word;
  - background_fill(page_object, project, place) -> list: the blocks of the
    run that follows the drawing, which draw its page's background over the
    object's area. A type whose run is that background alone, the plain
    fill, imports background_fill, below. A type that is not drawn has none
    (DRAWN, below);
  - data(page_object, project, place) -> bytes: the object's entries;
  - memory(page_object, project) -> bytes: the object's starting values in
    the screen's memory, a multiple of 4 bytes, which follow its page's,
    or the int variables for a global object (is_global), or memory_at,
    below, in its place;
  - record_slots() -> dict: the type's slots in the object's record, as
    {slot: the number of the entry within the type};
  - attribute_place(name) -> int: the number, within the type, of the entry
    of the attribute `name`, which the statement encoder adds to the
    object's first entry for an operand such as `t0.txt`. It gives any
    attribute the type writes, and raises KeyError for another. On P and E,
    the encoder takes the number from code_entry, which renumbers it.

A module may also have:

  - event_start(page_object, project, place, event) -> list: the blocks
    the Nextion Editor writes at the start of the event `event`, before
    the code the page file gives it. A type without it has none. A type
    whose blocks need only the object's place, and its series if they
    differ by series, may also give them as event_blocks, which the
    decoder calls (decompiling/), as the button and the dual-state
    button do;
  - load_start(page_object, project, place, places) -> list: the blocks the
    object adds to its page's load section, before the page's own load
    code, in the order of the page's components, as a timer does. `places`
    are the places of the object's record, by name (frame.py), and
    place.load_place is where in the user code these blocks start. A type
    without it adds none;
  - FIRST_PASS_NUMBERS, for a type whose code has "S " blocks, as a timer's
    and a scrolling text's: how many numbers it takes in the first pass that
    numbers its page's "S " blocks (label_numbers.py). The frame gives such
    an object its numbers in its place (ObjectPlace.timer_numbers);
  - DRAWING_JUMPS_TO_LOAD, True for a type whose drawing jumps into its own
    blocks in the load section, as a scrolling text's does. The frame lays
    such a page out twice, and gives the drawing place.load_place the
    second time;
  - page_text(page_object, project) -> bytes: what the object keeps after
    its page's components' memory, as a QR code keeps its txt there, a
    multiple of 4 bytes, or after the global objects' memory for a global
    one. Such a type has memory_at in place of memory;
  - buffer_size(page_object, project) -> int: the size of the buffer the
    object keeps at the end of its page's memory, as a waveform does
    (frame.py gives where). On T and K, such a type has memory_at in place
    of memory;
  - memory_at(page_object, project, place) -> bytes: the object's starting
    values, which give where its page_text lies, place.text_place, or
    where its buffer lies, place.buffer_place. The frame calls it once with
    neither place, for its length, which must not hang on them, then once
    the texts and buffers are placed;
  - TXT_PLACE, for a type that keeps its txt in its own memory on T, K, and
    F, as a text does: where its txt lies in its memory, from its base. The
    frame's scratch image then fills the bytes that round its room up to 4
    (frame._t_rooms);
  - P_ENTRIES, P_MEMORY_SIZE, and P_TEXTS, for a type the frame writes on P
    and E: its entries, {number: (name, place from its base, highest,
    lowest, code)}, the place a FixedValue for an entry that gives its value
    itself, as a hotspot's aph; its memory's size; and its texts, which lie
    after its page's components' memory, {where in its memory their place
    lies: (attribute, the attribute that gives its room, where in its memory
    that lies)}, such as {72: ("txt", "txt_maxl", 70)}, in the order they
    lie. It may give P_OWNER_TOPS too, {attribute: byte}, the top byte of
    the owner field of those attributes' entries, such as {"val": 0x80}
    (p_component_entries), P_OWNER, the owner every entry gives in place of
    its ID and its page's, as a variable's 0xFFFF, and P_ROOMS_WHEN_ZERO,
    {attribute: attribute}, the attribute that gives a text's room when the
    one P_TEXTS names is 0, such as {"path_m": "txt_maxl"} (p_text), and
    P_LAST_RESOURCE, {attribute: kind}, the attributes whose entry's highest
    is the project's last resource of a kind, such as {"vid": "animation"}
    (p_table);
  - P_HEAD_SIZE, for a type whose memory on P starts with fewer bytes of its
    record's head than a drawn type's: how many, as a file stream's 4;
  - P_CODE_ENTRIES, for a type whose code on P names an entry that its data
    does not give: {attribute: the entry's number within the type}, as a
    sliding text's {"path": 34} (code_entry);
  - p_memory_extras(page_object, project, place) -> dict: the bytes of its
    memory on P that no entry gives, {where in its memory: bytes}, as where
    a file stream's buffer lies, place.buffer_place;
  - unload_lines(page_object) -> list: the lines of code the Nextion Editor
    adds for the object at the end of its page's unload event, after the
    page's own code, in the order of the page's components, as a file
    stream's close;
  - DRAWN, False for a type that is not drawn, as a variable or a timer. Its
    drawing's run is its only one, without background_fill's, and its
    record has a place and size of 0, 0, 1, 1 (frame.py), or UNDRAWN_PLACE,
    (x, y, w, h), as an audio's -50, 0, 50, 50. A drawing without blocks, as
    such a type's or a hotspot's, gives the record no first block's place;
  - variant(page_object): what describes `page_object`, for a type whose
    objects differ, as a variable is one of a number or of a text by its
    sta. It has the members above but MATCHED, which stays the module's.
    The frame, first_entries, and the statement encoder find it through
    object_module.

`page_object` is the object as nxwright's page_block.parse_page gives it,
and `place` its ObjectPlace. The frame owns the record's layout and the
page's own blocks, data, and record.
"""
from dataclasses import dataclass, replace
from functools import lru_cache
import importlib
import importlib.util
import struct

from nxwright import NxwrightError
from nxwright.project.attribute_values import number_from_bytes
from nxwright.project.device_settings import TextCodec
from nxwright.project.object_types import TYPE_NAMES
from nxwright.project.page_header import SYSTEM_PAGES

from nxwright.tft.project import NOT_DESCRIBED, Component
from nxwright.tft.reasons import INVALID_VALUE

# A page's own entries, before its components'. A page with no background
# has one fewer (page_entries).
PAGE_ENTRIES = 33
# What lies behind a page, its sta: nothing, its bco, or its pic.
NO_BACKGROUND, COLOUR, PICTURE = 0, 1, 2
# The commands with which a page draws its background, and a component the
# part of it under its area: fill, for a colour; pic and xpic, for a
# picture. K numbers them as T does. Each takes the page's entry of its bco
# or its pic, which is the same entry. Some types draw with them too, as a
# picture does with pic. The drawing commands' table gives the same bytes
# (instructions/drawing_commands.py). This module cannot import that
# table, as the statement encoder imports this module.
FILL = b"\x09\x0d\x04"
PIC = b"\x09\x01\x04"
XPIC = b"\x09\x0a\x04"
PAGE_BACKGROUND_ENTRY = 24
# An effect, how an object comes into view as its page opens, gives the
# object two more entries, empty: a component's at its entry 19, where each
# drawn type's own entries start, and a page's at its entry 23, its sta's.
# Each later entry is numbered two on. T and K play no effect, and the
# Nextion Editor writes an effect, its first, and its time nowhere else.
EFFECT_ENTRIES = 2
OWN_ENTRIES_START = 19
_PAGE_EFFECT_START = 23
# The command ref, which refreshes a component: `ref b0` gives 09 03 04,
# then "b0", as the screen commands' table gives it
# (instructions/screen_commands.py). The Nextion Editor writes it in a
# button's events and in a scrolling text's timer code.
REF = b"\x09\x03\x04"
# The command setbrush, with which a component's drawing starts: its place
# and size, then the entries of its look. By series: K and F number it their
# own way, as they do zstr.
SETBRUSH = {"T": b"\x09\x1c\x08", "K": b"\x09\x1d\x08", "F": b"\x09\x1d\x08"}
# The command zstr, which draws a text, and its first four arguments' number.
_ZSTR = {"T": b"\x09\x13\x04", "K": b"\x09\x15\x04", "F": b"\x09\x17\x04"}
_ZSTR_NUMBER = 0x7FFF
# The command that draws a component's 3D border, by series, and the
# border's two colours. A pressed button and a checkbox give them dark then
# light, a released button light then dark (button-component.md).
_BORDER = {"T": b"\x09\x07\x08", "K": b"\x09\x07\x08", "F": b"\x09\x07\x08"}
BORDER_DARK, BORDER_LIGHT = 0x4228, 0xE71C


@dataclass(frozen=True)
class ObjectPlace:
    """Where an object lies: its page's ID; its own ID on the page; the
    numbers of its first entry and of its page's first entry, counted across
    the project (first_entries); its memory base, where its starting values
    lie in the screen's memory; for a type that keeps a text after its
    page's components' memory (page_text), where that text lies, or None;
    for a type that keeps a buffer at the end of its page's memory
    (buffer_size), where that buffer lies, or None; on P, for a type with
    texts (P_TEXTS), where each lies, by its attribute; for a type that adds
    blocks to its page's load section (load_start), where in the user code
    they start, or None before the frame knows; the byte the project's
    encoding gives each of the object's entries (two_byte_start); and, for
    a timer or a scrolling text on T, K, or F, its two numbers of the
    counter of "S " blocks, where its numbers start in the first pass and
    its second (label_numbers.numbers), or None. A probe's fixture keeps
    an object's place without them (frame_probes.py)."""
    page: int
    object_id: int
    first_entry: int
    page_entry: int
    base: int
    text_place: int = None
    text_places: dict = None
    buffer_place: int = None
    load_place: int = None
    two_byte_start: int = 0
    timer_numbers: tuple = None


# The first byte of an attribute's operand and of a value's (entry_operand,
# value_operand), which the decoder reads too (decompiling/code.py).
ENTRY_TAG, VALUE_TAG = 0x01, 0x03


def entry_operand(number: int) -> bytes:
    """Returns the operand for the entry `number`: 01, then the number, 4
    bytes, the form in which drawings and code refer to an attribute."""
    return bytes([ENTRY_TAG]) + struct.pack("<I", number)


def value_operand(number: int) -> bytes:
    """Returns the operand for the number `number` as a value: 03, then the
    number, 4 bytes, signed. Drawings give their numbers in this form, as
    code gives a long number and a jump."""
    return bytes([VALUE_TAG]) + struct.pack("<i", number)


# An entry: the object's base, a value, its highest and lowest values, its
# owner, and a code (packed_entries).
ENTRY = struct.Struct("<IiiiII")

# The first byte of each encoding's two-byte characters, as the Nextion
# Editor writes it in header 1 and in every entry: the lowest first byte of
# the encoding's grid, as its font generator lays out a font of every
# character (nxwright's zi_font). utf-8 gives 0xFF.
_TWO_BYTE_STARTS = {"gb2312": 0xA1, "big5": 0xA0, "shift-jis": 0x81, "ks_c_5601-1987": 0xA1,
                    "utf-8": 0xFF}


def two_byte_start(encoding: str) -> int:
    """Returns the first byte of the two-byte characters of the encoding
    named `encoding` (_TWO_BYTE_STARTS), or 0 for an encoding of one byte a
    character."""
    return _TWO_BYTE_STARTS.get(encoding, 0)


def object_entries(page_object, object_id: int) -> dict:
    """Returns the entries every object drawn has, by number: its type, its ID,
    its vscope (vscope_entry), its place and size, and its right and bottom
    edges, as (value, highest, lowest, code)."""
    x, y, w, h = place_and_size(page_object)
    return {0: (page_object.attribute("type")[0], 255, 0, 0x101), 1: (object_id, 255, 0, 0x101),
            3: vscope_entry(page_object), 9: (x, 6000, -6000, 0x20B), 10: (y, 6000, -6000, 0x20C),
            11: (w, 2000, -2000, 0x20D), 12: (h, 2000, -2000, 0x20E),
            13: (x + w - 1, 0x7FFF, -0x8000, 0x208), 14: (y + h - 1, 0x7FFF, -0x8000, 0x208)}


def vscope_entry(page_object) -> tuple:
    """Returns the entry of `page_object`'s vscope, which every object has as
    its entry 3, as (value, highest, lowest, code): 0, the page's own, or 1,
    global (is_global)."""
    return (int(is_global(page_object)), 1, 0, 0x101)


def is_global(page_object) -> bool:
    """Whether `page_object` is global, its vscope 1. A global object's
    memory lies among the int variables, not in its page's memory
    (frame.py)."""
    return number_from_bytes(page_object.attribute("vscope") or b"\x00") == 1


# The keyboard page each key opens, by the key's value. These are the stock
# pages the Nextion Editor adds for a component's key, whose value is the
# page's number among its system pages (nxwright's page_header), and
# nxwright's own keyboards, of the same names.
_KEYBOARD_NAMES = {"keyboard": "keybdA", "keypad": "keybdB", "speed-dial": "keybdC",
                   "chinese-input": "keybdAP"}
KEYBOARD_PAGES = {SYSTEM_PAGES[kind]: name for kind, name in _KEYBOARD_NAMES.items()}


def key_lines(page_object, object_id: int) -> list:
    """Returns the lines the Nextion Editor adds at the end of the Touch
    Release event of a component with a key, whose ID is `object_id`. They
    give its keyboard page's global variables loadpageid and loadcmpid the
    page the screen shows, dp, and the component's ID, then open that page,
    as `keybdB.loadpageid.val=dp`, `keybdB.loadcmpid.val=1`, and
    `page keybdB`. A component without a key, its key 255, has none."""
    page = KEYBOARD_PAGES.get(number_from_bytes(page_object.attribute("key") or b"\xff"))
    if page is None:
        return []
    return ["%s.loadpageid.val=dp" % page, "%s.loadcmpid.val=%d" % (page, object_id),
            "page %s" % page]


def packed_entries(entries: dict, count: int, place: ObjectPlace, owner: int = None,
                   owner_tops: dict = None) -> bytes:
    """Returns `count` entries of 24 bytes, `entries` {number: (value,
    highest, lowest, code)} filled in, the others zeros. Each starts with
    the object's base, and gives its ID times 256 plus its page's ID, or
    `owner` when it is given, then the byte its project's encoding gives
    (two_byte_start), in a field of 4 bytes. `owner_tops`, {number: byte},
    gives the top byte of that field for the entries it names, as a timer's
    tim and en give 1 and 2; every other entry gives 0 there."""
    if owner is None:
        owner = place.object_id << 8 | place.page
    owner |= place.two_byte_start << 16
    data = bytearray(ENTRY.size * count)
    for number, (value, highest, lowest, code) in entries.items():
        ENTRY.pack_into(data, ENTRY.size * number, place.base, value, highest, lowest,
                        owner | (owner_tops or {}).get(number, 0) << 24, code)
    return bytes(data)


# The entries a drawn component has on P, whatever its type, by number
# within the type: (name, place from its base, highest, lowest, code)
# (p_component_entries). They lie in the head its memory starts with, but
# for its effect.
P_DRAWN_ENTRIES = {
    0: ("type", 0, 255, 0, 0x121), 1: ("id", 1, 255, 0, 0x121), 3: ("vscope", 2, 1, 0, 0x121),
    4: ("drag", 32, 1, 0, 0x131), 6: ("aph", 34, 127, 0, 0x131),
    9: ("x", 40, 6000, -6000, 0x23B), 10: ("y", 42, 6000, -6000, 0x23C),
    11: ("w", 44, 2000, -2000, 0x22D), 12: ("h", 46, 2000, -2000, 0x22E),
    13: ("endx", 48, 0x7FFF, -0x8000, 0x228), 14: ("endy", 50, 0x7FFF, -0x8000, 0x228),
    15: ("effect", 52, 8, 0, 0x131)}


class FixedValue(int):
    """The place, in a type's P_ENTRIES, of an entry that gives its value
    itself, not a place in memory, as a hotspot's aph gives its aph, 127 at
    its default. The number is the attribute's default, and p_table puts
    the object's own value in its place. The entry writes it as it is
    (p_component_entries), and the memory keeps no bytes for it
    (p_component_memory)."""


# On P, an object with an effect has its first and its time as entries 16
# and 17, after its effect's, in its memory after its effect; each later
# entry is numbered two on (ResearchNotes/tft/p-series.md). Without an effect,
# they have no entry, and its memory gives zeros there.
P_EFFECT_ENTRIES = {16: ("first", 53, 100, 0, 0x131), 17: ("time", 54, 0xFFFF, 150, 0x232)}


def with_p_effect(entries: dict, page_object) -> dict:
    """Returns `entries`, an object's entries on P by number, {entry: (name,
    ...)}, as `page_object`'s are: with its effect's first and time, and
    each later entry two on, when it has an effect (P_EFFECT_ENTRIES)."""
    if not has_effect(page_object):
        return dict(entries)
    start = min(P_EFFECT_ENTRIES)
    moved = {entry + EFFECT_ENTRIES * (entry >= start): value for entry, value in entries.items()}
    return {**moved, **P_EFFECT_ENTRIES}


def p_table(module, page_object, project) -> dict:
    """Returns the entries on P of the component `page_object`, whose
    type's module is `module`: its P_ENTRIES (p_component_entries), with a
    font's highest the project's last font, and the highest of each
    attribute of its P_LAST_RESOURCE, as a gmov's vid, the project's last
    resource of that kind, -1 when it has none. A text's code (P_TEXTS) is
    its room in memory, its maxl + 1, shifted up one byte, above the code
    its P_ENTRIES gives (0x3F). An entry that gives its value itself
    (FixedValue) gives its attribute's value."""
    table = with_p_effect(module.P_ENTRIES, page_object)
    rooms = {attribute: maxl for attribute, maxl, _ in p_texts(module).values()}
    last_of = {"font": "font", **getattr(module, "P_LAST_RESOURCE", {})}
    for entry, (name, at, highest, lowest, code) in table.items():
        if name in last_of:
            last = project.resource_count(last_of[name]) - 1
            table[entry] = (name, at, last, lowest, code)
        elif name in rooms:
            maxl = number_from_bytes(page_object.attribute(rooms[name]))
            table[entry] = (name, at, 0, 0, (maxl + 1) << 8 | code)
        elif isinstance(at, FixedValue) and page_object.attribute(name) is not None:
            table[entry] = (name, FixedValue(number_from_bytes(page_object.attribute(name))),
                            highest, lowest, code)
    return table


def p_entries_by_value(entry_of: dict, names: dict, places: dict) -> dict:
    """Returns a variant's P_ENTRIES, for a type whose entries keep T's
    numbers on P while its values lie in one layout for every variant.

    `entry_of` gives each value's entry number on T, {value: entry within
    the type}. `places` gives each value's place on P, {value: (place,
    highest, lowest, code)}. `names` gives the attribute of a value whose
    attribute depends on the variant, as {"background": "pic"}; any other
    value is its own attribute. A value `places` lacks has no entry on P.
    The entries every drawn component has come first. A picture's highest
    is set later, by p_table (P_LAST_RESOURCE)."""
    entries = dict(P_DRAWN_ENTRIES)
    for value, entry in entry_of.items():
        if value in places:
            entries[entry] = (names.get(value, value),) + places[value]
    return entries


def code_entry(module, page_object, name: str, series: str) -> int:
    """Returns the number, within its type, of the entry that code names for
    the attribute `name` of the component `page_object`, which `module`
    describes (object_module), on the series `series`. Code may name only
    an attribute the type's attribute_place takes: raises KeyError for
    another.

    On T and K, the number is attribute_place's. On P and E, a type that
    gives P_ENTRIES numbers its entries as they do, after its effect moves
    them (with_p_effect). Most keep T's numbers there, but some do not, as
    a gauge's. An attribute its P_ENTRIES lacks takes its number from its
    P_CODE_ENTRIES, or is refused: its number on T would name another
    entry there."""
    entry = module.attribute_place(name)
    if series not in SERIES_WRITTEN_AS_P or not hasattr(module, "P_ENTRIES"):
        return entry
    code_entries = getattr(module, "P_CODE_ENTRIES", {})
    named = {**module.P_ENTRIES, **{number: (attribute,)
                                    for attribute, number in code_entries.items()}}
    for number, (attribute, *_) in with_p_effect(named, page_object).items():
        if attribute == name:
            return number
    raise KeyError(name)


def p_texts(module) -> dict:
    """Returns the texts a component of the type `module` keeps on P after
    its page's components' memory (P_TEXTS), or {} for a type without."""
    return getattr(module, "P_TEXTS", {})


def p_text(module, page_object, attribute: str, maxl: str) -> bytes:
    """Returns the room on P of `page_object`'s text `attribute`: its value,
    then zeros, its `maxl` attribute + 1 bytes, the whole rounded up to a
    multiple of 4, as a txt's on T (with_txt). Where `maxl` is 0 and its
    type's module, `module`, gives another attribute for it in
    P_ROOMS_WHEN_ZERO, that one gives the room, as a sliding text's
    txt_maxl does for its path_m."""
    if attribute_number(page_object, maxl) == 0:
        maxl = getattr(module, "P_ROOMS_WHEN_ZERO", {}).get(maxl, maxl)
    return with_txt(b"", page_object, attribute, maxl)


def p_component_entries(table: dict, count: int, place: ObjectPlace,
                        owner_tops: dict = None, owner: int = None) -> bytes:
    """Returns a component's `count` entries on P, each a place in its
    memory, from its base, as its type's `table` gives it, {entry: (name,
    place, highest, lowest, code)} (ResearchNotes/tft/p-series.md). A text's
    entry gives where that text lies, place.text_places (P_TEXTS).
    `owner_tops`, {name: byte}, its type's P_OWNER_TOPS, gives the top byte
    of the owner field of the entries of those attributes (packed_entries).
    It is keyed by name, so it follows an entry that an effect moves
    (with_p_effect). `owner`, its type's P_OWNER, gives every entry's owner
    in place of its ID and its page's, as a variable's 0xFFFF. An entry
    whose place is a FixedValue gives that value as it is."""
    texts = place.text_places or {}
    tops = {entry: owner_tops[name] for entry, (name, *_) in table.items()
            if name in (owner_tops or {})}

    def value(name: str, at: int) -> int:
        if name in texts:
            return texts[name]
        return at if isinstance(at, FixedValue) else place.base + at
    return packed_entries({entry: (value(name, at), highest, lowest, code)
                           for entry, (name, at, highest, lowest, code) in table.items()},
                          count, place, owner=owner, owner_tops=tops)


def p_memory_extras(module, page_object, project, place: ObjectPlace) -> dict:
    """Returns the bytes of a component's memory on P that no entry gives,
    {place: bytes}, as p_component_memory takes them. For each of its texts
    (P_TEXTS), they give the attribute that sets its room, such as its
    txt_maxl, and where the text lies, from place.text_places. Then they give
    what its type's module, `module`, adds (p_memory_extras), such as a
    gmov's buffer. Such bytes may lie within the head the memory starts
    with, as a hotspot's two zeros at 32 and 34 do."""
    extras = {}
    for at, (attribute, maxl, maxl_at) in p_texts(module).items():
        # A text's room is written here for a type whose room has no entry,
        # as the external picture's path_m. A txt_maxl's entry writes the
        # same bytes.
        extras[maxl_at] = (page_object.attribute(maxl) or b"")[:2].ljust(2, b"\x00")
        extras[at] = struct.pack("<I", place.text_places[attribute])
    if hasattr(module, "p_memory_extras"):
        extras.update(module.p_memory_extras(page_object, project, place))
    return extras


def p_component_memory(page_object, head: bytes, table: dict, size: int,
                       extras: dict = None) -> bytes:
    """Returns a component's memory on P, `size` bytes: `head`, what its
    record's head holds, then each value that its type's `table`
    (p_component_entries) places past the head, as the page file holds
    it, in the bytes its entry's code gives, its second hexadecimal digit;
    then `extras`, {place: bytes}, which no entry gives, as the place of a
    text's txt. The other bytes are zeros. A type's texts (P_TEXTS) lie
    after the page's components' memory, not in it, and an entry that gives
    its value itself (FixedValue) has no bytes in it."""
    memory = bytearray(size)
    memory[:len(head)] = head
    for name, at, _, _, code in table.values():
        if not isinstance(at, FixedValue) and at >= len(head) and name != "txt":
            width = code >> 8 & 0xF
            memory[at:at + width] = ((page_object.attribute(name) or b"") + bytes(width))[:width]
    for at, data in (extras or {}).items():
        memory[at:at + len(data)] = data
    return bytes(memory)


# The series whose user code the Nextion Editor writes as P's: P, and E,
# whose files differ from P's in their screen and their firmware alone
# (ResearchNotes/tft/e-series.md). Every P test that decides bytes or what the
# rules cover tests membership in it.
SERIES_WRITTEN_AS_P = ("P", "E")
TXT_MAXL_WORDS = ("any value, written as it is, at least its txt's length; nxwright's build "
                  "refuses a page that lacks the memory for it")
# The words of a txt's rule (text_fits).
TXT_WORDS = "a text of any characters, up to its txt_maxl in bytes"


# The words of the rules of a component's x, y, w, and h (place_fits_its_record).
PLACE_WORDS = ("x, y, w, and h from 0 to 32767, with the right and bottom edges, x + w - 1 "
               "and y + h - 1, at most 32767 too, as the component's record stores each in 2 "
               "signed bytes")
# The most a signed 2 bytes store.
_MOST_IN_2_BYTES = 0x7FFF


def place_fits_its_record(need) -> bool:
    """Whether the place and size of the component of the attribute `need`
    fit in its record. The record stores the x, the y, the w, the h, and the
    right and bottom edges, x + w - 1 and y + h - 1, in 2 signed bytes each
    (frame._record_head). nxwright's build refuses a component past the
    screen on T, K, and F, and one narrower or lower than 2, as the Nextion
    Editor does. nxwright writes any other place as it is."""
    x, y, w, h = (int.from_bytes(need.context[name], "little", signed=True)
                  for name in ("x", "y", "w", "h"))
    return (min(x, y, w, h) >= 0 and x + w - 1 <= _MOST_IN_2_BYTES
            and y + h - 1 <= _MOST_IN_2_BYTES)


def from_to(low: int, high: int):
    """Returns a rule's check that the value of the attribute it checks is
    from `low` to `high`."""
    return lambda need: low <= number_from_bytes(need.value) <= high


# The words of a sta's rule (sta_covered).
STA_WORDS = ("0, a crop of a picture, 1, a colour, or 2, a picture; and on P and E 3 too, "
             "nothing behind it, its entry's highest there, which nxwright's build refuses on "
             "T, K, and F")


def sta_covered(need) -> bool:
    """Whether the sta `need` is one the Nextion Editor compiles: from 0 to
    2, and on P and E 3 too, which puts nothing behind the component."""
    return from_to(0, 3 if need.series in SERIES_WRITTEN_AS_P else 2)(need)


# The words and the range of each attribute whose rule is the same for every
# type that has it, or None for one that takes any value that fits in its
# bytes, which nxwright writes as it is (value_rule).
_AS_IT_IS = "any value that fits in its byte, written as it is"
_COLOUR_RANGE = ("any colour, from 0 to 65535", 0, 0xFFFF)
_VALUE_RANGES = {
    **{name: _COLOUR_RANGE for name in ("bco", "bco1", "bco2", "borderc", "gdc", "pco",
                                        "pco0", "pco1", "pco2", "pco3")},
    "borderw": ("from 0 to 255", 0, 255),
    "xcen": ("any value, written as it is", None, None),
    "ycen": ("any value, written as it is", None, None),
    "isbr": (_AS_IT_IS, None, None), "pw": (_AS_IT_IS, None, None),
    "spax": ("from 0 to 255", 0, 255), "spay": ("from 0 to 255", 0, 255),
    "lenth": ("any value, written as it is", None, None), "format": (_AS_IT_IS, None, None)}


def value_rule(name: str) -> tuple:
    """Returns the words and the check of the rule of the attribute `name`,
    that its value is from its range (_VALUE_RANGES), or any value when the
    range is None, for a type's Rule."""
    words, low, high = _VALUE_RANGES[name]
    return words, (lambda need: True) if low is None else from_to(low, high)


def _style_covered(highest: int):
    """Returns the check of a need of a style: one of 0 to `highest`, at any
    sta. With a picture or a crop behind it, the Nextion Editor draws no
    border, but a style of 1 gives its border's entries all the same, which
    each type's variant writes."""
    return lambda need: 0 <= number_from_bytes(need.value) <= highest


def border_and_background_rules(button: bool = False) -> list:
    """Returns the name, the words, the check, and the reason of each rule of
    a text's, a number's, or an xfloat's border and of what lies behind it,
    as their probes matched them on T, K, P, and E, for a type's Rule: a sta
    of 0 to 2, and on P and E 3 too (sta_covered); a style of 0 to 3, which
    draws no border at a sta other than 1; any borderc; a borderw from 0 to
    255; and any pic and picc. A `button` takes a style of 4 too, raised and
    sunken while it is pressed, and a pic2 and a picc2, which it shows while
    it is pressed."""
    picture = ("any value from 0 to 65535, written as it is: a picture of the project, or "
               "65535 for none")
    if button:
        styles = ("0, no border, 1, a border of its borderc and borderw, 2 or 3, a 3D border, "
                  "sunken or raised, or 4, a 3D border, raised, and sunken while it is pressed, "
                  "at a sta of 1; at another sta, none draws a border, and 1 gives its "
                  "border's entries all the same")
    else:
        styles = ("0, no border, 1, a border of its borderc and borderw, or 2 or 3, a 3D "
                  "border, sunken or raised, at a sta of 1; at another sta, none draws a border, "
                  "and 1 gives its border's entries all the same")
    # Its sta and style pick how the compile draws it. The build refuses
    # any other value, and the compile has no way to draw one.
    parts = [("sta", STA_WORDS, sta_covered, INVALID_VALUE),
             ("style", styles, _style_covered(4 if button else 3), INVALID_VALUE)]
    parts += [(name, *value_rule(name), None) for name in ("borderc", "borderw")]
    # A picture's ID is 2 bytes in memory, written as it is, whichever
    # picture it is, and only at the sta that shows it.
    pictures = ("pic", "picc") + (("pic2", "picc2") if button else ())
    return parts + [(name, picture, lambda need: True, None) for name in pictures]


# The words of the styles of a type of P, by its highest style.
_P_STYLES = {1: "0, flat, or 1, a border of one colour",
             3: "0, flat, 1, a border of one colour, 2, sunken, or 3, raised"}


def p_border_and_background_rules(highest_style: int = None) -> list:
    """Returns the name, the words, the check, and the reason of each rule of
    the border of a component of a type of P, and of what lies behind it,
    for a type's Rule. The probes of the combo box, the data record, the
    file browser, the select, and the sliding text matched them on P and E.
    The rules take a sta of 0 to 3 and any pic and picc. With
    `highest_style`, they take a style from 0 to it, any borderc, and a
    borderw from 0 to 255; a type whose border has rules of its own gives
    none."""
    picture = ("any value from 0 to 65535, written as it is: a picture of the project, or "
               "65535 for none")
    # Its sta and style pick how the compile draws it. The build refuses
    # any other value, and the compile has no way to draw one.
    parts = [("sta", "0, a crop of a picture, 1, a colour, 2, a picture, or 3, nothing behind "
              "it", from_to(0, 3), INVALID_VALUE)]
    parts += [(name, picture, lambda need: True, None) for name in ("pic", "picc")]
    if highest_style is not None:
        parts.append(("style", _P_STYLES[highest_style], from_to(0, highest_style),
                      INVALID_VALUE))
        parts += [(name, *value_rule(name), None) for name in ("borderc", "borderw")]
    return parts


def attribute_number(page_object, name: str) -> int:
    """Returns the value of `page_object`'s attribute `name`, a number, as
    its page file gives it."""
    return number_from_bytes(page_object.attribute(name))


def text_fits(need) -> bool:
    """Whether the txt of the attribute `need` holds no more bytes than its
    txt_maxl, the room it is written in. Its characters are not checked:
    nxwright writes a txt's bytes as they are, so it writes any character
    nxwright's build gives it."""
    return len(need.value) <= number_from_bytes(need.context["txt_maxl"])


@lru_cache(maxsize=None)
def codec_of(encoding: str) -> TextCodec:
    """Returns the codec of the encoding named `encoding`, made once."""
    return TextCodec(encoding)


def text_in_room(room: str):
    """Returns a rule's check that the text of the attribute it checks holds
    no more bytes than its `room` attribute, the room it is written in. It
    checks the texts of the data record, the file browser, the select, the
    combo-box, and the sliding text, and the paths of the external picture,
    the gmov, the video, and the audio. As with a txt (text_fits), nxwright
    writes their bytes as they are, so their characters are not checked."""
    return lambda need: len(need.value) <= number_from_bytes(need.context[room])


def room_covered(text: str, high: int, low: int = 1):
    """Returns a rule's check that the room of the attribute it checks is
    from `low` to `high`, and its text `text` fits it. A text at its default
    has no need of its own, so its room's checks it."""
    def covered(need) -> bool:
        room = number_from_bytes(need.value)
        return low <= room <= high and len(need.context.get(text) or b"") <= room
    return covered


def txt_maxl_covered(need) -> bool:
    """Whether the object's txt fits the txt_maxl of the attribute `need`.
    A txt at its default, such as "newtxt", has no need of its own, so its
    txt_maxl's checks it: the Nextion Editor refuses a txt longer than its
    txt_maxl. The txt_maxl itself is written as it is. A txt longer than
    its txt_maxl does not fit in the room the txt_maxl gives it, so a rule
    with this check refuses for that reason (matching.DOES_NOT_FIT)."""
    return len(need.context.get("txt") or b"") <= number_from_bytes(need.value)


def with_txt(values: bytes, page_object, attribute: str = "txt",
             maxl: str = "txt_maxl") -> bytes:
    """Returns `values`, the object's starting values before its text, then
    its txt, padded with zeros to txt_maxl + 1 bytes, the whole padded with
    zeros to a multiple of 4. `attribute` and `maxl` name another text and
    the attribute that gives its room, such as path and path_m."""
    room = number_from_bytes(page_object.attribute(maxl)) + 1
    found = values + (page_object.attribute(attribute) or b"").ljust(room, b"\x00")
    return found + bytes(-len(found) % 4)


def border(area: bytes, first: int, second: int, series: str) -> bytes:
    """Returns the block of the command on `series` that draws a component's
    3D border: `area`, its place and size as text, each followed by a comma,
    then the colours `first` and `second` as values, then 1."""
    return (_BORDER[series] + area + value_operand(first) + b"," + value_operand(second)
            + b",1")


def flat_border(area: bytes, colour: bytes, width: bytes, series: str) -> bytes:
    """Returns the block of the command on `series` that draws a component's
    border of one colour, as a style of 1 gives it: `area`, its place and
    size as text, each followed by a comma, then the operand `colour` twice,
    as the colour of each side, then the operand `width`, its width."""
    return _BORDER[series] + area + colour + b"," + colour + b"," + width


def zstr(operand: bytes, series: str, area: list = None) -> bytes:
    """Returns the block of zstr on `series`, which draws the text of the
    entry `operand`: at the four operands of `area`, as a scrolling text
    gives its position, or else in the area the setbrush before it set,
    32767 each."""
    area = area or [value_operand(_ZSTR_NUMBER)] * 4
    return _ZSTR[series] + b"".join(part + b"," for part in area) + operand


def background_fill(page_object, project, place) -> list:
    """Returns the blocks that draw the component's page's background over
    the component's area: a fill with the page's bco, or the part of the
    page's pic under it, with xpic. A page with no background gives none."""
    x, y, w, h = place_and_size(page_object)
    page = project.pages[place.page].objects[0]
    background = entry_operand(place.page_entry + page_entry(page, PAGE_BACKGROUND_ENTRY))
    sta = page_sta(page)
    if sta == NO_BACKGROUND:
        return []
    if sta == PICTURE:
        return [XPIC + b"%d,%d,%d,%d,%d,%d," % (x, y, w, h, x, y) + background]
    return [FILL + b"%d,%d,%d,%d," % (x, y, w, h) + background]


def page_sta(page) -> int:
    """Returns the sta of the page `page`, the page's own object: what lies
    behind it (NO_BACKGROUND, COLOUR, or PICTURE)."""
    return attribute_number(page, "sta")


def page_entries(page) -> int:
    """Returns the number of the entries of the page `page`, the page's own
    object. A page with no background has no entry of a bco or a pic, so
    its entries after its sta's are one down, and it has one fewer. A page
    with an effect has two more (EFFECT_ENTRIES)."""
    return (PAGE_ENTRIES - (page_sta(page) == NO_BACKGROUND)
            + EFFECT_ENTRIES * has_effect(page))


def page_entry(page, number: int) -> int:
    """Returns the number the page `page` gives its entry `number`, of a
    page without an effect: two on from its sta's, entry 23, for a page
    with one (EFFECT_ENTRIES)."""
    moved = number >= _PAGE_EFFECT_START and has_effect(page)
    return number + EFFECT_ENTRIES * moved


# A page's entries on P, by entry, each with the attribute whose value it
# gives, which the record's slots give in the order of the first block's
# table: (name, offset, highest, lowest, code). The frame writes them
# (frame._p_page_entries), and code names them (statements.page_code_entry).
P_PAGE_ENTRIES = {
    0: ("type", 0, 255, 0, 0x121), 1: ("id", 1, 255, 0, 0x121), 3: ("vscope", 2, 1, 0, 0x121),
    9: ("x", 40, 6000, -6000, 0x22B), 10: ("y", 42, 6000, -6000, 0x22C),
    11: ("w", 44, 2000, -2000, 0x22D), 12: ("h", 46, 2000, -2000, 0x22E),
    13: ("endx", 48, 0x7FFF, -0x8000, 0x228), 14: ("endy", 50, 0x7FFF, -0x8000, 0x228),
    15: ("effect", 52, 10, 0, 0x131), 19: ("up", 56, 255, 0, 0x131),
    20: ("down", 57, 255, 0, 0x131), 21: ("left", 58, 255, 0, 0x131),
    22: ("right", 59, 255, 0, 0x131), 23: ("sta", 60, 2, 0, 0x121)}
# The attribute a page keeps as its background, by its sta: its bco, or its
# pic. A page with no background keeps 0, and has no entry of either.
PAGE_BACKGROUND_NAMES = {COLOUR: "bco", PICTURE: "pic"}


def p_page_named_entries(page) -> dict:
    """Returns the page `page`'s entry for each attribute name on P, its
    background's among them (PAGE_BACKGROUND_NAMES), and its first's and
    its time's with an effect (with_p_effect)."""
    named = {name: entry for entry, (name, *_) in with_p_effect(P_PAGE_ENTRIES, page).items()}
    name = PAGE_BACKGROUND_NAMES.get(page_sta(page))
    if name:
        named[name] = page_entry(page, PAGE_BACKGROUND_ENTRY)
    return named


def has_effect(page_object) -> bool:
    """Whether the object `page_object` comes into view with an effect as
    its page opens: an effect other than 0."""
    effect = page_object.attribute("effect")
    return effect is not None and number_from_bytes(effect) != 0


def place_and_size(page_object) -> tuple:
    """Returns the object's x, y, width, and height, from its attributes."""
    return tuple(int.from_bytes(page_object.attribute(name), "little", signed=True)
                 for name in ("x", "y", "w", "h"))


@lru_cache(maxsize=None)
def type_module(type_name: str):
    """Returns the module of the component type `type_name`, or None when
    nxwright has no module for it. A dash in a type's name, as in
    "scrolling-text", is an underscore in its module's. Each type's module
    is found once and kept, as it does not change while nxwright runs, and a
    compile needs one for each object, again and again."""
    module = type_name.replace("-", "_")
    if not module.isidentifier() or importlib.util.find_spec("%s.%s" % (__name__, module)) is None:
        return None
    return importlib.import_module("%s.%s" % (__name__, module))


def object_module(page_object):
    """Returns what describes the component `page_object`: its type's module,
    or what the module's variant gives for it when the module has one.
    Returns None when nxwright has no module for its type. A project's
    Component keeps what describes it, worked out the first time, as a
    compile needs it again and again. Another object is described on each
    call."""
    if isinstance(page_object, Component):
        if page_object.description is NOT_DESCRIBED:
            page_object.description = _described(page_object)
        return page_object.description
    return _described(page_object)


def _described(page_object):
    """Works out what describes `page_object`, as object_module gives it."""
    module = type_module(type_name(page_object))
    if module is not None and hasattr(module, "variant"):
        module = module.variant(page_object)
    if module is not None and has_effect(page_object):
        return _WithEffect(module)
    return module


class _WithEffect:
    """What describes a component with an effect: `described`, its type's
    module or variant, but for two empty entries more at its entry 19
    (EFFECT_ENTRIES). Its entries from 19 on, which every drawn type's own
    are, are numbered two on, so its drawing and its code are written with
    a first entry two on. Its entries 0 to 14, those every object drawn
    has (object_entries), keep their numbers in its data, its record, and
    code, as no drawing names them. Its other members are its type's."""

    def __init__(self, described):
        self._described = described
        self.ENTRIES = described.ENTRIES + EFFECT_ENTRIES

    def __getattr__(self, name: str):
        if name == "_described":
            # Not set yet, as in a copy being made: looked up here, it would
            # call this again.
            raise AttributeError(name)
        member = getattr(self._described, name)
        if name not in _WRITTEN_FROM_THE_FIRST_ENTRY:
            return member

        def moved(*arguments):
            # Its place is moved, wherever it lies among the arguments.
            return member(*(replace(argument, first_entry=argument.first_entry + EFFECT_ENTRIES)
                            if isinstance(argument, ObjectPlace) else argument
                            for argument in arguments))
        return moved

    def data(self, page_object, project, place) -> bytes:
        """Returns its type's entries, with two empty ones at entry 19."""
        data = self._described.data(page_object, project, place)
        at = ENTRY.size * OWN_ENTRIES_START
        return data[:at] + bytes(ENTRY.size * EFFECT_ENTRIES) + data[at:]

    def record_slots(self) -> dict:
        return {slot: self._moved(entry)
                for slot, entry in self._described.record_slots().items()}

    def attribute_place(self, name: str) -> int:
        return self._moved(self._described.attribute_place(name))

    @staticmethod
    def _moved(entry: int) -> int:
        return entry + EFFECT_ENTRIES * (entry >= OWN_ENTRIES_START)


# The members of a type's module that write blocks from its first entry,
# which a component with an effect gives them two on (_WithEffect).
_WRITTEN_FROM_THE_FIRST_ENTRY = frozenset({"drawing", "load_start", "event_start",
                                           "load_blocks", "event_blocks"})

# What lies behind a component of a type of P, by its sta, when it is not a
# colour, its sta of 1: a crop of a picture, a picture, or nothing; and the
# attribute whose entry, in its colour's place, gives it, none for nothing
# behind it.
_P_BACKGROUNDS = {0: "picc", 2: "pic", 3: None}
# A border of one colour: its style, and the entries of its colour and its
# width, just before its font's entry, by (name, place from its base,
# highest, lowest, code).
P_BORDERED = 1
P_BORDER_ENTRIES = (("borderc", 58, 0xFFFF, 0, 0x232), ("borderw", 60, 255, 0, 0x131))


def with_p_background(described, page_object):
    """Returns what describes `page_object`, a component of a type of P
    whose entries at a sta of 1, a colour, `described`, its type's module
    or variant, gives: `described` itself at a sta of 1; at another sta,
    its entries as _WithPBackground changes them. A sta its rules refuse,
    past 3, is described as one of a colour, so that its rule refuses it."""
    sta = attribute_number(page_object, "sta")
    return _with_p_background(described, sta) if sta in _P_BACKGROUNDS else described


@lru_cache(maxsize=None)
def _with_p_background(described, sta: int):
    return _WithPBackground(described, _P_BACKGROUNDS[sta])


def with_p_border(described, page_object):
    """Returns what describes `page_object`, a component of a type of P
    whose entries without a border of one colour `described` gives:
    `described` itself, but at a style of 1, a border of one colour, its
    entries as _WithPBorder changes them, whatever its sta."""
    bordered = attribute_number(page_object, "style") == P_BORDERED
    return _with_p_border(described) if bordered else described


@lru_cache(maxsize=None)
def _with_p_border(described):
    return _WithPBorder(described)


class _PEntriesChanged:
    """What describes a component of a type of P whose entries differ from
    those its type's module or variant, `described`, gives, as P_ENTRIES
    and ENTRIES give them. An entry that only code names, in its
    P_CODE_ENTRIES, moves as `moved` moves the entry of that number. Its
    other members are `described`'s."""

    def __init__(self, described, entries: dict, moved):
        self._described = described
        self.P_ENTRIES = entries
        self.ENTRIES = described.ENTRIES + len(entries) - len(described.P_ENTRIES)
        self.P_CODE_ENTRIES = {name: moved(entry) for name, entry
                               in getattr(described, "P_CODE_ENTRIES", {}).items()}
        self._entry_of = {**{name: entry for entry, (name, *_) in entries.items()},
                          **self.P_CODE_ENTRIES}

    def __getattr__(self, name: str):
        if name == "_described":
            # Not set yet, as in a copy being made: looked up here, it would
            # call this again.
            raise AttributeError(name)
        return getattr(self._described, name)

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, as
        its entries or its P_CODE_ENTRIES give it. Raises KeyError for one
        they do not give."""
        return self._entry_of[name]


def _entry_named(entries: dict, name: str) -> int:
    """Returns the number of the entry of `entries`, P_ENTRIES, that gives
    the attribute `name`."""
    return next(entry for entry, (each, *_) in entries.items() if each == name)


class _WithPBackground(_PEntriesChanged):
    """A component of a type of P with another background than a colour, as
    the probes of the combo box, the data record, the file browser, the
    select, and the sliding text on P and E showed: its style has no entry,
    and the entry in its colour's place gives `background`, its picc or its
    pic, or is not there for nothing behind it. Each later entry is numbered
    one less for each entry not there. A picture's highest is the project's
    last picture."""

    def __init__(self, described, background):
        entries = described.P_ENTRIES
        colour = _entry_named(entries, "bco")
        gone = [_entry_named(entries, "style")] + ([colour] if background is None else [])

        def moved(entry: int) -> int:
            return entry - sum(entry > each for each in gone)
        super().__init__(described, {
            moved(entry): (background, *value[1:]) if entry == colour else value
            for entry, value in entries.items() if entry not in gone}, moved)
        self.P_LAST_RESOURCE = {**getattr(described, "P_LAST_RESOURCE", {}),
                                "pic": "picture", "picc": "picture"}


class _WithPBorder(_PEntriesChanged):
    """A component of a type of P with a border of one colour, as the probes
    of the combo box, the select, and the sliding text on P and E showed:
    its border's colour and width have entries just before its font's,
    after its style's and, on a sliding text, the empty entry after it.
    Its font's entry, and each later one, is numbered two on
    (P_BORDER_ENTRIES)."""

    def __init__(self, described):
        entries = described.P_ENTRIES
        font = _entry_named(entries, "font")

        def moved(entry: int) -> int:
            return entry + len(P_BORDER_ENTRIES) * (entry >= font)
        changed = {moved(entry): value for entry, value in entries.items()}
        changed.update({font + number: value for number, value in enumerate(P_BORDER_ENTRIES)})
        super().__init__(described, changed, moved)


def type_name(page_object) -> str:
    """Returns the type's name of `page_object`, as nxwright names it."""
    number = page_object.attribute("type")[0]
    return TYPE_NAMES.get(number, "type %d" % number)


def object_name(page_object) -> str:
    """Returns the name of `page_object`, its objname."""
    return (page_object.attribute("objname") or b"").decode("latin-1")


def first_entries(project) -> dict:
    """Returns {(page ID, object's name): the number of the object's first
    entry} for every object of `project`, the pages' own included. Raises
    NxwrightError for a component whose type has no module, as its number
    of entries is not known."""
    numbers, at = {}, 0
    for page_id, page in enumerate(project.pages):
        for page_object in page.objects:
            numbers[(page_id, object_name(page_object))] = at
            if page_object is page.objects[0]:
                at += page_entries(page_object)
                continue
            module = object_module(page_object)
            if module is None:
                raise NxwrightError("nxwright has no module for the type %s, of %s"
                                    % (type_name(page_object), object_name(page_object)))
            at += module.ENTRIES
    return numbers
