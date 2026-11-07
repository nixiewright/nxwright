"""The decoded file: a TFT file's user code read into its pages, objects,
int variables, macros, and runs of code, which every other decoder reads
(the package's docstring).

It is read with the compile's own reader (tft_file.py), and laid out as the
frame writes it (frame.py, ResearchNotes/tft/user-code-frame.md). It reads the
user code of T, K, and F, which the frame writes alike, and of P and E,
which E writes as P does (ResearchNotes/tft/e-series.md). P's differs from T's
in its memory, which the decoders of its objects read, and in three things
this module reads (ResearchNotes/tft/p-series.md):

- the first block has a fourth region, a table of the attribute names the
  project's objects have, each as its name's checksum;
- a record is its head, then a slot for each of those names, in the
  table's order, not T's fixed slots;
- no object has drawing blocks or a background fill: its drawing is the 0
  word alone.

Each name is the guess whose checksum the file keeps, or a readable name
when no guess matches (the package's docstring). A page's or a
component's guess is the name the Nextion Editor gives a new object of its
type, such as t0 or page1, and an int variable's is sys0 to sys2. A page's
guesses also take the names of nxwright's keyboard pages, such as keybdB,
and a keyboard page's components take the names nxwright gives that
keyboard's, such as loadpageid.

A name the user chose is found where the user code keeps it as text, as
some commands keep the names they are given: `page settings`, or
`click b0,1`. So each word of the user code that could be a name is tried
too, for a page or a component that no other guess matches.
"""
from dataclasses import dataclass, field
from functools import lru_cache
import re
import struct
import tomllib

from nxwright.project.component_defaults import (DEFAULTS_FILE, DERIVED_ATTRIBUTES,
                                                 NAME_PREFIXES, defaults_from_toml)
from nxwright.project.device_settings import ENCODINGS, DeviceSettings
from nxwright.project.editor_limits import NAME_LIMIT
from nxwright.project.object_types import TYPE_NAMES
from nxwright.project.screen_models import model_named, model_with_id
from nxwright.source.keyboards import CHINESE_INPUT, KEYBOARD_PAGES, keyboard

from nxwright.tft import component_types, frame, label_numbers
from nxwright.tft.decompiling import DecodeError, numbers
from nxwright.tft.firmware_versions import MATCHED_VERSIONS, version_text
from nxwright.tft.packaging import (FONT_HEADER, FONT_PLACE_FIELD, LARGE_SECTIONS, MEDIA_HEADER,
                             MEDIA_PLACE_FIELD, MEMORY_FILE_SERIES, MEMORY_FILE_STORAGE_PLACE,
                             ONE_TIME_UPDATE_PLACE, PICTURE_HEADER, PICTURE_PLACE_FIELD,
                             ROTATION_PLACE, SOUND_HEADER)
from nxwright.tft.tft_file import (MACRO_ENTRY_SIZE, VARIABLE_SIZE, TftFile, UserCode, byte_form_crc,
                            encode_blocks, layout_of)


@dataclass
class CodeRun:
    """A run of code's blocks, each without its size word: an event's code,
    program.s's, or a macro's, without the blocks around it, such as the
    event's name and its 0 word. No list of blocks the decoded file gives
    keeps the 0 word that ends it. `place` is where the first block's size
    word lies, counted from the user code's start, which a jump's target is
    counted from too. A run without code has no block, and its place is
    where its first block would be."""
    place: int
    blocks: list

    def block_places(self) -> list:
        """Returns where each block's size word lies, from the user code's
        start."""
        places, at = [], self.place
        for block in self.blocks:
            places.append(at)
            at += 4 + len(block)
        return places


@dataclass
class Name:
    """A name, as the decoded file gives it: `text`, the guess whose checksum
    is `crc`, the one the file keeps, or a readable name when `matched` is
    False."""
    text: str
    crc: int
    matched: bool


@dataclass
class DecodedObject:
    """A page or a component, as its page's blocks, data, and record give
    it:

    - `object_id`, its ID on its page, 0 for the page itself;
    - `type_number`, its type as its record's first byte gives it, and
      `type_name`, nxwright's name for that type, such as "text";
    - `name`, its Name;
    - `is_global`, whether its record marks it as global;
    - `first_entry`, the number of its first entry, counted across the
      project, and `entries`, its entries, 24 bytes each, from its first
      up to the next object's first;
    - `record`, its record's bytes, and `base`, its memory's base, as its
      record gives it. A global object's memory lies in the decoded file's
      int area, and every other object's in its page's memory;
    - `drawing`, the blocks of its drawing, and `background_fill`, those of
      its background fill's run, which ends with the refs of the components
      it overlaps; a page's background fill is empty, and so is that of an
      object that is not drawn, as a variable; on P and E, both are empty
      for every object;
    - `events`, {event's name, such as "down": its CodeRun}, in the order
      its blocks give them. A page's are down, up, and unload: its load
      and loadend events lie in its page's load section."""
    object_id: int
    type_number: int
    type_name: str
    name: Name
    is_global: bool
    first_entry: int
    entries: list
    record: bytes
    base: int
    drawing: list
    background_fill: list
    events: dict


@dataclass
class DecodedPage:
    """A page: `page_id`, its ID; `objects`, its DecodedObject, the page's
    own first, then its components in ID order; `memory_start`, the place
    in the screen's memory of the first byte of `memory`, the block of the
    page's starting memory, from its run to its texts' end, the run being
    0xFF bytes on T, K, and F, and each object's base, 4 bytes each, on P
    and E;
    and `load_section`, the CodeRun of what follows that block: the blocks
    its components add there, its load event's code, the doevents command
    the Nextion Editor adds, and its loadend event's code. The page's
    decoder splits it (page.page_load_runs)."""
    page_id: int
    objects: list
    memory_start: int
    memory: bytes
    load_section: CodeRun

    def memory_at(self, base: int, size: int) -> bytes:
        """Returns the `size` bytes of the page's memory from the place
        `base`, as an object's base gives it. Raises IndexError when they do
        not all lie in the page's memory, as a global object's do not."""
        start = base - self.memory_start
        if start < 0 or start + size > len(self.memory):
            raise IndexError("the %d bytes from %d are not all in page %d's memory, from %d to "
                             "%d" % (size, base, self.page_id, self.memory_start,
                                     self.memory_start + len(self.memory)))
        return self.memory[start:start + size]


@dataclass
class IntVariable:
    """One of program.s's int variables: its Name, and its starting value."""
    name: Name
    value: int


@dataclass
class Macro:
    """A macro: its Name; `label_number`, the number of the "S " block
    that starts it, which the numbers of its labels follow; and `code`, the
    CodeRun of its lines, from the block after that "S " block, where a
    call of the macro jumps, up to the 0 word that ends it. A return in the
    macro is a 0 word too, which does not end its run."""
    name: Name
    label_number: int
    code: CodeRun


@dataclass
class Resource:
    """A resource of the file's resources section: `kind`, "picture",
    "font", or on P and E "animation", "video", or "sound"; its ID; and its size
    in bytes, as its project file's block."""
    kind: str
    resource_id: int
    size: int


@dataclass
class DecodedFile:
    """A TFT file's user code, decoded:

    - `series`, the screen's series, such as "T";
    - `model`, the screen's model as nxwright names it, such as
      NX4832T035;
    - `rotation`, in degrees, and `encoding`, as nxwright names it, such as
      "iso-8859-1";
    - `ints`, program.s's int variables, in the order it declares them,
      which is the order of their values in the int area;
    - `int_area`, the first block's int area, which starts at place 0 of
      the screen's memory: the int variables' values, the global objects'
      memory and texts, then a word, the size of the global objects'
      buffers, which lie between the int area and every page's memory
      (frame._GlobalMemory);
    - `program`, the CodeRun of program.s, without the page 0 command the
      Nextion Editor appends to it;
    - `macros`, in the order their blocks lie, which is the macro tab's;
    - `pages`, in ID order;
    - `resources`, the pictures, the fonts, and on P and E the
      animations, videos, and sounds, in ID order of each kind, which the
      file's section gives, and the user code does not;
    - `one_time_update`, and on P and E `memory_file_storage_size`, the
      device settings that header 1 keeps, but the model, the rotation,
      and the encoding, which the fields above give;
    - `attribute_names`, on P and E, the names of the first block's table of
      attribute names, in its order, which is the order of each record's
      slots. On P of the Nextion Editor 1.63.3, and of those before 1.63,
      which write no such table, the decoded file's own names of their 108
      or 98 slots, None for a slot it does not name. None on T, K, and F;
    - `version`, header 1's version of the Nextion Editor that wrote the
      file, such as (1, 68, 2), which picks how its code is numbered
      (numbers.py)."""
    series: str
    model: str
    rotation: int
    encoding: str
    ints: list
    int_area: bytes
    program: CodeRun
    macros: list
    pages: list
    resources: list = field(default_factory=list)
    attribute_names: list = None
    one_time_update: bool = False
    memory_file_storage_size: int = 0
    version: tuple = min(MATCHED_VERSIONS)

    def entry_owner(self, number: int) -> tuple:
        """Returns (the DecodedPage, the DecodedObject) of the object whose
        entries the entry `number` is among, counted across the project, as
        an operand of code gives it. Raises KeyError for a number past the
        last object's entries."""
        for page in self.pages:
            for decoded_object in page.objects:
                if 0 <= number - decoded_object.first_entry < len(decoded_object.entries):
                    return page, decoded_object
        raise KeyError("no object has entry %d" % number)


# The series whose user code this module reads, and of those, the series
# whose first block has a table of attribute names, those written as P.
_SERIES_READ = ("T", "K", "F", "P", "E")
_SERIES_OF_NAMES = component_types.SERIES_WRITTEN_AS_P
# An entry's size, and a record's on T, K, and F: its head, then its slots
# (frame._record). On P, a record has a 2-byte slot for each attribute name.
_ENTRY_SIZE = 24
_RECORD_SIZE = 232
_P_SLOT_SIZE = 2
# A record's slot on P of an attribute the object lacks.
NO_SLOT = 0xFFFF
# A record's head, as frame._record_head writes it: its type, its ID,
# whether it is global, what it is, the place of its drawing's first block,
# five places of its code, its base, its sendkey and its aph between unread
# bytes, its place and size, and the place of its drawing's run. Of what it
# is, 0x10 marks an object that is drawn (frame._record_kind). Every
# decoder reads it here.
RECORD_HEAD = struct.Struct("<BBBBI5IIxBBx2H6hI")
_TYPE, _ID, _GLOBAL, _KIND, _BASE, _DRAWING = 0, 1, 2, 3, 10, 21
DRAWN = 0x10
# The slot of a record that gives the object's entry 0, its type's, as a
# number counted from its page's first entry. Every object has it.
_TYPE_SLOT = 62
# The first block's regions: the 0 word, the int area, the page list, and
# on P and E the table of attribute names.
_INT_AREA_REGION, _PAGE_LIST_REGION, _NAMES_REGION = 1, 2, 3
# The attribute each slot of a record of P gives, on the Nextion Editor
# 1.63.3, which writes no table of names. There are 108 slots. Each
# attribute that T has too takes T's slot for it (the slot tables of
# component_types/). The attributes that only P has take slots that T's
# records leave free. The probes of 1.63.3 cover each component type it
# offers on P, and their variants, and each with an effect. Every slot they
# fill is named here (ResearchNotes/tft/older-editors.md). None marks a slot
# that no probe or file fills. A component whose drag is 1 fills slot 79,
# its disup, which 1.68.2 does not have. The projects that 1.63.3 and
# 1.60.1 saved list no other attribute that 1.68.2 lacks. On 1.60.1, they
# list a gmov's from as sta, in slot 2 (_P_TYPE_SLOTS_BEFORE_1_63).
_P_SLOTS_OF_1_63 = tuple({
    1: "vscope", 2: "sta", 3: "ch", 4: "bco", 5: "picc", 6: "pic", 7: "gdc", 8: "gdw", 9: "gdh",
    10: "pco0", 11: "pco1", 12: "pco2", 13: "pco3", 14: "mode", 15: "psta", 16: "pco", 17: "pic2",
    18: "wid", 19: "hig", 20: "val", 21: "maxval", 22: "minval", 23: "picc2", 24: "bco2",
    25: "font", 26: "xcen", 27: "ycen", 28: "txt", 29: "txt_maxl", 30: "dez", 31: "bpic",
    32: "ppic", 33: "tim", 34: "en", 36: "picc1", 38: "bco1", 40: "pic1", 41: "lenth", 42: "x",
    43: "y", 44: "endx", 45: "endy", 46: "w", 47: "h", 48: "dir", 49: "id", 50: "vvs0", 51: "vvs1",
    52: "vvs2", 53: "vvs3", 54: "isbr", 55: "dis", 56: "spax", 57: "spay", 58: "pw", 59: "style",
    60: "borderc", 61: "borderw", 62: "type", 64: "format", 65: "vid", 66: "qty", 67: "fps",
    68: "loop", 69: "drag", 70: "aph", 71: "effect", 72: "stim", 73: "first", 74: "up",
    75: "down", 76: "left", 77: "right", 78: "time", 79: "disup", 80: "path", 81: "buffsize",
    82: "filter", 83: "val_x", 84: "maxval_x", 85: "val_y", 86: "maxval_y", 87: "order",
    88: "insert", 89: "clear", 90: "open", 91: "read", 92: "write", 93: "close", 94: "find",
    95: "delete", 96: "from",
}.get(slot) for slot in range(108))
# How many blocks start the user code, before program.s's, in the layouts
# the decoded file reads (tft_file.Layout): 1.68.2's one, 1.63.3's three,
# and the two of the Nextion Editors before 1.63.
_FIRST_BLOCKS_READ = (1, 2, 3)
_FIRST_BLOCKS_OF_1_63, _FIRST_BLOCKS_BEFORE_1_63 = 3, 2
# The slots of a record of P before 1.63: 98, the first 98 of 1.63.3's.
# Each slot the probes of P of the Nextion Editor 1.60.1 fill, of a page
# and of each component type it has, gives the attribute 1.63.3's table
# names there, and they fill every slot that table names among the first
# 98 (ResearchNotes/tft/older-editors.md, P's records).
_P_SLOT_COUNT_BEFORE_1_63 = 98
_P_SLOTS_BEFORE_1_63 = _P_SLOTS_OF_1_63[:_P_SLOT_COUNT_BEFORE_1_63]
# Before 1.63, the slots where one type keeps another attribute than the
# table names there, by type. A gmov keeps its from in slot 2, which gives
# sta on every other type, and leaves slot 96 empty. From 1.63 on, its from
# is in slot 96, as a video's is (ResearchNotes/tft/older-editors.md).
_P_TYPE_SLOTS_BEFORE_1_63 = {"gmov": {2: "from"}}
# The names of a record's slots on P, by how many blocks start the user code
# of the layout (tft_file.Layout), for the layouts without a table of names.
_P_SLOTS_BY_FIRST_BLOCKS = {_FIRST_BLOCKS_OF_1_63: _P_SLOTS_OF_1_63,
                            _FIRST_BLOCKS_BEFORE_1_63: _P_SLOTS_BEFORE_1_63}
# A page list's or an objects' table's row: a name's CRC, then an ID.
_NAMED_ID = struct.Struct("<IH")
# A word of the user code that could be a page's or a component's name.
# Each is tried by its checksum, so a word of no name is harmless.
_WORD = re.compile(rb"[A-Za-z_][A-Za-z0-9_]*")
# The int variables' guesses, those of a new project's program.s, and the
# most numbers tried after a type's prefix, or after "page".
_INT_GUESSES = ("sys0", "sys1", "sys2")
_MOST_NUMBERED = 256
# The kind of each keyboard page nxwright adds, by its page's name.
_KEYBOARD_KINDS = {page: kind for kind, page in KEYBOARD_PAGES.items()}
# The font the Chinese keyboard is laid out in, which nxwright takes from
# the project. It sets the size of its keys' labels, not its components'
# names, which are all the decoder reads of it.
_ANY_FONT = ("font", 16)
# Header 2's place of the encoding's code (tft_file.py). Header 1's places
# of the device settings are packaging's.
_ENCODING = 0x110
# Header 2's place of each kind of resource's number, as (place, shift,
# mask). Header 2 gives two numbers in a word at 0x104, the pictures' in its
# low 2 bytes and the animations' in its high 2, two at 0x108, the videos'
# and the sounds', and the fonts' in a word of their own at 0x10C
# (packaging._header_2).
_COUNTS = {"picture": (0x104, 0, 0xFFFF), "animation": (0x104, 16, 0xFFFF),
           "video": (0x108, 0, 0xFFFF), "sound": (0x108, 16, 0xFFFF),
           "font": (0x10C, 0, 0xFFFFFFFF)}
# The section table's rows of each kind of resource (packaging.py).
PICTURE_ROW, FONT_ROW, ANIMATION_ROW, VIDEO_ROW, SOUND_ROW = 7, 8, 9, 10, 11
# The series whose section has rows of animations, videos, and sounds.
_SERIES_OF_MEDIA = LARGE_SECTIONS


def read_decoded(tft: TftFile) -> DecodedFile:
    """Returns the decoded file of `tft`, a file the compile's reader read:
    its settings and resources, from its headers and its section, and the
    rest, from its user code (decoded_user_code). Raises DecodeError as
    decoded_user_code does, and for a file whose user code the reader could
    not split, or whose model or encoding nxwright does not know."""
    model = model_with_id(tft.device_id)
    if model is None:
        raise DecodeError("no model nxwright knows has this device ID", 0, tft.device_id)
    encoding = ENCODINGS.get(tft.header_2_value(_ENCODING))
    if encoding is None:
        raise DecodeError("header 2 gives an encoding nxwright does not know", 0,
                          struct.pack("<I", tft.header_2_value(_ENCODING)))
    if tft.user_code is None:
        raise DecodeError("the reader could not split the user code: %s"
                          % "; ".join(tft.problems))
    decoded = decoded_user_code(tft.user_code, tft.series, model.name,
                                tft.data[ROTATION_PLACE] * 90, encoding, tft.version)
    decoded.one_time_update = bool(tft.data[ONE_TIME_UPDATE_PLACE])
    if tft.series in MEMORY_FILE_SERIES:
        decoded.memory_file_storage_size = struct.unpack_from(
            "<I", tft.data, MEMORY_FILE_STORAGE_PLACE)[0]
    def counted(kind: str, row: int, header_size: int, place_field: int) -> list:
        return _resources(tft, kind, resource_count(tft, kind), row, header_size, place_field)

    try:
        decoded.resources = (counted("picture", PICTURE_ROW, PICTURE_HEADER, PICTURE_PLACE_FIELD)
                             + counted("font", FONT_ROW, FONT_HEADER, FONT_PLACE_FIELD))
        if tft.series in _SERIES_OF_MEDIA:
            decoded.resources += (
                counted("animation", ANIMATION_ROW, MEDIA_HEADER, MEDIA_PLACE_FIELD)
                + counted("video", VIDEO_ROW, MEDIA_HEADER, MEDIA_PLACE_FIELD)
                + _sounds(tft, resource_count(tft, "sound")))
    except struct.error as error:
        raise DecodeError("the section's resources are not packed as the compile packs them "
                          "(%s)" % error, tft.section_place, b"") from None
    return decoded


def slot_names(decoded: DecodedFile, type_name: str) -> list:
    """Returns the name of the attribute that each slot gives in the record
    of a `type_name` object, on P and E. These are `decoded`'s
    attribute_names, except where the type keeps another attribute in a
    slot on the file's layout (_P_TYPE_SLOTS_BEFORE_1_63)."""
    names = decoded.attribute_names
    if layout_of(decoded.version).first_blocks != _FIRST_BLOCKS_BEFORE_1_63:
        return names
    own = _P_TYPE_SLOTS_BEFORE_1_63.get(type_name, {})
    return [own.get(slot, name) for slot, name in enumerate(names)]


def resource_count(tft: TftFile, kind: str) -> int:
    """Returns the number of resources of `kind` that header 2 of `tft`
    gives: "picture", "font", "animation", "video", or "sound"."""
    place, shift, mask = _COUNTS[kind]
    return tft.header_2_value(place) >> shift & mask


def _resources(tft: TftFile, kind: str, count: int, row: int, header_size: int,
               place_field: int) -> list:
    """Returns the Resource of each of the `count` resources of `kind` in
    the section's part that the table's row `row` gives. The part keeps
    every header first, each of `header_size` bytes, and each header gives,
    at `place_field`, where its resource's rest lies in the part
    (packaging._headers_first)."""
    part = tft.table_part(tft.table[row])
    places = [struct.unpack_from("<I", part, header_size * number + place_field)[0]
              for number in range(count)] + [len(part)]
    return [Resource(kind, number, header_size + places[number + 1] - places[number])
            for number in range(count)]


def _sounds(tft: TftFile, count: int) -> list:
    """Returns the Resource of each of the `count` sounds of the section's
    part of sounds. The part keeps every sound's header first, each giving
    where its sound lies in the part and its size (packaging._sounds)."""
    part = tft.table_part(tft.table[SOUND_ROW])
    sizes = [SOUND_HEADER.unpack_from(part, SOUND_HEADER.size * number)[1]
             for number in range(count)]
    return [Resource("sound", number, size) for number, size in enumerate(sizes)]


def decoded_user_code(code: UserCode, series: str, model: str, rotation: int,
                      encoding: str, version: tuple = min(MATCHED_VERSIONS)) -> DecodedFile:
    """Returns the decoded file of the user code `code`, of a screen of
    `series` and `model`, at `rotation`, in `encoding`, written by the
    Nextion Editor `version`, without resources. The version gives how many
    blocks start the user code before program.s's (tft_file.Layout): one, as
    the frame writes it, three, as the Nextion Editor 1.63.3 does, or two,
    as the Nextion Editors before 1.63 do.
    Raises DecodeError for user code whose layout is not the frame's, such
    as a page whose record is not where its index's entry places it, for a
    series it does not know, and for a `version` later than every matched
    one."""
    if series not in _SERIES_READ:
        raise DecodeError("the user code of the %s series is not decoded" % series)
    # A later Nextion Editor may number its commands differently. Read with
    # 1.68.2's numbers, its code could decode into the wrong commands. Those
    # compile back into the same bytes, so the round trip would not catch the
    # error.
    newest = max(MATCHED_VERSIONS)
    if version > newest:
        raise DecodeError("the file was made by the Nextion Editor %s, but nxwright decompiles "
                          "only files made by the Nextion Editor %s or older. A later version "
                          "may number its commands differently"
                          % (version_text(version), version_text(newest)))
    # A layout not read yet is refused here, not misread, as an older file's
    # folder is written without a round trip to show what went wrong.
    first_blocks = layout_of(version).first_blocks
    if first_blocks not in _FIRST_BLOCKS_READ:
        raise DecodeError("files of the %s series of the Nextion Editor %s lay out their user "
                          "code otherwise, which the decompiler does not read yet"
                          % (series, version_text(version)))
    # The Nextion Editors before 1.68.1 lack 6.cc, E's firmware file
    # (tft_file.firmware_names), so they write no files of E. One on an
    # older layout is refused, as a backstop, rather than read by 1.68.2's
    # numbers of E's code.
    if series == "E" and first_blocks != 1:
        raise DecodeError("a file of the Edge series of the Nextion Editor %s is not read, as "
                          "the Nextion Editors before 1.68.1 write none" % version_text(version))
    # A part too short for what the frame writes there, as in a damaged
    # file, would be read past its end.
    try:
        return _decoded(code, series, model, rotation, encoding, version)
    except (struct.error, IndexError) as error:
        raise DecodeError("the user code is not laid out as the frame writes it (%s)"
                          % error) from None


def _decoded(code: UserCode, series: str, model: str, rotation: int, encoding: str,
             version: tuple) -> DecodedFile:
    """Returns the decoded file decoded_user_code returns."""
    blocks = _Blocks(code)
    first_blocks = layout_of(version).first_blocks
    # The Nextion Editor 1.63.3 writes the first block's first three regions
    # as blocks of their own, and its records' slots without a table of
    # names. The Nextion Editors before 1.63 write the int area and the page
    # list alone, without the 0 word, which stands empty in its place.
    if first_blocks == 1:
        regions = _regions(code.blocks[0])
    else:
        regions = [b""] * (_PAGE_LIST_REGION + 1 - first_blocks) + code.blocks[:first_blocks]
    int_area = regions[_INT_AREA_REGION]
    names = None
    if series in _SERIES_OF_NAMES:
        names = (_attribute_names(code) if first_blocks == 1
                 else list(_P_SLOTS_BY_FIRST_BLOCKS[first_blocks]))
    page_crcs = {page_id: crc for crc, page_id in _NAMED_ID.iter_unpack(
        regions[_PAGE_LIST_REGION])}
    entries = code.index_entries()
    records = _page_records(code, entries, _RECORD_SIZE if names is None
                            else RECORD_HEAD.size + _P_SLOT_SIZE * len(names))
    if names is not None and None in names:
        _refuse_unnamed_slots(code, records, names)
    # Each page's blocks start with its own drawing's, which its record gives.
    starts = [blocks.number_at(RECORD_HEAD.unpack_from(page[0])[_DRAWING]) for page in records]
    starts.append(len(code.blocks))
    macros = _macros(code, blocks, starts[0])
    program = _program(blocks, first_blocks, blocks.number_at(macros[0].code.place) - 1
                       if macros else starts[0], series, version)
    data_start = code.places()["data"][0]
    data_ends = [entry.data_place - data_start for entry in entries[1:]] + [len(code.data)]
    # Every page's memory starts after the int area and the global objects'
    # buffers, whose size the int area's last word gives.
    memory_start = len(int_area) + struct.unpack_from("<I", int_area, len(int_area) - 4)[0]
    words = _words_by_crc(code)
    pages, first_entry = [], 0
    for page_id, (entry, page_records) in enumerate(zip(entries, records)):
        data = code.data[entry.data_place - data_start:data_ends[page_id]]
        page = _page(page_id, page_crcs.get(page_id), entry.table_place, page_records, blocks,
                     starts[page_id + 1], data, first_entry, memory_start,
                     DeviceSettings(model_named(model), rotation, encoding).page_size, names,
                     words)
        first_entry += len(data) // _ENTRY_SIZE
        pages.append(page)
    for page, name in zip(pages, _unique([page.objects[0].name for page in pages])):
        page.objects[0].name = name
    return DecodedFile(series, model, rotation, encoding, _int_variables(code, int_area),
                       int_area, program, macros, pages, attribute_names=names, version=version)


class _Blocks:
    """The user code's blocks, with where each lies."""

    def __init__(self, code: UserCode):
        self.blocks = code.blocks
        self.places = code.block_places() + [len(encode_blocks(code.blocks))]
        self._numbers = {place: number for number, place in enumerate(self.places)}

    def number_at(self, place: int) -> int:
        """Returns the number of the block whose size word lies at `place`,
        or the number after the last block for the place after it. Raises
        DecodeError when no block starts there."""
        if place not in self._numbers:
            raise DecodeError("no block starts where the user code says one does", place, b"")
        return self._numbers[place]

    def run(self, start: int, end: int) -> CodeRun:
        """Returns the CodeRun of the blocks from the number `start` up to,
        but not including, the number `end`."""
        return CodeRun(self.places[start], self.blocks[start:end])

    def zero_word(self, start: int, end: int) -> int:
        """Returns the number of the first 0 word from the block `start`,
        before the block `end`. Raises DecodeError when there is none."""
        for number in range(start, end):
            if not self.blocks[number]:
                return number
        raise DecodeError("a run of blocks has no 0 word to end it", self.places[start],
                          self.blocks[start] if start < end else b"")


def _regions(first_block: bytes) -> list:
    """Returns the regions of the first block, by its head's places and
    sizes (frame._first_block)."""
    count = struct.unpack_from("<I", first_block)[0]
    return [first_block[place:place + size]
            for place, size in struct.iter_unpack("<II", first_block[4:4 + 8 * count])]


def _attribute_names(code: UserCode) -> list:
    """Returns the names of the table of attribute names in `code`'s first
    block, on P and E, in its order, each found by its checksum among the names
    of every attribute nxwright knows. Raises DecodeError for a checksum of
    no such name, and for a table without type, whose slot gives each
    object's first entry."""
    first = code.blocks[0]
    place, size = struct.unpack_from("<II", first, 4 + 8 * _NAMES_REGION)
    # The first block's places are counted from its start, after its size
    # word.
    start = code.block_places()[0] + 4 + place
    known = _known_attribute_names()
    names = []
    for at, (crc,) in enumerate(struct.iter_unpack("<I", first[place:place + size])):
        if crc not in known:
            raise DecodeError("the first block's table of attribute names holds the checksum "
                              "%08X, of no attribute nxwright knows" % crc, start + 4 * at,
                              struct.pack("<I", crc))
        names.append(known[crc])
    if "type" not in names:
        raise DecodeError("the first block's table of attribute names has no type", start,
                          first[place:place + size])
    return names


@lru_cache(maxsize=None)
def _known_attribute_names() -> dict:
    """Returns {the checksum of a name: the name} of every attribute
    nxwright knows: each type's, as its component defaults give them, and
    those it derives, such as objname."""
    defaults = defaults_from_toml(DEFAULTS_FILE.read_text(encoding="utf-8"), DEFAULTS_FILE.name)
    names = set(DERIVED_ATTRIBUTES).union(*(each.names() for each in defaults.values()))
    return {_unpadded_crc(name): name for name in names}


def _int_variables(code: UserCode, int_area: bytes) -> list:
    """Returns the int variables the variables' table gives, in the order
    of their values in the int area, which is the order program.s declares
    them, each with its value there (frame._variable_table)."""
    table = code.variables[:len(code.variables) // VARIABLE_SIZE * VARIABLE_SIZE]
    rows = sorted((offset, crc) for crc, offset, _ in struct.iter_unpack("<III", table))
    return [IntVariable(_guessed(crc, [_by_crc(_INT_GUESSES, _unpadded_crc)],
                                 "int%d" % (offset // 4)),
                        struct.unpack_from("<i", int_area, offset)[0]) for offset, crc in rows]


def _unpadded_crc(name: str) -> int:
    """Returns the CRC of an int variable's, a macro's, or an attribute's
    name, not padded."""
    return byte_form_crc(name.encode("ascii"))


def _padded_crc(name: str) -> int:
    """Returns the CRC of a page's or a component's name, padded."""
    return frame.page_name_crc(name.encode("ascii"))


def _guessed(crc: int, tables: list, readable: str) -> Name:
    """Returns the Name of the CRC `crc` in the first of `tables` that has
    it, each {CRC: name} (_by_crc), or `readable`, unmatched."""
    for table in tables:
        if crc in table:
            return Name(table[crc], crc, True)
    return Name(readable, crc, False)


@lru_cache(maxsize=None)
def _by_crc(guesses: tuple, crc_of) -> dict:
    """Returns {CRC, as `crc_of` gives it: the first of `guesses` of that
    CRC}. The decoder guesses each object's name from the same few lists of
    names, such as t0 to t255, so each list's CRCs are worked out once a
    run."""
    table = {}
    for guess in guesses:
        table.setdefault(crc_of(guess), guess)
    return table


@lru_cache(maxsize=None)
def _numbered(prefix: str) -> tuple:
    """Returns the names the Nextion Editor gives new objects of the name
    prefix `prefix`, such as t0 to t255 for "t", in order."""
    return tuple("%s%d" % (prefix, number) for number in range(_MOST_NUMBERED))


def _page_records(code: UserCode, entries: list, size: int) -> list:
    """Returns each page's records, one for each of its objects, as its
    index's entry counts them, each of `size` bytes. Raises DecodeError
    when the records part holds fewer."""
    records, at = [], 0
    for entry in entries:
        end = at + size * entry.objects
        if not entry.objects or end > len(code.records):
            raise DecodeError("the records end before the page index's objects do",
                              code.places()["records"][0] + at, code.records[at:at + 4])
        records.append([code.records[place:place + size] for place in range(at, end, size)])
        at = end
    return records


def _refuse_unnamed_slots(code: UserCode, records: list, names: list):
    """Raises DecodeError when a record of `records` fills a slot that
    `names` leaves without a name, so that its value is not dropped. Such a
    slot gives an attribute that nxwright does not read yet."""
    at = code.places()["records"][0]
    for record in (record for page in records for record in page):
        slots = struct.unpack_from("<%dH" % len(names), record, RECORD_HEAD.size)
        for slot, (name, value) in enumerate(zip(names, slots)):
            if name is None and value != NO_SLOT:
                raise DecodeError("a record fills slot %d, whose attribute nxwright does not read "
                                  "yet" % slot, at + RECORD_HEAD.size + _P_SLOT_SIZE * slot,
                                  record[:4])
        at += len(record)


def _macros(code: UserCode, blocks: _Blocks, pages_start: int) -> list:
    """Returns the macros, in the order their blocks lie: each an "S " block,
    its lines' blocks, and a 0 word, up to the next macro's "S " block or
    the first page's blocks, the block `pages_start` (frame._macros). A
    macro's name has no guess, so it gets a readable name, such as macro0."""
    table = code.macros[:len(code.macros) // MACRO_ENTRY_SIZE * MACRO_ENTRY_SIZE]
    rows = sorted((place, crc) for crc, place in struct.iter_unpack("<II", table))
    starts = [blocks.number_at(place) for place, _ in rows] + [pages_start]
    macros = []
    for number, (place, crc) in enumerate(rows):
        start, end = starts[number], starts[number + 1]
        first = blocks.blocks[start]
        if not first.startswith(label_numbers.S_BLOCK_START) or blocks.blocks[end - 1]:
            raise DecodeError("a macro does not start with its \"S \" block and end with a 0 "
                              "word", place, first)
        label = struct.unpack_from("<i", first, len(label_numbers.S_BLOCK_START) + 1)[0]
        macros.append(Macro(Name("macro%d" % number, crc, False), label,
                            blocks.run(start + 1, end - 1)))
    return macros


def _program(blocks: _Blocks, start: int, end: int, series: str, version: tuple) -> CodeRun:
    """Returns program.s's run, from the block `start`, after the first
    blocks, up to the block `end`, without the page 0 command and the 0
    word the Nextion Editor `version` appends to it. Raises DecodeError when
    they do not end it."""
    appended = numbers.as_written(frame.APPENDED_PAGE_0[series], series, version)
    if blocks.blocks[end - 2:end] != [appended, b""]:
        raise DecodeError("program.s does not end with the page 0 command the Nextion Editor "
                          "appends", blocks.places[end - 2], b"".join(blocks.blocks[end - 2:end]))
    return blocks.run(start, end - 2)


def _page(page_id: int, page_crc, table_place: int, records: list, blocks: _Blocks, end: int,
          data: bytes, first_entry: int, memory_start: int, page_size: tuple,
          names: list = None, words: dict = None) -> DecodedPage:
    """Returns the page `page_id`, whose name's CRC the page list gives as
    `page_crc`, whose objects' table lies at `table_place`, and whose
    blocks end before the block `end`. `data` is its entries, the first of
    which is the entry `first_entry`, and `page_size` the screen's (width,
    height), at which nxwright lays out a keyboard page. On P, `names` are
    the attribute names its records' slots follow. `words` are the user
    code's words that could be names, by their CRCs (_words_by_crc). Its
    own name is made unlike the other pages' once every page is read
    (decoded_user_code)."""
    table = blocks.number_at(table_place)
    if not table + 1 < end or blocks.blocks[end - 1]:
        raise DecodeError("a page's blocks do not end with its objects' table, its memory, and "
                          "its load section's 0 word", table_place, blocks.blocks[table])
    crcs = {object_id: crc for crc, object_id in _NAMED_ID.iter_unpack(blocks.blocks[table])}
    if page_crc is not None:
        crcs[0] = page_crc
    heads = [RECORD_HEAD.unpack_from(record) for record in records]
    # Each object's blocks run from its drawing's up to the next object's,
    # and the last's up to the objects' table.
    starts = [blocks.number_at(head[_DRAWING]) for head in heads] + [table]
    # Each object's entries run from its first, its type's, which its
    # record's slot gives, up to the next object's first.
    type_slot = _TYPE_SLOT if names is None else names.index("type")
    firsts = [struct.unpack_from("<H", record, RECORD_HEAD.size + 2 * type_slot)[0]
              for record in records] + [len(data) // _ENTRY_SIZE]
    objects, keyboard_names = [], ()
    for object_id, (record, head) in enumerate(zip(records, heads)):
        type_name = TYPE_NAMES.get(head[_TYPE])
        if (type_name is None or head[_ID] != object_id
                or not firsts[object_id] < firsts[object_id + 1]):
            raise DecodeError("a record's type, ID, or first entry is not one the frame writes "
                              "there", 0, record[:4])
        name = _object_name(crcs.get(object_id), head[_TYPE], type_name, object_id, page_id,
                            tuple(_KEYBOARD_KINDS) if object_id == 0 else keyboard_names,
                            words or {})
        if object_id == 0 and name.matched and name.text in _KEYBOARD_KINDS:
            keyboard_names = _keyboard_names(_KEYBOARD_KINDS[name.text], *page_size)
        entries = [data[at:at + _ENTRY_SIZE] for at in range(
            _ENTRY_SIZE * firsts[object_id], _ENTRY_SIZE * firsts[object_id + 1], _ENTRY_SIZE)]
        drawing, fill, events = _object_blocks(blocks, starts[object_id], starts[object_id + 1],
                                               type_name,
                                               names is None and bool(head[_KIND] & DRAWN),
                                               object_id == 0)
        objects.append(DecodedObject(object_id, head[_TYPE], type_name, name, bool(head[_GLOBAL]),
                                     first_entry + firsts[object_id], entries, record,
                                     head[_BASE], drawing, fill, events))
    # A component's name is unlike its page's other components'.
    for decoded_object, name in zip(objects[1:], _unique([each.name for each in objects[1:]])):
        decoded_object.name = name
    return DecodedPage(page_id, objects, memory_start, blocks.blocks[table + 1],
                       blocks.run(table + 2, end - 1))


def _object_name(crc, type_number: int, type_name: str, object_id: int, page_id: int,
                 more: tuple = (), words: dict = None) -> Name:
    """Returns the Name of the object `object_id` of the page `page_id`,
    whose name's CRC is `crc`: one of `more`, the name the Nextion Editor
    gives a new object of its type, its prefix and a number, a word of the
    user code, `words` by their CRCs, or a readable one, its type's name
    and its ID, the type's name cut to fit the 14 bytes the Nextion Editor
    keeps of a name."""
    if object_id == 0:
        prefix, readable = "page", "page%d" % page_id
    else:
        prefix = NAME_PREFIXES.get(type_number)
        number = "%d" % object_id
        readable = type_name.replace("-", "_")[:NAME_LIMIT - len(number)] + number
    if crc is None:
        return Name(readable, 0, False)
    guesses = () if prefix is None else _numbered(prefix)
    name = _guessed(crc, [_by_crc(tuple(more), _padded_crc), _by_crc(guesses, _padded_crc)],
                    readable)
    if not name.matched and crc in (words or {}):
        return Name(words[crc], crc, True)
    return name


def _words_by_crc(code: UserCode) -> dict:
    """Returns {CRC, padded: word} of each word of `code`'s blocks that
    could be a page's or a component's name (_WORD): of ASCII, and no longer
    than the 14 bytes the Nextion Editor keeps of a name. The blocks keep
    such a name where a command keeps it as text, as `page settings` does.
    Each word's CRC is worked out once, whatever the number of objects."""
    words = {match.group().decode("ascii") for block in code.blocks
             for match in _WORD.finditer(block) if len(match.group()) <= NAME_LIMIT}
    return {_padded_crc(word): word for word in sorted(words)}


@lru_cache(maxsize=None)
def _keyboard_names(kind: str, width: int, height: int) -> tuple:
    """Returns the names of the components of nxwright's keyboard page of
    `kind`, a key of nxwright's KEYBOARD_PAGES, laid out on a page `width`
    by `height` pixels, from the page file nxwright writes for it."""
    page = keyboard(kind, width, height, _ANY_FONT if kind == CHINESE_INPUT else None)
    return tuple(table["name"] for table in tomllib.loads(page.page_toml).get("component", []))


def _unique(names: list) -> list:
    """Returns `names`, each readable name that another of them already
    has, or that one of them matched, given one "_" more until it is unlike
    them all. A matched name is kept as it is."""
    taken = {name.text for name in names if name.matched}
    unique = []
    for name in names:
        while not name.matched and name.text in taken:
            name = Name(name.text + "_", name.crc, False)
        taken.add(name.text)
        unique.append(name)
    return unique


def _object_blocks(blocks: _Blocks, start: int, end: int, type_name: str, drawn: bool,
                   is_page: bool) -> tuple:
    """Returns (the drawing's blocks, the background fill's, {event's name:
    its CodeRun}) of an object whose blocks run from the block `start` up
    to the block `end`: its drawing and a 0 word; if it is `drawn`, its
    background fill and a 0 word; then each event of its type, its name,
    its code, and a 0 word (frame._PageLayout). A return in the code is a 0
    word too, so an event's code ends at the 0 word before the next event's
    name. Raises DecodeError for a type nxwright does not write, and for
    blocks that are not laid out so."""
    at = blocks.zero_word(start, end)
    drawing = blocks.blocks[start:at]
    fill, at = [], at + 1
    if drawn:
        fill_end = blocks.zero_word(at, end)
        fill, at = blocks.blocks[at:fill_end], fill_end + 1
    if is_page:
        names = frame.NAMED_EVENTS
    else:
        module = component_types.type_module(type_name)
        if module is None:
            raise DecodeError("nxwright writes no %s" % type_name, blocks.places[start],
                              blocks.blocks[start])
        names = module.EVENTS
    events = {}
    for number, name in enumerate(names):
        if at >= end or blocks.blocks[at] != name.encode("ascii"):
            raise DecodeError("the %s's %s event is not where the frame writes it"
                              % (type_name, name), blocks.places[min(at, end)],
                              blocks.blocks[at] if at < end else b"")
        following = names[number + 1].encode("ascii") if number + 1 < len(names) else None
        code_end = next((place for place in range(at + 1, end) if not blocks.blocks[place]
                         and (following is None and place == end - 1
                              or following is not None and place + 1 < end
                              and blocks.blocks[place + 1] == following)), None)
        if code_end is None:
            raise DecodeError("the %s's %s event has no 0 word to end it" % (type_name, name),
                              blocks.places[at], blocks.blocks[at])
        events[name] = blocks.run(at + 1, code_end)
        at = code_end + 1
    if at != end:
        raise DecodeError("an object's blocks go on past what the frame writes for a %s"
                          % type_name, blocks.places[at], blocks.blocks[at])
    return drawing, fill, events
