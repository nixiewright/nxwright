"""Reads each page's and each component's attributes back, from its memory,
its entries, its record, and its drawing, as the frame (frame.py) and its
type's module (component_types/) write them.

A component type's decoder is the module of the same name in
decompiling/component_types/, as text.py for a text, with a function
decoded_values(decoded_object, decoded_page, decoded_file). The page's own
decoder is page.py's.

Each decoder also gives the code the Nextion Editor adds for its object by
itself, such as the lines a key adds, so that the source folder leaves it
out. A decoder recognises that code by having the compile's own module
write the code its attributes give, and comparing it with the file.

Every object's record starts with the same head, which the frame writes
(frame._record_head): record_head reads it, for every decoder. On P, an
object's values lie where its named entries say (named_entries), and
p_values reads them, for every decoder on P. E writes its user code as P
does, so P here means E too (decoded_file.py).
"""
from dataclasses import dataclass, field
from functools import partial
import importlib
import importlib.util
import struct

from nxwright.project.attribute_values import number_to_bytes
from nxwright.project.component_defaults import nxwright_defaults
from nxwright.project.page_block import Attribute, PageObject

from nxwright.tft.component_types import (ENTRY, KEYBOARD_PAGES, OWN_ENTRIES_START, P_BORDER_ENTRIES,
                                   code_entry, key_lines, object_module, p_texts)
from nxwright.tft.decompiling import DecodeError, numbers
from nxwright.tft.decompiling.decoded_file import (DRAWN, NO_SLOT, RECORD_HEAD, CodeRun, DecodedFile,
                                            DecodedObject, DecodedPage, slot_names)
from nxwright.tft.frame import P_MOVES_PLACE
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.statements import page_code_entry

# The effect an object with one is given. The file keeps only whether an
# object has an effect, as two more entries, and any effect but 0 compiles
# to the same file.
AN_EFFECT = 1
# The bytes of a number attribute, as nxwright's page objects keep it.
_NUMBER_SIZE = 4
# The names code may give after any object with a place, besides its type's
# attributes (nxwright's attribute_descriptions.type_has).
_FIXED = ("type", "id", "endx", "endy")
# The attributes of an object on P that p_values does not give: its type
# and its ID, which its decoded object gives, and its right and bottom
# edges, which the frame writes from its place and size.
P_VALUES_SKIPPED = ("type", "id", "endx", "endy")
# How an entry's code on P keeps its value (ResearchNotes/tft/p-series.md):
#  - A text's code ends in one of _P_TEXT_CODES. Its entry gives where the
#    text lies, and the code's bits above its last byte give its room, in
#    bytes.
#  - With any other code that has _P_IN_MEMORY set, the value lies in
#    memory, at the place its entry gives. The code's bits 8 to 11 give
#    its size, in bytes, as 2 for 0x232. A page file keeps a number of
#    fewer than 4 bytes unsigned, as nxwright's number_from_bytes reads it.
#    So only a value of 4 bytes is read as signed, and only when its entry
#    takes a value below 0.
#  - A code without it, as a hotspot's 0x111, gives the value in the entry
#    itself (component_types.FixedValue).
_P_TEXT_CODES = (0x2F, 0x3F)
_P_IN_MEMORY = 0x20
# The bytes of a movex, and of a movey after it, in an object's memory on P.
_MOVE_SIZE = 2
# The attributes of a border of one colour, which a bordered style gives.
_BORDER = tuple(name for name, *_ in P_BORDER_ENTRIES)
# The bytes of a text's room on P where no entry gives it, as a gmov's
# path_m (component_types.p_memory_extras).
_ROOM_SIZE = 2


@dataclass
class ObjectValues:
    """What a decoder reads back for an object:

    - `attributes`, {attribute's name: its value}, as a page file gives it:
      a number, or a text, as the bytes the file keeps, in the project's
      encoding. A font, a picture, or another resource is given by its ID.
      An attribute the file does not keep is left out, and the source
      folder gives it its default.
    - `added`, {run's name: (blocks at its start, blocks at its end)}, how
      many blocks of a run of code the Nextion Editor added for the object
      by itself. A run's name is an event's, such as "up"; or "load" for
      what a component adds at the start of its page's load section; or
      "page unload" for what it adds at the end of its page's unload
      event, as a file stream's close. A run the Nextion Editor added
      nothing to is left out."""
    attributes: dict
    added: dict = field(default_factory=dict)


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of `decoded_object`, a component of
    `decoded_page`, from its type's decoder. Raises DecodeError for a type
    with no decoder, and for what that decoder cannot read."""
    # A dash in a type's name, as in "scrolling-text", is an underscore in
    # its module's, as the compile's component_types.type_module finds it.
    name = decoded_object.type_name.replace("-", "_")
    module = "%s.component_types.%s" % (__package__, name)
    if not name.isidentifier() or importlib.util.find_spec(module) is None:
        raise DecodeError("nxwright cannot decode a %s yet" % decoded_object.type_name,
                          record_head(decoded_object).drawing_place, decoded_object.record)
    return importlib.import_module(module).decoded_values(decoded_object, decoded_page,
                                                          decoded_file)


@dataclass
class RecordHead:
    """What the head of an object's record gives: its type, as
    `type_number`; its `object_id`; whether it `is_global`; whether it is
    `drawn`; its place and size, `x`, `y`, `w`, and `h`, which are 0, 0, 1,
    1 for most types that are not drawn; its `sendkey` and its `aph`, 0 and
    127 for an object without them; and, in the user code, where its
    drawing's run lies, `drawing_place`, and its background fill's run,
    `background_fill_place`, 0xFFFFFFFF for an object without one."""
    type_number: int
    object_id: int
    is_global: bool
    drawn: bool
    x: int
    y: int
    w: int
    h: int
    sendkey: int
    aph: int
    drawing_place: int
    background_fill_place: int


def record_head(decoded_object: DecodedObject) -> RecordHead:
    """Returns the head of `decoded_object`'s record."""
    (type_number, object_id, is_global, kind, _, background_fill, _, _, _, _, _, sendkey, aph,
     _, _, x, y, w, h, _, _, drawing) = RECORD_HEAD.unpack_from(decoded_object.record)
    return RecordHead(type_number, object_id, bool(is_global), bool(kind & DRAWN), x, y, w, h,
                      sendkey, aph, drawing, background_fill)


def named_entries(decoded_object: DecodedObject, decoded_file: DecodedFile) -> dict:
    """Returns {attribute's name: the number of its entry, within the
    object's own} of `decoded_object`, on P, whose record gives a slot for
    each name of the file's table of attribute names (frame._component_record),
    or of the type's own names on an older layout (decoded_file.slot_names).
    A slot of 0xFFFF, for an attribute the object lacks, is left out.
    Raises ValueError on T, K, and F, whose records have no such slots."""
    if decoded_file.attribute_names is None:
        raise ValueError("the records of the %s series give no slot by name"
                         % decoded_file.series)
    names = slot_names(decoded_file, decoded_object.type_name)
    slots = struct.unpack_from("<%dH" % len(names), decoded_object.record, RECORD_HEAD.size)
    # A slot counts its entry from its page's first, and the type's slot
    # gives the object's own first entry.
    first = slots[names.index("type")]
    return {name: slot - first for name, slot in zip(names, slots)
            if slot != NO_SLOT and name is not None}


def p_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
             decoded_file: DecodedFile) -> dict:
    """Returns {attribute's name: its value} of `decoded_object`, a page or
    a component of `decoded_page` on P, from each of its named entries
    (named_entries) but P_VALUES_SKIPPED, as its entry's code keeps it:

    - a text, as the bytes at the place its entry gives, up to the first
      zero;
    - a number in memory, as the bytes at the place its entry gives, in
      the size its code gives, signed when it has 4 bytes and its entry's
      lowest is below 0;
    - a number in its entry, as the entry gives it.

    For a type that has a movex, it gives the sendkey too, from the
    record's head, and the movex and the movey, from the head its memory
    starts with (frame.P_MOVES_PLACE). Values that no entry gives, such
    as a gauge's wid, are left to its type's decoder. Raises DecodeError
    when a value does not lie in its page's memory or, for a global
    object, in the int area (memory_at), and ValueError on T, K, and F, as
    named_entries does."""
    values = {}
    for name, number in named_entries(decoded_object, decoded_file).items():
        if name in P_VALUES_SKIPPED:
            continue
        _, value, _, lowest, _, code = ENTRY.unpack(decoded_object.entries[number])
        if code & 0xFF in _P_TEXT_CODES:
            values[name] = memory_at(decoded_object, decoded_page, decoded_file, value,
                                     code >> 8).split(b"\x00", 1)[0]
        elif code & _P_IN_MEMORY:
            size = code >> 8 & 0xF
            values[name] = int.from_bytes(
                memory_at(decoded_object, decoded_page, decoded_file, value, size), "little",
                signed=size == _NUMBER_SIZE and lowest < 0)
        else:
            values[name] = value
    defaults = nxwright_defaults().get(decoded_object.type_number)
    if defaults is not None and "movex" in defaults.names():
        values["sendkey"] = record_head(decoded_object).sendkey
        moves = memory_at(decoded_object, decoded_page, decoded_file,
                          decoded_object.base + P_MOVES_PLACE, 2 * _MOVE_SIZE)
        values["movex"] = int.from_bytes(moves[:_MOVE_SIZE], "little")
        values["movey"] = int.from_bytes(moves[_MOVE_SIZE:], "little")
    return values


def p_kept_style(attributes: dict, bordered: int) -> dict:
    """Returns `attributes`, an object's on P as p_values reads them, with
    its style at `bordered`, its type's style of a border of one colour,
    when its border's entries are there but its style's is not. Behind
    anything but a colour, a style has no entry, but a bordered style still
    gives its border's two, as on T (kept_style)."""
    if "style" not in attributes and all(name in attributes for name in _BORDER):
        return {**attributes, "style": bordered}
    return attributes


def object_memory(decoded_object: DecodedObject, decoded_page: DecodedPage,
                  decoded_file: DecodedFile, size: int) -> bytes:
    """Returns the `size` bytes of `decoded_object`'s starting memory, from
    its base (memory_at)."""
    return memory_at(decoded_object, decoded_page, decoded_file, decoded_object.base, size)


def memory_at(decoded_object: DecodedObject, decoded_page: DecodedPage,
              decoded_file: DecodedFile, place: int, size: int) -> bytes:
    """Returns the `size` bytes of the screen's starting memory at `place`,
    which belong to `decoded_object`, as its memory or a text it keeps
    elsewhere, as a QR code keeps its txt: in the int area for a global
    object, and in its page's memory for any other. Raises DecodeError when
    they do not all lie there."""
    if not record_head(decoded_object).is_global:
        try:
            return decoded_page.memory_at(place, size)
        except IndexError as error:
            raise DecodeError(str(error), record_head(decoded_object).drawing_place,
                              decoded_object.record) from None
    if place + size > len(decoded_file.int_area):
        raise DecodeError("the %d bytes of global object %d from %d are not all in the int area, "
                          "of %d bytes" % (size, decoded_object.object_id, place,
                                           len(decoded_file.int_area)),
                          record_head(decoded_object).drawing_place, decoded_object.record)
    return decoded_file.int_area[place:place + size]


def attribute_of_entry(decoded_file: DecodedFile, number: int) -> tuple:
    """Returns (the DecodedPage, the DecodedObject, the attribute's name) of
    the entry `number`, counted across the project, as an operand of code
    gives it. Which attribute an entry is depends on its object's variant,
    as a text's txt is entry 27 to 30 of its type by its sta and its style,
    so the object's attributes are decoded first (decoded_values). A page's
    own entries are named as code names them (statements.page_code_entry).
    Raises KeyError for an entry no attribute of its object has, as it
    knows no place to give a DecodeError: its caller gives that of the
    operand it read. Raises DecodeError as decoded_values does.

    The names tried are those code may give after the object: its type's
    attributes, as nxwright's component defaults list them, and _FIXED.
    Each is numbered as the statement encoder numbers it."""
    # The page's decoder imports this module, so it is imported here.
    from nxwright.tft.decompiling.page import decoded_page_values
    page, decoded_object = decoded_file.entry_owner(number)
    if decoded_object.object_id == 0:
        candidate = candidate_object(decoded_object.type_number,
                                 decoded_page_values(page, decoded_file).attributes)
        entry = partial(page_code_entry, candidate)
    else:
        candidate = candidate_object(decoded_object.type_number,
                                 decoded_values(decoded_object, page, decoded_file).attributes)
        entry = partial(code_entry, object_module(candidate), candidate)
    defaults = nxwright_defaults().get(decoded_object.type_number)
    for name in (defaults.names() if defaults is not None else []) + list(_FIXED):
        try:
            if entry(name, decoded_file.series) == number - decoded_object.first_entry:
                return page, decoded_object, name
        except KeyError:
            continue
    raise KeyError("no attribute of %s has entry %d" % (decoded_object.name.text, number))


def described(type_number: int, attributes: dict):
    """Returns what the compile's component_types.object_module gives for a
    component of the type `type_number` with `attributes`, {name: number},
    and its other attributes at their defaults (candidate_object): its type's
    module, its variant, or either with an effect. So a decoder asks the
    compile which entries a candidate's attributes give."""
    return object_module(candidate_object(type_number, attributes))


def candidate_object(type_number: int, attributes: dict) -> PageObject:
    """Returns an nxwright page object of the type `type_number` with
    `attributes`, {name: a number or a text's bytes}, which the compile's
    functions read. Any other attribute of the type is its default, as
    nxwright's component defaults give it and the source folder writes it."""
    defaults = nxwright_defaults().get(type_number)
    values = dict(defaults.attributes) if defaults is not None else {}
    values.update({name: number_to_bytes(value, _NUMBER_SIZE) if isinstance(value, int)
                   else value for name, value in attributes.items()})
    return PageObject([Attribute("type", bytes([type_number]))]
                      + [Attribute(name, value) for name, value in values.items()])


def entry_value(decoded_object: DecodedObject, number: int) -> int:
    """Returns the value of `decoded_object`'s entry `number`, within its
    type: an attribute's value, or the place in memory where it lies."""
    return ENTRY.unpack(decoded_object.entries[number])[1]


def has_effect_entries(decoded_object: DecodedObject) -> bool:
    """Whether `decoded_object`'s entries start its type's own with the two
    empty entries an effect gives (component_types.EFFECT_ENTRIES), for a
    type whose own first entry is never empty, as a text's sta."""
    return not any(decoded_object.entries[OWN_ENTRIES_START])


def shared_values(decoded_object: DecodedObject) -> dict:
    """Returns the attributes every drawn component keeps alike, which the
    frame writes: its vscope, place and size, aph, and sendkey, from its
    record's head, and its effect, AN_EFFECT or 0, from its entries
    (has_effect_entries). The effect is right only for a type whose own
    first entry is never empty, as has_effect_entries says."""
    head = record_head(decoded_object)
    return {"vscope": int(head.is_global), "x": head.x, "y": head.y, "w": head.w, "h": head.h,
            "aph": head.aph, "sendkey": head.sendkey,
            "effect": AN_EFFECT if has_effect_entries(decoded_object) else 0}


def has_entry(module, name: str) -> bool:
    """Whether the component that `module` describes (described) has an
    entry of the attribute `name`."""
    try:
        module.attribute_place(name)
    except KeyError:
        return False
    return True


def kept_style(decoded_object: DecodedObject, variant, sta: int, style_at_colour: int,
               compiled):
    """Returns the style the file keeps of `decoded_object`, a text, a
    number, or a type that takes a style as they do, or None when the file
    keeps none. `compiled` is its type's module in the compile, which gives
    its COLOUR, the sta of a colour behind it, and its BORDERED, the style
    of a border of its borderc and borderw. Behind a colour, the style
    draws, and is `style_at_colour`, as its entry or its memory gives it.
    Behind anything else, a style draws as none, but a bordered style gives
    its border's two entries, and any other leaves no trace.
    `variant(sta, style)` describes a candidate (described)."""
    if sta == compiled.COLOUR:
        return style_at_colour
    if len(decoded_object.entries) == variant(sta, compiled.BORDERED).ENTRIES:
        return compiled.BORDERED
    return None


def key_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
               decoded_file: DecodedFile) -> tuple:
    """Returns (the key of the component `decoded_object`, how many blocks
    at the end of its Touch Release event its key added), or (None, 0)
    when its event does not end with a key's lines. A key opens one of
    nxwright's keyboard pages (component_types.KEYBOARD_PAGES), and adds
    the lines component_types.key_lines gives it, which the decoder of code
    reads back here (code.decoded_lines). A key of no keyboard adds no
    lines, so the file does not keep it.

    nxwright's build takes a key on a global component alone, as the
    Nextion Editor does. So a local component's code that ends with such
    lines is its own, and keeps them."""
    # The decoder of code imports this module, so it is imported here.
    from nxwright.tft.decompiling.code import decoded_lines
    run = decoded_object.events.get("up")
    if not record_head(decoded_object).is_global or run is None:
        return None, 0
    expected = {key: key_lines(candidate_object(decoded_object.type_number, {"key": key}),
                               decoded_object.object_id) for key in KEYBOARD_PAGES}
    # Every key adds as many lines.
    count = len(next(iter(expected.values())))
    if len(run.blocks) < count:
        return None, 0
    tail = CodeRun(run.block_places()[-count], run.blocks[-count:])
    try:
        lines = decoded_lines(tail, decoded_page.page_id, decoded_file)
    except DecodeError:
        return None, 0
    return next(((key, count) for key, wanted in expected.items() if lines == wanted),
                (None, 0))


def with_key(attributes: dict, decoded_object: DecodedObject, decoded_page: DecodedPage,
             decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of `decoded_object`, a component of a type
    that takes a key, of `attributes` and its key, when its Touch Release
    event ends with the lines its key adds, which are given as added
    (key_values)."""
    key, added = key_values(decoded_object, decoded_page, decoded_file)
    if key is None:
        return ObjectValues(attributes)
    return ObjectValues({**attributes, "key": key}, {"up": (0, added)})


def p_text_rooms(decoded_object: DecodedObject, decoded_page: DecodedPage,
                 decoded_file: DecodedFile, module) -> dict:
    """Returns {attribute's name: its value} of each attribute that sets the
    room of a text `decoded_object` keeps on P, by its type's or its
    variant's `module`, as a gmov's path_m. The compile writes each in 2
    bytes of the object's memory, at the place its module's P_TEXTS gives
    (component_types.p_memory_extras), whether or not an entry gives it
    too, as a text's txt_maxl's does. So the two agree. Raises DecodeError
    as memory_at does."""
    return {maxl: int.from_bytes(memory_at(decoded_object, decoded_page, decoded_file,
                                           decoded_object.base + at, _ROOM_SIZE), "little")
            for _, maxl, at in p_texts(module).values()}


def p_init_blocks(decoded_object: DecodedObject, decoded_page: DecodedPage,
                  decoded_file: DecodedFile) -> int:
    """Returns how many blocks the Nextion Editor adds at the start of the
    page's load section for `decoded_object` on P: the block of init with
    its ID, as the compile writes it (undocumented_commands.init_block), as
    the version of `decoded_file` numbers it (numbers.as_written). A
    decoder gives the count in its ObjectValues.added, under "load", with
    any other blocks its type adds there. Raises DecodeError when the load
    section lacks the block."""
    block = numbers.as_written(init_block(decoded_object.object_id), decoded_file.series,
                               decoded_file.version)
    if block not in decoded_page.load_section.blocks:
        raise DecodeError("the load section of page %d lacks the init block of its object %d"
                          % (decoded_page.page_id, decoded_object.object_id),
                          decoded_page.load_section.place, block)
    return 1


def p_values_and_rooms(decoded_object: DecodedObject, decoded_page: DecodedPage,
                       decoded_file: DecodedFile) -> dict:
    """Returns {attribute's name: its value} of `decoded_object` on P: its
    values that its named entries give (p_values), with the rooms of the
    texts it keeps (p_text_rooms), as the variant those values give
    describes them, such as a video's from a file. Raises as p_values and
    p_text_rooms do."""
    values = p_values(decoded_object, decoded_page, decoded_file)
    values.update(p_text_rooms(decoded_object, decoded_page, decoded_file,
                               described(decoded_object.type_number, values)))
    return values
