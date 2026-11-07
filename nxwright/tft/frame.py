"""The user code's frame: what the user code of every project has, whatever
its components and code. That is the first block (its sizes, the int
variables' starting values, the page list), each page's drawing and data,
each object's events' block, the page index, and the object records' layout,
with each page's own record (tft_file.py gives the user code's parts).

The frame asks each component type's module (component_types/) for the
type's drawing, its data, and its own numbers in its record. It asks the
statement encoder (statements.py) for the blocks of program.s's code, and of
each event's. It makes the compile's context (compile_context.py) once, and
gives it to the encoder, to its page layouts, and to the macros, which find
the tables of the whole project there rather than building them.

So far it writes pages, on T, K, P, and E, and the components of each type
with a module in component_types/, on the series its SERIES gives, as the
Nextion Editor 1.68.2 writes them, with the refs it adds for drawn
components that overlap (overlaps.py). On P, an object has no drawing
blocks and keeps every value in its memory, and its record's slots follow
the first block's table of attribute names (ResearchNotes/tft/p-series.md).
ResearchNotes/tft/user-code-frame.md and each type's note, such as
text-component.md, give each value, and how it was found. The terms it uses:

  - a name's CRC: the byte-form CRC (tft_file.byte_form_crc) of the name's
    bytes. A page's name is first padded with zeros to 14 bytes. A
    variable's name is not padded.
  - the int area: the int variables' starting values, 4 bytes each, in the
    order program.s declares them, then a 0 word. A variable's offset is
    where its value is in that area.
  - an object's memory: its starting values in the screen's memory, past
    the int area: a page's 8 bytes, then each of its components' in turn.
    An object's base is where its memory starts. A page's is past the int
    area and the page's run of 0xFF bytes, one per object, the page
    included, rounded up to a multiple of 4: 20 for the three ints of a new
    project and a page of up to 4 objects.
  - an object's entries: its data, 24 bytes each, 33 for a page, or 32 for
    a page with no background (component_types.page_entries). Each entry
    is six 4-byte numbers: the object's base, a value, its highest and its
    lowest value, the object's ID times 256 plus its page's ID, or 65535
    for a variable, and a code. The entries an object does not use are
    zeros. Entries are numbered across the project
    (component_types.first_entries), and code names an entry by that
    number, as a page's fill does.
  - a slot: a 2-byte number in an object's record. It is the number of one
    of its page's entries, counted from the page's first, or 0xFFFF for
    none.
  - a piece: a run of the user code's bytes that a test checks on its own,
    such as one object's memory (Piece, laid_out). An object's pieces are
    named by its page's ID, its own ID, and what they hold, such as
    "page0-1-memory" for the memory of page 0's object 1, and a page's other
    pieces by its ID, as "page0-texts". On P, an object's memory starts
    with its record's head, which the frame writes, so "page0-1-head" holds
    the head and "page0-1-memory" the values its type writes after it. A
    type's own bytes that lie within the head's, as a hotspot's
    p_memory_extras, are in the head piece.
    Names are of letters, digits, and "-", so that a test names a piece as
    it is written in a probe's table of its fixtures' pieces. The pieces of
    a part cover all of it.
"""
from dataclasses import dataclass, replace
import re
import struct

from nxwright import NxwrightError
from nxwright.project.attribute_values import number_from_bytes, number_to_bytes
from nxwright.project.device_settings import ENCODINGS
from nxwright.project.editor_language import EDITOR_COLOURS, EDITOR_PROGRAM_DECLARATION
from nxwright.project.editor_limits import lacked_attributes
from nxwright.project.page_block import Attribute

from nxwright.tft import component_types, label_numbers, overlaps
from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import (COLOUR, FILL, PAGE_BACKGROUND_ENTRY, PIC, PICTURE,
                                   ObjectPlace, entry_operand, from_to, object_entries,
                                   packed_entries, page_entry, page_sta, place_and_size,
                                   SERIES_WRITTEN_AS_P, two_byte_start,
                                   value_operand, value_rule)
# The match check's own reading of code into lines, so that the frame encodes
# exactly the lines the check checked.
from nxwright.tft.matching import Rule, code_lines
from nxwright.tft.project import Project
from nxwright.tft.reasons import INVALID_VALUE
from nxwright.tft.statements import CodePlace, encode_code as encode_statements, past_ascii_covered
from nxwright.tft.tft_file import UserCode, byte_form_crc, encode_blocks

# An int declaration of program.s: `int`, then one or more names with their
# starting values, such as `int sys0=0,sys1=0,sys2=0`. A line is one when
# it starts with the keyword and a space or a tab; the frame then reads it
# in full, or refuses it. Its indentation and a
# comment after it are gone before the frame reads it: a Project strips them
# from its code as it is made (project.py).
_INT_KEYWORD = re.compile(r"[ \t]*int[ \t]")
_INT_DECLARATION = re.compile(r"int[ \t]+(\S.*)")
# A name, then its value: a decimal, with a sign or leading zeros or not, a
# hexadecimal number, or none, which starts it at 0. The Nextion Editor
# reads spaces around the name, the "=", and the value as none:
# `int e = 5 , f = 6` as `int e=5,f=6`. A name has up to 32 characters. The
# Nextion Editor refuses a longer one ("Illegal global variable name
# length"), which nxwright's build lets through.
_INT_VARIABLE = re.compile(
    r" *([A-Za-z_][A-Za-z0-9_]{0,31}) *(?:= *([+-]?[0-9]+|0[xX][0-9A-Fa-f]+) *)?")
_NAME_SIZE = 14
_INT_RANGE = range(-2 ** 31, 2 ** 31)
# The program.s of the Nextion Editor's new project, which it compiles in
# place of one of no lines, or of blank lines alone. It compiles one of
# comments alone as it is, as no lines.
_NEW_PROJECT_PROGRAM = "\r\n".join((
    EDITOR_PROGRAM_DECLARATION, "baud=9600", "dim=100", "recmod=0",
    "printh 00 00 00 ff ff ff 88 ff ff ff", "page 0", "")).encode("ascii")
# The names the Nextion Editor refuses for an int, which nxwright's build
# lets through: its colours' ("Illegal name"). nxwright's build refuses a
# command's, a system variable's, a page's, and a component's.
_TAKEN_NAMES = frozenset(EDITOR_COLOURS)

# The block the Nextion Editor appends after program.s's last line: `page 0`,
# by series: P numbers `page` its own way.
APPENDED_PAGE_0 = {"T": b"\x09\x0b\x04\x30", "K": b"\x09\x0b\x04\x30", "P": b"\x09\x0c\x04\x30",
                   "E": b"\x09\x0c\x04\x30", "F": b"\x09\x0b\x04\x30"}
# The command doevents, which follows a page's load code, by series: K, P,
# and F number it their own way.
DOEVENTS = {"T": b"\x09\x21\x08", "K": b"\x09\x22\x08", "P": b"\x09\x30\x08",
            "E": b"\x09\x30\x08", "F": b"\x09\x23\x08"}
# On P, a page keeps every value in its memory, as components do on T
# (ResearchNotes/tft/p-series.md). Its memory starts with what its record's head
# holds, its first _HEAD_SIZE bytes, then its effect, its first, 1 byte
# each, and its time, 2 bytes, which are 0 without an effect, its swipe
# targets up, down, left, and right, 1 byte each, its sta, and its
# background (_page_background), 2 bytes each: 64 bytes. Its entries give
# where each value lies, from its base, by entry: (offset, highest, lowest,
# code), each code T's with 0x20, and its background's entry, 24, as on T
# (_with_background_entry). With an effect, its first and its time take
# entries 16 and 17, and each later entry is numbered two on
# (component_types.with_p_effect).
_HEAD_SIZE = 52
_P_PAGE_VALUES = (("effect", "<B", 0), ("first", "<B", 0), ("time", "<H", 0),
                  ("up", "<B", 255), ("down", "<B", 255), ("left", "<B", 255),
                  ("right", "<B", 255), ("sta", "<H", 1))
_P_BACKGROUND_PLACE = _HEAD_SIZE + sum(struct.calcsize(form) for _, form, _ in _P_PAGE_VALUES)
_P_PAGE_MEMORY_SIZE = _P_BACKGROUND_PLACE + 2
# A page's entries on P, and the attribute it keeps as its background by its
# sta (component_types.P_PAGE_ENTRIES and PAGE_BACKGROUND_NAMES).
_P_PAGE_ENTRIES = component_types.P_PAGE_ENTRIES
_BACKGROUND_NAMES = component_types.PAGE_BACKGROUND_NAMES
# The events whose blocks are their name, their code, then a 0 word, in the
# order a page gives them. A page's load code follows its objects' table,
# and its loadend code doevents.
NAMED_EVENTS = ("down", "up", "unload")
# The places a record gives, in its order, each by the names of what may
# take it: its background fill's, then its events' code's. The fourth is a
# timer's timer event's or a slider's slide event's, and was 0xFFFFFFFF for
# every other object seen. The fifth is a page's unload event's, or an
# audio's or a gmov's playend event's.
_BACKGROUND_FILL = "background fill"
_RECORD_PLACES = ((_BACKGROUND_FILL,), ("down",), ("up",), ("timer", "slide"),
                  ("unload", "playend"))
_NO_PLACE = 0xFFFFFFFF
# The place of a drawing's first block, which a record gives first, when the
# drawing has blocks.
_FIRST_BLOCK = "first block"
# The place and size a record gives a component that is not drawn, as a
# variable: 0, 0, of 1 by 1.
_UNDRAWN_PLACE = (0, 0, 1, 1)
# The aph a record gives an object without one, as a timer: the most opaque.
_OPAQUE = 127
# A page's memory on T and K, and its size (page_memory_of).
PAGE_MEMORY_FORMAT = "<BBBBHH"
PAGE_MEMORY_SIZE = struct.calcsize(PAGE_MEMORY_FORMAT)
# The block of the page's starting memory, after its objects' table, starts
# with the page's run of 0xFF bytes (_memory_run). After its components'
# memory come 4 zeros, then the texts some types keep there (page_text), as
# a QR code keeps its txt. Its last word, 4 bytes, is the total size of the
# buffers some types keep at the end of the page's memory (buffer_size), as
# a waveform does: 0 when none keeps one. The first buffer starts at that
# word's place, in every file seen.
_BEFORE_TEXTS = bytes(4)

_RECORD_SLOTS = 88
# A page's slots that name an entry, by place among its record's slots; and
# the slot of its background's entry, by the attribute it keeps
# (_BACKGROUND_NAMES). A page with no background has neither.
_PAGE_SLOTS = {1: 3, 2: 23, 42: 9, 43: 10, 44: 13, 45: 14, 46: 11, 47: 12, 49: 1, 62: 0}
_PAGE_BACKGROUND_SLOTS = {"bco": 4, "pic": 6}
# Each variable's last number, the same in every file seen.
_VARIABLE_NUMBER = 9
# The parts of the user code that pieces lie in, as UserCode.places names them.
_BLOCKS, _DATA, _RECORDS = "blocks", "data", "records"


@dataclass(frozen=True)
class Piece:
    """Where a piece lies: its name (the module's docstring); the part of the
    user code it lies in, as UserCode.places names it, such as "data"; and
    its start and its end, counted from that part's start."""
    name: str
    part: str
    start: int
    end: int


class FrameError(NxwrightError):
    """A project the frame does not write. Its message says why."""


def read_int_declaration(line: str):
    """Returns the int variables the declaration `line` gives, as (name,
    starting value), in order, or None when it is not one the frame
    writes: `int`, spaces or tabs, then names, each with a decimal value, a
    hexadecimal one, or none, which starts it at 0, separated by commas
    (_INT_VARIABLE). The Nextion
    Editor refuses, though nxwright's build lets them through, a name past
    32 characters, a colour's (_TAKEN_NAMES), and a name twice ("Repeated
    definition global variable name"). A value past 4 bytes is refused,
    as an int's bytes cannot hold it."""
    match = _INT_DECLARATION.fullmatch(line)
    if match is None:
        return None
    found = []
    for part in match.group(1).split(","):
        variable = _INT_VARIABLE.fullmatch(part)
        value = _int_value(variable.group(2) or "0") if variable is not None else None
        if variable is None or value not in _INT_RANGE or variable.group(1) in _TAKEN_NAMES:
            return None
        found.append((variable.group(1), value))
    names = [name for name, _ in found]
    return found if len(set(names)) == len(names) else None


def _int_value(text: str) -> int:
    """Returns the starting value an int declaration gives as `text`: a
    decimal as it reads, or a hexadecimal number's low 4 bytes, read as a
    signed int, as the Nextion Editor reads `int a=0xFFFFFFFF` as -1."""
    if text[:2] in ("0x", "0X"):
        value = int(text, 16) & 0xFFFFFFFF
        return value - (1 << 32) if value >= 1 << 31 else value
    return int(text)


def _declaration_covered(need) -> bool:
    """Whether the program.s line `need` is an int declaration the frame
    writes (read_int_declaration)."""
    return read_int_declaration(need.value) is not None


# disup, an attribute of the Nextion Editors 1.60.1 and 1.63.3, which a page
# file may give on any object that has a drag (nxwright's page_source). The
# Nextion Editor 1.68.2 has none, and writes the same file with or without
# it. So the frame writes nothing of it: P's table of attribute names
# leaves it out (_attribute_names).
DISUP = "disup"


# The attributes that every component with a place has, and the page too,
# that the frame writes alike for every type: an aph and a sendkey in its
# record's head (_record_head), an effect's two more entries
# (component_types.EFFECT_ENTRIES), a vscope, which puts a global object's
# memory before every page's (_GlobalMemory), and the others, which change
# nothing in the file on T and K. A timer, a variable, and a touch capture have
# groupid0, groupid1, lockobj, and vscope alone. By name, but vscope, which
# has rules of its own: their words.
#
# Each of these is written as it is, so every value that fits in its bytes
# is taken. The Nextion Editor takes fewer, and nxwright's build refuses
# the rest first (project/attribute_ranges.toml).
_SHARED_ATTRIBUTES = {
    "aph": "any value that fits in its byte, in its record",
    "sendkey": ("0, none, 1 as it is released, 2 as it is pressed, 3 both, or any other "
                "value that fits in its byte, in its record"),
    "drag": "any value, which changes nothing in the file",
    "lockobj": "any value, which changes nothing in the file",
    "effect": ("0, at once, or any other value, sliding in, which T and K do not play: two "
               "more empty entries"),
    "first": "any value, which changes nothing in the file",
    "time": "any value, which changes nothing in the file",
    **{name: "any value, which changes nothing in the file"
       for name in ("movex", "movey", "groupid0", "groupid1")},
    DISUP: ("any value, which changes nothing in the file, as the Nextion Editor 1.68.2 has "
            "no disup"),
}
# T, K, and F, written alike.
_SERIES_WRITTEN_AS_T = ("T", "K", "F")


# Of those attributes, the ones P's probes showed, of the types the frame
# writes on P. On P, an object's memory gives its drag, its movex, and its
# movey (_p_memory_head), and with an effect, its first and its time, which
# take two entries after its effect's (component_types.with_p_effect).
_SHARED_ON_P = ("aph", "sendkey", "drag", "lockobj", "movex", "movey", "groupid0", "groupid1",
                "effect", "first", "time", DISUP)
_TYPES_ON_P = ("page", "text", "number", "button", "select", "combo-box", "sliding-text",
               "gmov", "video", "data-record", "file-browser", "checkbox", "radio",
               "dual-state-button", "progress-bar", "picture", "xfloat", "qr-code",
               "crop", "slider", "gauge", "scrolling-text", "waveform", "hotspot", "switch",
               "external-picture")
# The types without a place, which have lockobj, groupid0, and groupid1
# alone of those attributes, and P's probe of their own showed.
_WITHOUT_A_PLACE_ON_P = ("timer", "variable", "touch-capture", "audio", "file-stream")
_GROUPS_AND_LOCK = ("lockobj", "groupid0", "groupid1")


def _shared_attribute_covered(name: str):
    """Returns the check of a need of the attribute `name`, which its rule's
    subject gives: of any type of T, K, or F, and on P of _TYPES_ON_P when
    `name` is one of _SHARED_ON_P, or of _WITHOUT_A_PLACE_ON_P when it is one
    of _GROUPS_AND_LOCK."""
    def on_p(need) -> bool:
        type_name = need.subject.partition(".")[0]
        return ((name in _SHARED_ON_P and type_name in _TYPES_ON_P)
                or (name in _GROUPS_AND_LOCK and type_name in _WITHOUT_A_PLACE_ON_P))
    return lambda need: need.series not in SERIES_WRITTEN_AS_P or on_p(need)


def _shared_attribute_words(name: str, words: str) -> str:
    """Returns the words of the rule of the attribute `name` of any object,
    whose values `words` gives (_SHARED_ATTRIBUTES), with what it covers on
    P."""
    said = "%s of any object that has it: %s, on T, K, and F" % (name, words)
    if name in _SHARED_ON_P:
        said += (", and of a page, a text, a number, a button, a select, a combo-box, a "
                 "sliding text, a gmov, a video, a data record, a file browser, a checkbox, a "
                 "radio, a dual-state button, a progress bar, a picture, an xfloat, a QR "
                 "code, a crop, a slider, a gauge, a scrolling text, a waveform, a hotspot, a "
                 "switch, or an external picture on P and E")
        if name in _GROUPS_AND_LOCK:
            said += (", and of a timer, a variable, a touch capture, an audio, or a file "
                     "stream there too")
        if name in ("drag", "movex", "movey"):
            said += ", where its memory's record head gives it"
        elif name in ("effect", "first", "time"):
            said += (", where an effect gives its first and its time two entries after its "
                     "effect's, and values in its memory")
        if name in ("drag", "aph", "effect"):
            said += "; a hotspot's %s lies in its entry, not in its memory" % name
    return said


# The attributes that give a component a key, by the types that have one:
# the sliding text on P and E alone, as T, K, and F have none.
_KEYED = ("text.key", "number.key", "xfloat.key", "scrolling-text.key", "sliding-text.key")
# The vscope of the page and of each type P has, global or not, as P's
# probes of a global component of each showed (p_probes.py): every type
# but the data record, which is always global, and the file stream, which
# the Nextion Editor refuses global on P and E, as nxwright's memory table
# records.
_GLOBAL_ON_P = tuple(name + ".vscope" for name in (
    "page", "text", "number", "button", "checkbox", "radio", "dual-state-button",
    "progress-bar", "xfloat", "qr-code", "slider", "gauge", "waveform", "scrolling-text",
    "hotspot", "timer", "variable", "touch-capture", "picture", "crop", "switch",
    "external-picture", "select", "combo-box", "sliding-text", "gmov", "video", "audio",
    "file-browser"))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P, pages alone, in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the frame has matched with probes (matching.py): pages, on the T, K,
# P, E, and F base folders' models and on F's other models, at each rotation,
# and program.s's int declarations.
# Each component type's module keeps its own list.
MATCHED = [
    # nxwright's build refuses a page of more than 250 components and a
    # project of more than 251 pages, as the Nextion Editor does, so any page
    # it builds is one the frame writes.
    Rule("type", "page", "any page nxwright's build takes; its components and code are each "
         "matched by their own piece"),
    # nxwright's build takes a page name of up to 14 letters, digits, and _,
    # in ASCII, not starting with a digit, and none the Nextion Editor
    # refuses, which the page list gives as the CRC of its 14 bytes.
    Rule("attribute", "page.objname", "any name nxwright's build takes"),
    # A page's place and size: the Nextion Editor writes any page at its
    # screen's place and size, whatever these are (_at_the_screen).
    *[Rule("attribute", "page." + name, "any value, written as 0") for name in ("x", "y")],
    *[Rule("attribute", "page." + name, "any value, written as the screen's %s" % word)
      for name, word in (("w", "width"), ("h", "height"))],
    Rule("attribute", "page.bco", *value_rule("bco")),
    Rule("attribute", "page.sta", "0, 1, or 2: no background, a colour, or a picture",
         from_to(0, 2), INVALID_VALUE),
    # A pic is 2 bytes in memory, written as it is, whichever picture it is.
    Rule("attribute", "page.pic", "any value from 0 to 65535, written as it is: a picture of "
         "the project, or 65535 for none"),
    # A page's effect goes to 10, its entry's highest on P. A component's
    # stops at 8, its own entry's highest, which the rule of the attributes
    # every object has takes.
    Rule("attribute", "page.effect", "from 0 to 10, 9 fading in and 10 growing from the "
         "middle", from_to(0, 10)),
] + [Rule("attribute", "page." + name, "the ID of the page a swipe %s opens, from 0 to 254, or "
          "255 for none" % way, from_to(0, 255))
     for name, way in (("up", "up the screen"), ("down", "down the screen"),
                       ("left", "to the left"), ("right", "to the right"))] + [
    Rule("encoding", None, "any of the Nextion Editor's 24 encodings, as nxwright names them, "
         "such as iso-8859-1, gb2312, or utf-8; page names stay in ASCII, as nxwright's build "
         "takes no other", lambda need: need.subject in ENCODINGS.values()),
    Rule("text in code", None, "a line of code with characters past ASCII, each one the "
         "project's encoding writes", past_ascii_covered),
    Rule("attribute", None, "key of a text, a number, an xfloat, a scrolling text, or a "
         "sliding text: any "
         "value of its byte; 1, 2, 3, or 4, the full keyboard, the keypad, the speed dial, or "
         "Chinese input, whose page it opens after its own Touch Release code, which must be "
         "the project's, with its global variables loadpageid and loadcmpid, as nxwright's "
         "keyboards have them; another opens none",
         lambda need: need.subject in _KEYED and from_to(0, 255)(need)),
    # A vscope is 0, its page's, or 1, global. Any other value has no
    # meaning, and nxwright's build refuses it on every series, as it does a
    # data record that is not global, and a file stream that is, on P and E.
    Rule("attribute", "*.vscope", "vscope of any object, on T, K, and F: 0, its page's, or 1, "
         "global, whose memory then lies before every page's", from_to(0, 1), INVALID_VALUE,
         series=_SERIES_WRITTEN_AS_T),
    Rule("attribute", "*.vscope", "vscope of a page or of a component of any type but the "
         "data record and the file stream, on P and E: 0, its page's, or 1, global, whose "
         "memory then lies in the first block's int area",
         lambda need: need.subject in _GLOBAL_ON_P and from_to(0, 1)(need), INVALID_VALUE,
         series=SERIES_WRITTEN_AS_P),
    Rule("attribute", "data-record.vscope", "1 on P and E, its default and its only value: a "
         "data record is always global", from_to(1, 1), INVALID_VALUE,
         series=SERIES_WRITTEN_AS_P),
    Rule("attribute", "file-stream.vscope", "0 on P and E, its page's: the Nextion Editor "
         "refuses a global file stream there, as nxwright's memory table records",
         from_to(0, 0), INVALID_VALUE, series=SERIES_WRITTEN_AS_P),
    Rule("code", "program.s", "an int declaration, such as `int sys0=0,sys1=0,sys2=0`: names "
         "of up to 32 letters, digits, and _, each with a decimal value from -2147483648 to "
         "2147483647, a hexadecimal one, as its low 4 bytes, or none, which starts it at 0, "
         "separated by commas, with spaces around them or not; no name twice and none a "
         "colour's, which the Nextion Editor refuses",
         _declaration_covered),
] + [Rule("attribute", "*." + name, _shared_attribute_words(name, words),
          _shared_attribute_covered(name))
     for name, words in _SHARED_ATTRIBUTES.items()]


def _at_the_screen(project: Project) -> Project:
    """Returns `project` with each page at its screen's place and size: an x
    and a y of 0, and the screen's width and height at the project's
    rotation (DeviceSettings.page_size). The Nextion Editor writes every page
    so, whatever its own place and size, which it resets as it opens the
    project."""
    width, height = project.settings.page_size
    place = {"x": 0, "y": 0, "w": width, "h": height}
    pages = []
    for page in project.pages:
        head = page.objects[0]
        items = [replace(item, value=number_to_bytes(place[item.name], len(item.value)))
                 if isinstance(item, Attribute) and item.name in place else item
                 for item in head.items]
        pages.append(replace(page, objects=[replace(head, items=items)] + page.objects[1:]))
    return replace(project, pages=pages)


def user_code(project: Project, encode_code=encode_statements) -> UserCode:
    """Returns the user code of `project`, as laid_out lays it out."""
    return laid_out(project, encode_code)[0]


def laid_out(project: Project, encode_code=encode_statements) -> tuple:
    """Returns (the user code of `project`; where each of its pieces lies, a
    list of Piece, which cover every byte of it; where each component lies,
    {"page0-1": its ObjectPlace}, by its page's ID and its own, as a test of
    its type passes it to the type's functions). `encode_code` gives the blocks of
    a run of lines, as statements.encode_code does. The frame calls it once
    for program.s, once for each macro, and once for each event, on their
    lines that are not blank (code_lines), in the order their blocks lie,
    and once more after the Touch Release event of a component with a key,
    on the lines the key adds (component_types.key_lines); on a page that it
    lays out twice, as one with a scrolling text, twice for each of that
    page's events. Raises FrameError for a global component on P of a type
    the frame does not write there, a component whose type has no module,
    an int declaration it does not write, one after other code, an int
    declaration in a macro, a name program.s declares twice, an object
    whose ID is not its place on its page, or a page whose second layout
    puts its load section's blocks elsewhere than its first. The match
    check (matching.py) refuses the first five first; it cannot see the
    others, which are about program.s or a page as a whole."""
    project = _at_the_screen(project)
    if not code_lines(project, project.program):
        project = replace(project, program=_NEW_PROJECT_PROGRAM)
    variables = int_variables(project)
    # The stages that follow share the context, which builds each table of
    # the whole project once. Where each object's entries start is built
    # first, so that a component whose type has no module is refused here.
    context = CompileContext(project)
    try:
        context.first_entries
    except NxwrightError as error:
        raise FrameError(str(error)) from None
    series = project.settings.model.series
    # On P, the first block ends with a table of the project's attribute
    # names, and each record gives a slot for each of them.
    names = _attribute_names(project) if series in SERIES_WRITTEN_AS_P else None
    global_memory = _GlobalMemory(context, variables)
    blocks = [_first_block(global_memory.int_area, [page.objects[0] for page in project.pages],
                           names)]
    program = _code_blocks(context, project.program, CodePlace(), encode_code)
    program_place = len(encode_blocks(blocks))
    ending = [APPENDED_PAGE_0[series], b""]
    # The macros follow program.s. A call anywhere jumps into one, so their
    # places are known before any run of code is written.
    macro_blocks, macro_places, macro_table, macro_spans = _macros(
        context, program_place + len(encode_blocks(program + ending)), encode_code)
    blocks += label_numbers.resolved(program, context.numbers.events[None, None, None],
                                     program_place, macro_places)
    blocks += ending
    regions = _first_block_regions(global_memory.int_area,
                                   [page.objects[0] for page in project.pages], names)
    pieces = _first_block_pieces(global_memory, regions) + [
        Piece("program-s", _BLOCKS, program_place, len(encode_blocks(blocks)))]
    # A macro's piece is named by its place in the macro tab, as its own name
    # may hold a space, which a piece's name may not.
    pieces += [Piece("macro-%d" % number, _BLOCKS, start, end)
               for number, (_, start, end) in enumerate(macro_spans)]
    blocks += macro_blocks
    layouts, first_blocks = [], []
    for number, page in enumerate(project.pages):
        start = len(encode_blocks(blocks))
        first_blocks.append(len(blocks))
        layout = _PageLayout(context, number, page, global_memory, encode_code, start,
                             names=names, macros=macro_places)
        # A scrolling text's drawing jumps into its blocks in the load
        # section. Only a first layout finds where those start. The second
        # layout has the same sizes, so it puts them in the same places.
        if layout.drawing_jumps_to_load:
            first = layout.load_places
            layout = _PageLayout(context, number, page, global_memory, encode_code, start,
                                 load_places=first, names=names, macros=macro_places)
            if layout.load_places != first:
                raise FrameError("page %d's second layout put its load section's blocks "
                                 "elsewhere than its first" % number)
        blocks += layout.blocks
        layouts.append(layout)
        pieces += [replace(piece, start=piece.start + start, end=piece.end + start)
                   for piece in layout.pieces if piece.part == _BLOCKS]
    # On P, the global components' memories are known once their pages are.
    # They keep their length, so the blocks after the first keep their
    # places.
    memories = {key: memory for layout in layouts
                for key, memory in layout.global_memories.items()}
    int_area = global_memory.with_p_memories(memories)
    if memories:
        blocks[0] = _first_block(int_area, [page.objects[0] for page in project.pages], names)
    # Only P's global objects have a record's head in the int area.
    _through_the_scratch_image(blocks, layouts, first_blocks, int_area,
                               global_memory.p_heads() if names is not None else [])
    variable_table = _variable_table(variables)
    data_place = len(encode_blocks(blocks)) + len(variable_table)
    index = _page_index([(len(layout.objects), layout.table, len(layout.data),
                          layout.memory_size) for layout in layouts], data_place)
    data, records = b"", b""
    for layout in layouts:
        shift = {_DATA: len(data), _RECORDS: len(records)}
        pieces += [replace(piece, start=piece.start + shift[piece.part],
                           end=piece.end + shift[piece.part])
                   for piece in layout.pieces if piece.part in shift]
        data += layout.data
        records += layout.records
    code = UserCode(blocks, b"", variable_table, data, index, records, macro_table)
    # The user code ends at a multiple of 4 bytes, padded with 0xFF.
    padding = b"\xff" * (-len(code.to_bytes()) % 4)
    code.records += padding
    pieces += [Piece(name, part, 0, len(content)) for name, part, content in (
        ("variables", "variables", variable_table), ("page-index", "page index", index),
        ("macros-table", "macros", macro_table)) if content]
    if padding:
        pieces.append(Piece("padding", _RECORDS, len(records), len(code.records)))
    places = {"page%d-%d" % (layout.number, object_id): place
              for layout in layouts for object_id, place in layout.places.items()}
    return code, pieces, places


def _page_index(pages: list, data_place: int) -> bytes:
    """Returns the page index of `pages`. Each page is given as (its number
    of objects, where its objects table lies among the user code's blocks,
    the size of its entries, the size of its memory).

    A page's entry in the index holds five numbers, in this order:
    - the number of objects on the pages before it, not the page's ID, so 2
      for a page after a page with one text;
    - its own number of objects;
    - its objects table's place;
    - where its entries start: the first page's at `data_place`, each later
      page's after the entries of the pages before it;
    - its memory's size."""
    index, objects_before, entries_place = b"", 0, data_place
    for objects, table, entries, memory_size in pages:
        index += struct.pack("<HHIII", objects_before, objects, table, entries_place,
                             memory_size)
        objects_before += objects
        entries_place += entries
    return index


def int_variables(project: Project) -> list:
    """Returns program.s's int variables, as (name, starting value), in the
    order it declares them. Raises FrameError for a declaration it does not
    write (read_int_declaration), and for these, which the Nextion Editor
    refuses though nxwright's build lets them through: one after other code
    ("Global variable definitions must precede all code"), and a name
    declared twice."""
    found, after_code = [], False
    for line in code_lines(project, project.program):
        if not declares_ints(line):
            after_code = after_code or not line.strip().startswith("//")
            continue
        if after_code:
            raise FrameError("the int declaration %r comes after code, which the Nextion "
                             "Editor refuses" % line)
        variables = read_int_declaration(line)
        if variables is None:
            raise FrameError("the frame does not write the int declaration %r: it writes "
                             "names of up to 32 characters, each with a decimal value of 4 "
                             "bytes, a hexadecimal one, or none, separated by commas. The "
                             "Nextion Editor refuses a longer name, a colour's name, a longer "
                             "decimal value, and a name twice" % line)
        found += variables
    names = [name for name, _ in found]
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        raise FrameError("program.s declares %s more than once, which the Nextion Editor "
                         "refuses (\"Repeated definition global variable name\")"
                         % ", ".join(twice))
    return found


def declares_ints(line: str) -> bool:
    """Whether the program.s line `line` is an int declaration, whose
    values the frame reads, and which gives no block of its own."""
    return _INT_KEYWORD.match(line) is not None


def page_name_crc(name: bytes) -> int:
    """Returns the CRC of the page name `name` (the module's docstring)."""
    return byte_form_crc(name.ljust(_NAME_SIZE, b"\x00"))


def _code_blocks(context: CompileContext, code: bytes, place: CodePlace, encode_code) -> list:
    """Returns the blocks of the lines of `code`, which belong to `place`."""
    return encode_code(code_lines(context.project, code), place, context)


def _first_block_regions(int_area: bytes, pages: list, names: list = None) -> list:
    """Returns the regions of the first block after its 0 word: `int_area`
    (_GlobalMemory), then the page list, which gives each page as its name's
    CRC and its ID, in the order of their CRCs. On P, `names` gives a third:
    the table of the project's attribute names (_attribute_names), each
    name's CRC."""
    page_list = b"".join(struct.pack("<IH", crc, number) for crc, number in sorted(
        (page_name_crc(page.attribute("objname")), number) for number, page in enumerate(pages)))
    regions = [int_area, page_list]
    if names is not None:
        regions.append(b"".join(struct.pack("<I", _name_crc(name)) for name in names))
    return regions


def _first_block_head_size(regions: list) -> int:
    """Returns the size of the first block's head, before its regions
    `regions` (_first_block_regions): the number of its regions, each
    region's place and size, the 0 word's among them, then the 0 word."""
    return 4 + 8 * (len(regions) + 1) + 4


def _first_block(int_area: bytes, pages: list, names: list = None) -> bytes:
    """Returns the first block: the number of its regions, then each
    region's place and size, then the regions. The first region is a 0
    word, then the others (_first_block_regions): 3 regions on T and K, and
    4 on P."""
    regions = _first_block_regions(int_area, pages, names)
    head_size = _first_block_head_size(regions)
    places, at = [(head_size - 4, 4)], head_size
    for region in regions:
        places.append((at, len(region)))
        at += len(region)
    return (struct.pack("<I", len(places)) + b"".join(struct.pack("<II", *place)
                                                      for place in places)
            + bytes(4) + b"".join(regions))


def _first_block_pieces(global_memory: "_GlobalMemory", regions: list) -> list:
    """Returns where each piece of the first block lies, as _first_block
    writes it from `regions` (_first_block_regions), a list of Piece in the
    blocks, which start with it: its head, its size word and the head
    _first_block_head_size gives; the pieces of its int area
    (_GlobalMemory.pieces); its page list; and on P, its table of attribute
    names."""
    # The blocks give each block's size word before it.
    at = 4 + _first_block_head_size(regions)
    pieces = [Piece("first-block-head", _BLOCKS, 0, at)] + global_memory.pieces(at)
    at += len(regions[0])
    for name, region in zip(("page-list", "attribute-names"), regions[1:]):
        pieces.append(Piece(name, _BLOCKS, at, at + len(region)))
        at += len(region)
    return pieces


# In a record's head, the bytes the Nextion Editor fills in only in its
# copy of a memory image on P: its kind, its blocks' places, and its base.
_HEAD_FILLED_LATE = slice(3, 32)


def _blank_filled_late(memory: bytearray, head: int, size: int):
    """Writes 0 over the bytes of the record's head at `head` in `memory`
    that the Nextion Editor fills in only in its copy (_HEAD_FILLED_LATE),
    those of its `size` bytes alone: a head shorter than a whole one, as a
    variable's of 4, keeps its values after it."""
    late = range(_HEAD_FILLED_LATE.start, min(_HEAD_FILLED_LATE.stop, size))
    memory[head + late.start:head + late.stop] = bytes(len(late))


def _through_the_scratch_image(blocks: list, layouts: list, first_blocks: list,
                               int_area: bytes, global_heads: list):
    """Gives each page's memory block the bytes of the Nextion Editor's
    scratch image where the page leaves them. The Nextion Editor writes
    every memory image in one scratch image, from its start: the int area
    first, then each page's memory block over the one before. Each layout's
    rooms give where a local txt's room leaves the bytes that lay there: on
    P, past its txt and a zero; on T, K, and F, as _t_rooms gives. On P, a
    record's head lies there without its kind, places, and base
    (_HEAD_FILLED_LATE), which the Nextion Editor fills in only in its copy.
    `first_blocks` gives the place of each layout's first block among
    `blocks`, and `global_heads` each global object's memory in the int area
    `int_area` that has such a head, as (its place, its head's size). A head
    shorter than a whole one, as a variable's of 4 bytes, has only its own
    bytes filled in late, and its values after it stay."""
    scratch = bytearray(int_area)
    for base, size in global_heads:
        _blank_filled_late(scratch, base, size)
    for layout, first in zip(layouts, first_blocks):
        block = bytearray(blocks[first + layout.memory_block])
        scratch.extend(bytes(max(0, len(block) - len(scratch))))
        for place, written, length in layout.rooms:
            block[place + written:place + length] = scratch[place + written:place + length]
        blocks[first + layout.memory_block] = bytes(block)
        for head, size in layout.heads:
            _blank_filled_late(block, head, size)
        scratch[:len(block)] = block


def _t_rooms(components: list, project: Project, block_start: int) -> list:
    """Returns the rooms of the local txts of `components` on T, K, and F, as
    (where the room lies in its page's memory block, the bytes the Nextion
    Editor writes, its length), for _through_the_scratch_image. A txt kept
    in its component's memory (TXT_PLACE) takes its txt_maxl + 1 bytes, so
    only the bytes that round its room up to 4 keep what lay there. A txt
    kept after the page's components' memory (page_text) takes its txt and a
    zero alone. A page's memory block starts at `block_start` in memory."""
    rooms = []
    for page_object, module, place, memory in components:
        # A global component's memory lies in the int area.
        if not memory:
            continue
        if hasattr(module, "page_text"):
            rooms.append((place.text_place - block_start,
                          len(page_object.attribute("txt") or b"") + 1,
                          len(module.page_text(page_object, project))))
        elif hasattr(module, "TXT_PLACE"):
            rooms.append((place.base - block_start + module.TXT_PLACE,
                          number_from_bytes(page_object.attribute("txt_maxl")) + 1,
                          len(memory) - module.TXT_PLACE))
    return rooms


# A macro's "S " block, with its size word, before its lines' blocks.
_MACRO_START_SIZE = 4 + len(label_numbers.S_BLOCK_START + value_operand(0))


def _macros(context: CompileContext, place: int, encode_code) -> tuple:
    """Returns the blocks of the macros of the project of `context`, the
    compile's context, which start at the place `place` in the user code;
    the place of the block after each one's "S " block, where a call jumps,
    by name; the macros' table; and where each macro's blocks start and
    end, as (name, start, end). Each macro, in the macro tab's order, is an
    "S " block of its number
    (label_numbers.numbers), its lines' blocks, as program.s's, and a 0
    word. The table gives, for each, the CRC of its name and the place of
    its "S " block, sorted by the CRC (ResearchNotes/tft/macros.md). Raises
    FrameError for an int declaration in a macro."""
    macros = context.project.macros
    runs, firsts = [], {}
    for name, lines in macros:
        if any(declares_ints(line) for line in lines):
            raise FrameError("macro %s: an int declaration, which the Nextion Editor refuses "
                             "in a macro (\"Global variable definitions must precede all code\")"
                             % name)
        run = encode_code(lines, CodePlace(), context)
        runs.append((name, place, run))
        firsts[name] = place + _MACRO_START_SIZE
        place += _MACRO_START_SIZE + len(encode_blocks(run + [b""]))
    blocks, entries, spans = [], [], []
    for name, start, run in runs:
        number = context.numbers.macros[name]
        blocks.append(label_numbers.S_BLOCK_START + value_operand(number))
        blocks += label_numbers.resolved(run, number + 1, firsts[name], firsts)
        blocks.append(b"")
        entries.append((_name_crc(name), start))
        spans.append((name, start, start + _MACRO_START_SIZE + len(encode_blocks(run + [b""]))))
    return blocks, firsts, b"".join(struct.pack("<II", crc, start)
                                    for crc, start in sorted(entries)), spans


def _attribute_names(project: Project) -> list:
    """Returns the names of the attributes the project's objects have, each
    once, in the order of their CRCs, as P's first block gives them. An
    event is not an attribute, and an object lacks some attributes by
    another attribute's value, as nxwright's editor_limits.lacked_attributes
    gives them: a page with a colour behind it has no pic. A disup is left
    out, as the Nextion Editor 1.68.2 has none (DISUP)."""
    names = set()
    for page in project.pages:
        for page_object in page.objects:
            def value_of(name, page_object=page_object):
                value = page_object.attribute(name)
                return None if value is None else int.from_bytes(value, "little")
            lacked = lacked_attributes(component_types.type_name(page_object), value_of)
            names.update(item.name for item in page_object.items
                         if isinstance(item, Attribute) and item.name not in lacked
                         and item.name != DISUP)
    return sorted(names, key=_name_crc)


def _name_crc(name: str) -> int:
    """Returns the CRC of an attribute's name, not padded."""
    return byte_form_crc(name.encode("ascii"))


class _GlobalMemory:
    """The memory before every page's: the int variables, then the global
    objects' (component_types.is_global), on T and K. In order:

      - each int variable's starting value, 4 bytes, in the order program.s
        declares them;
      - each global object's memory, in page order, then ID order, a global
        page's first on its page;
      - the texts they keep (page_text), in the same order;
      - a word, the total size of their buffers (buffer_size), 0 without
        one. The first buffer starts at that word, and the others follow it
        in the same order.

    `int_area` is the first block's int area: all of the above but the
    buffers. `size` is where every page's memory starts, after the int area
    and the buffers. `places` gives each global object's place, by (page
    ID, object ID), its load_place None.

    On P, a global component's memory starts with its record's head, which
    gives where its blocks lie, so `int_area` holds zeros of its length in
    its place until its page is laid out (with_p_memories), and so does a
    global page's, of _P_PAGE_MEMORY_SIZE. Raises FrameError for a global
    component on P of a type the frame does not write there."""

    def __init__(self, context: CompileContext, variables: list):
        project, first_entries = context.project, context.first_entries
        self._ints = b"".join(struct.pack("<i", value) for _, value in variables)
        on_p = project.settings.model.series in SERIES_WRITTEN_AS_P
        # Each global object, as _placed_after takes them. A page has no
        # module.
        found, at = [], len(self._ints)
        for number, page in enumerate(project.pages):
            page_entry = first_entries[(number, component_types.object_name(page.objects[0]))]
            for object_id, page_object in enumerate(page.objects):
                if not component_types.is_global(page_object):
                    continue
                name = component_types.object_name(page_object)
                place = ObjectPlace(number, object_id, first_entries[(number, name)], page_entry,
                                    at, two_byte_start=two_byte_start(project.settings.encoding),
                                    timer_numbers=context.numbers.timers.get((number, object_id)))
                if object_id == 0:
                    module = None
                    memory = bytes(_P_PAGE_MEMORY_SIZE) if on_p else page_memory_of(page_object)
                else:
                    module = component_types.object_module(page_object)
                    if on_p and not hasattr(module, "P_MEMORY_SIZE"):
                        raise FrameError("%s: the frame does not write a %s on the %s series yet"
                                         % (name, component_types.type_name(page_object),
                                            project.settings.model.series))
                    if on_p:
                        memory = bytes(module.P_MEMORY_SIZE)
                    else:
                        memory = (module.memory_at(page_object, project, place)
                                  if _places_after(module) else module.memory(page_object, project))
                found.append((page_object, module, place, memory))
                at += len(memory)
        found, self._texts, self._buffers_size = _placed_after(project, found, at, on_p=on_p)
        self._memories = [((place.page, place.object_id), memory)
                          for _, _, place, memory in found]
        # On P, the head of its record each global object's memory starts
        # with: a page's whole head, or as much as its type gives.
        self._head_sizes = {(place.page, place.object_id):
                            (_p_head_size(module) if module else _HEAD_SIZE) if on_p else 0
                            for _, module, place, _ in found}
        self.places = {(place.page, place.object_id): place for _, _, place, _ in found}
        self.int_area = self.with_p_memories({})
        self.size = len(self.int_area) + self._buffers_size

    def p_heads(self) -> list:
        """Returns where each global object's memory lies in the int area on
        P, and the size of the record's head it starts with, as (place,
        size): a whole head for a page, or as much as its type gives."""
        return [(place.base, self._head_sizes[key]) for key, place in self.places.items()]

    def with_p_memories(self, memories: dict) -> bytes:
        """Returns the int area with the memories `memories` gives, by (page
        ID, object ID), in place of the global objects' memories found so
        far, as P's components' memories are known once their pages are laid
        out."""
        return (self._ints + b"".join(memories.get(key, memory) for key, memory in self._memories)
                + b"".join(self._texts) + struct.pack("<I", self._buffers_size))

    def pieces(self, at: int) -> list:
        """Returns where each piece of the int area lies, a list of Piece in
        the blocks, the int area starting at the place `at`: the int
        variables; each global object's memory, on P its head then its
        values, named as a local object's are (_PageLayout._memory_pieces);
        then their texts and the buffers' total. A piece of no bytes, as the
        int variables of a program.s that declares none, is left out."""
        sizes = [("int-variables", len(self._ints))]
        for (page, object_id), memory in self._memories:
            head_size = self._head_sizes[page, object_id]
            sizes += [("page%d-%d-head" % (page, object_id), head_size),
                      ("page%d-%d-memory" % (page, object_id), len(memory) - head_size)]
        sizes.append(("global-texts", len(b"".join(self._texts)) + 4))
        pieces = []
        for name, size in sizes:
            if size:
                pieces.append(Piece(name, _BLOCKS, at, at + size))
                at += size
        return pieces


class _PageLayout:
    """A page's part of the user code: its blocks, from `start` in the user
    code, and its objects' entries and records, the page first, then its
    components in ID order. Raises FrameError for an object whose ID is not
    its place among them, or a component whose type has no module."""

    def __init__(self, context: CompileContext, number: int, page,
                 global_memory: _GlobalMemory, encode_code, start: int, load_places: dict = None,
                 names: list = None, macros: dict = None):
        """`context` is the compile's context, which gives the project and
        its tables. `global_memory` is the memory before every page's,
        which gives a global object's place. `load_places` gives, by ID,
        where each component's blocks in the load section start, as a first
        layout of the page found them, for a type whose drawing jumps there
        (DRAWING_JUMPS_TO_LOAD). `names`, on P alone, is the first block's
        table of attribute names (_attribute_names), for the records'
        slots. `macros` gives the place a call of each macro jumps to, by
        name (_macros)."""
        project, first_entries = context.project, context.first_entries
        self.context, self.project = context, project
        self.number, self.encode_code = number, encode_code
        self.macros = macros or {}
        # The numbers of the "S " blocks: each run of code's first label's.
        self.s_numbers = context.numbers
        # Where each component's blocks in the load section start, by ID, and
        # whether a type's drawing needs them, so that the page is laid out
        # again with them (user_code).
        self.load_places, self.drawing_jumps_to_load = {}, False
        self.objects = list(page.objects)
        # On P, the run that starts a page's memory gives each object's base,
        # 4 bytes each, and the page's own memory holds every value.
        self.names = names
        run = (bytes(4 * len(self.objects)) if names is not None
               else _memory_run(len(self.objects)))
        page_memory_size = _P_PAGE_MEMORY_SIZE if names is not None else PAGE_MEMORY_SIZE
        # The page's memory follows the run, unless the page is global. A
        # global object's memory lies before every page's, where
        # global_memory placed it, and its page's memory leaves it out. The
        # run counts every object all the same.
        at = global_memory.size + len(run)
        page_global = (number, 0) in global_memory.places
        if page_global:
            base, page_memory_size = global_memory.places[number, 0].base, 0
        else:
            base = at
        self.page_entry = first_entries[(number, component_types.object_name(self.objects[0]))]
        self.blocks = []
        # The size of the blocks counted so far, with their size words, and
        # how many they are (_size).
        self._sized, self._counted = 0, 0
        # Where each of the page's pieces lies: in its blocks, from their
        # start, and in its data and records, from theirs.
        self.pieces = []
        # Each component, as (its object, its type's module, its place, its
        # memory, empty for a global one), in ID order. A type with no module
        # was refused by component_types.first_entries.
        components, at = [], at + page_memory_size
        for object_id, page_object in enumerate(self.objects):
            name = component_types.object_name(page_object)
            # Entries, records, and the objects' table all number an object
            # by its place, so its ID must be that place.
            if _object_id(page_object) != object_id:
                raise FrameError("%s's ID is %d, but it is object %d of its page"
                                 % (name, _object_id(page_object), object_id))
            if object_id == 0:
                continue
            module = component_types.object_module(page_object)
            if names is not None and not hasattr(module, "P_MEMORY_SIZE"):
                raise FrameError("%s: the frame does not write a %s on the %s series yet"
                                 % (name, component_types.type_name(page_object),
                                    project.settings.model.series))
            load_place = (load_places or {}).get(object_id)
            self.drawing_jumps_to_load |= getattr(module, "DRAWING_JUMPS_TO_LOAD", False)
            if (number, object_id) in global_memory.places:
                components.append((page_object, module, replace(
                    global_memory.places[number, object_id], load_place=load_place), b""))
                continue
            place = ObjectPlace(number, object_id, first_entries[(number, name)], self.page_entry,
                                at, load_place=load_place,
                                two_byte_start=two_byte_start(project.settings.encoding),
                                timer_numbers=self.s_numbers.timers.get((number, object_id)))
            # A type that keeps a text after the page's components' memory,
            # as a QR code keeps its txt, or a buffer at the end of the
            # page's memory, as a waveform does, gives in its memory where
            # that lies, which is known once every component's memory is
            # (below). Its memory's length is known now.
            if names is not None:
                # On P, its memory starts with its record's head, known once its
                # blocks are (below). Its length is known now.
                memory = bytes(module.P_MEMORY_SIZE)
            else:
                memory = (module.memory_at(page_object, project, place)
                          if _places_after(module) else module.memory(page_object, project))
            components.append((page_object, module, place, memory))
            at += len(memory)
        # The components that are not global keep their texts and buffers
        # after the page's components' memory and 4 zeros.
        local = [component for component in components
                 if (number, component[2].object_id) not in global_memory.places]
        local, texts, buffers_size = _placed_after(project, local, at + len(_BEFORE_TEXTS),
                                                   on_p=names is not None)
        placed = {component[2].object_id: component for component in local}
        components = [placed.get(component[2].object_id, component) for component in components]
        # Where the page and each component lie, now known whole, as the
        # probe runner keeps it beside a probe's pieces (laid_out). The
        # page's own place gives its first entry and its memory's base.
        self.places = {0: ObjectPlace(number, 0, self.page_entry, self.page_entry, base)}
        self.places.update({place.object_id: place for _, _, place, _ in components})
        # Each drawn component's area, by ID, for the refs of those that
        # overlap (overlaps.py).
        self.areas = {place.object_id: place_and_size(page_object)
                      for page_object, module, place, _ in components if _drawn(module)}
        memories = [memory for _, _, _, memory in components]
        self.memory_size = len(run) + page_memory_size + sum(len(memory) for memory in memories)
        code_places = [self._page_own_blocks(self.objects[0], start)]
        for page_object, module, place, _ in components:
            code_places.append(self._component_blocks(module, page_object, place, start))
        self.table = self._place(start)
        at = self._size()
        self.blocks.append(_objects_table(self.objects))
        self._blocks_piece("page%d-objects-table" % number, at)
        # On P, a global component's memory lies before every page's, but is
        # known only now, with its blocks' places: it is kept here for the
        # first block (user_code).
        self.global_memories, self.heads, self.rooms = {}, [], []
        if names is not None:
            run = _p_memory_run(base, [place.base for _, _, place, _ in components])
            page_memory = _p_page_memory(page.objects[0], code_places[0], base)
            if page_global:
                self.global_memories[number, 0], page_memory = page_memory, b""
            memories = []
            for (page_object, module, place, _), places in zip(components, code_places[1:]):
                memory = _p_component_memory(page_object, module, place, places, self.project)
                if (number, place.object_id) in global_memory.places:
                    self.global_memories[number, place.object_id], memory = memory, b""
                memories.append(memory)
            # Where in the memory block the Nextion Editor's scratch image
            # shows (_through_the_scratch_image): each record's head, by its
            # place and how many of its bytes the memory holds, and each
            # local txt's room, by its place, the bytes its txt and a zero
            # take, and its length.
            self.heads = [(len(run), _HEAD_SIZE)] if page_memory else []
            offset = len(run) + len(page_memory)
            for (_, module, _, _), memory in zip(components, memories):
                if memory:
                    self.heads.append((offset, _p_head_size(module)))
                offset += len(memory)
            self.rooms = [(place.text_places[attribute] - global_memory.size,
                           len(page_object.attribute(attribute) or b"") + 1,
                           len(component_types.p_text(module, page_object, attribute, maxl)))
                          for page_object, module, place, memory in components if memory
                          for attribute, maxl, _ in component_types.p_texts(module).values()]
        else:
            page_memory = b"" if page_global else page_memory_of(page.objects[0])
            self.rooms = _t_rooms(components, project, global_memory.size)
        self.memory_block = len(self.blocks)
        at = self._size()
        self.blocks.append(run + page_memory + b"".join(memories) + _BEFORE_TEXTS
                           + b"".join(texts) + struct.pack("<I", buffers_size))
        on_p = names is not None
        self._memory_pieces(at, run, [(0, page_memory, _HEAD_SIZE if on_p else 0)] + [
            (place.object_id, memory,
             _p_head_size(module) if on_p else 0)
            for (_, module, place, _), memory in zip(components, memories)])
        # The load section: what each component adds there, as a timer
        # does, then the page's own load code.
        for (page_object, module, place, _), places in zip(components, code_places[1:]):
            if hasattr(module, "load_start"):
                self.load_places[place.object_id] = self._place(start)
                here = replace(place, load_place=self.load_places[place.object_id])
                at = self._size()
                self.blocks += module.load_start(page_object, project, here, places)
                self._blocks_piece(self._name(place.object_id, "load"), at)
        at = self._size()
        self.blocks += self._event(page.objects[0], "load", start)
        self._blocks_piece(self._name(0, "event-load"), at)
        at = self._size()
        self.blocks.append(DOEVENTS[self.project.settings.model.series])
        self._blocks_piece("page%d-doevents" % number, at)
        at = self._size()
        self.blocks += self._event(page.objects[0], "loadend", start) + [b""]
        self._blocks_piece(self._name(0, "event-loadend"), at)
        if names is not None:
            self.data = _p_page_entries(page.objects[0], number, base, project)
        else:
            self.data = _page_entries(page.objects[0], number, base, project)
        self.records = _page_record(page.objects[0], code_places[0], base, names)
        self._entries_and_record_pieces(0, 0, 0)
        for (page_object, module, place, _), places in zip(components, code_places[1:]):
            data_at, records_at = len(self.data), len(self.records)
            if names is not None:
                table = component_types.p_table(module, page_object, project)
                self.data += component_types.p_component_entries(
                    table, module.ENTRIES, place, getattr(module, "P_OWNER_TOPS", None),
                    getattr(module, "P_OWNER", None))
                self.records += _component_record(page_object, module, place, places, names,
                                                  table)
            else:
                self.data += module.data(page_object, project, place)
                self.records += _component_record(page_object, module, place, places)
            self._entries_and_record_pieces(place.object_id, data_at, records_at)

    def _size(self) -> int:
        """Returns the size of the page's blocks so far, with their size
        words: where the next block starts, from their start. A layout only
        adds blocks, and never changes one, so each is counted once, as it
        is added; counting them all again at each call would take time in
        proportion to the square of a page's blocks."""
        for block in self.blocks[self._counted:]:
            self._sized += 4 + len(block)
        self._counted = len(self.blocks)
        return self._sized

    def _name(self, object_id: int, what: str) -> str:
        """Returns the name of the piece of the object `object_id` of this
        page that holds `what`, such as "memory": "page0-1-memory"."""
        return "page%d-%d-%s" % (self.number, object_id, what)

    def _blocks_piece(self, name: str, at: int):
        """Notes the blocks added since the place `at`, from the start of the
        page's blocks, as the piece `name`, if there are any."""
        end = self._size()
        if end > at:
            self.pieces.append(Piece(name, _BLOCKS, at, end))

    def _memory_pieces(self, at: int, run: bytes, memories: list):
        """Notes the pieces of the page's memory block, the last block added,
        which starts at the place `at`, from the start of the page's blocks:
        its size word and the page's run, then each object's memory,
        `memories` giving each as (its ID, its memory, the size of the head
        it starts with), empty for a global one, then the rest, its texts and
        its buffers' size. On P, an object's memory starts with its record's
        head, which the frame writes, so the head is a piece of its own, and
        the memory piece holds the values its type writes after it. A type's
        own bytes that lie within the head's are in the head piece."""
        self.pieces.append(Piece("page%d-memory-run" % self.number, _BLOCKS, at,
                                 at + 4 + len(run)))
        at += 4 + len(run)
        for object_id, memory, head_size in memories:
            for name, size in (("head", head_size), ("memory", len(memory) - head_size)):
                if memory and size:
                    self.pieces.append(Piece(self._name(object_id, name), _BLOCKS, at,
                                             at + size))
                    at += size
        self.pieces.append(Piece("page%d-texts" % self.number, _BLOCKS, at, self._size()))

    def _entries_and_record_pieces(self, object_id: int, data_at: int, records_at: int):
        """Notes the entries and the record of the object `object_id`, added
        to the page's data and records from the places `data_at` and
        `records_at`, as its pieces."""
        self.pieces += [Piece(self._name(object_id, "entries"), _DATA, data_at, len(self.data)),
                        Piece(self._name(object_id, "record"), _RECORDS, records_at,
                              len(self.records))]

    def _place(self, start: int) -> int:
        return start + self._size()

    def _event(self, page_object, event_name: str, start: int, before: list = ()) -> list:
        """Returns the blocks of the code of `page_object`'s event `event_name`,
        its labels, gotos, and calls written (label_numbers.resolved). Its
        blocks follow the page's blocks so far, from the place `start`, and
        then `before`, the blocks the Nextion Editor writes of its own at the
        event's start, as a timer's "S " block."""
        name = component_types.object_name(page_object)
        place = CodePlace(self.number, name, event_name)
        blocks = _code_blocks(self.context, label_numbers.event_code(page_object, event_name),
                              place, self.encode_code)
        blocks = label_numbers.resolved(blocks, self.s_numbers.events[self.number, name,
                                                                     event_name],
                                        self._place(start) + len(encode_blocks(before)),
                                        self.macros)
        # A component with a key opens its keyboard page as it is released,
        # after its own code (component_types.key_lines).
        keys = component_types.key_lines(page_object, _object_id(page_object))
        if event_name == "up" and keys:
            blocks += self.encode_code(keys, place, self.context)
        # A page's unload event ends with what its components add there, as
        # a file stream's close (unload_lines), after the page's own code.
        if event_name == "unload" and page_object is self.objects[0]:
            closing = [line for component in self.objects[1:]
                       for line in _unload_lines(component)]
            if closing:
                blocks += self.encode_code(closing, place, self.context)
        return blocks

    def _named_events(self, page_object, event_names, start: int, places: dict,
                      event_starts: dict = None):
        """Adds each event of `event_names`: its name, the blocks
        `event_starts` gives it, if any, its code, then a 0 word, noting in
        `places` where the blocks of each that has some start."""
        for event_name in event_names:
            at = self._size()
            self.blocks.append(event_name.encode("ascii"))
            own = (event_starts or {}).get(event_name, [])
            event_blocks = own + self._event(page_object, event_name, start, own)
            if event_blocks:
                places[event_name] = self._place(start)
            self.blocks += event_blocks + [b""]
            self._blocks_piece(self._name(_object_id(page_object), "event-" + event_name), at)

    def _page_own_blocks(self, page_object, start: int) -> dict:
        """Adds the page's own blocks: its drawing, an empty background
        fill, and its events; on P, a drawing without blocks, and its
        events. Its drawing is a fill with its bco, its pic at its place,
        or, for a page with no background, no blocks. Returns its record's
        places."""
        places = {"drawing": self._place(start)}
        at = self._size()
        if self.names is not None:
            # On P, the page has no fill: its drawing's blocks are the 0 word
            # alone.
            self.blocks.append(b"")
        else:
            drawing = page_drawing(page_object, self.page_entry)
            if drawing:
                places[_FIRST_BLOCK] = places["drawing"]
            self.blocks += drawing + AFTER_PAGE_DRAWING
        self._blocks_piece(self._name(0, "drawing"), at)
        self._named_events(page_object, NAMED_EVENTS, start, places)
        return places

    def _component_blocks(self, module, page_object, place: ObjectPlace, start: int) -> dict:
        """Adds a component's blocks, as its type's `module` gives them: its
        drawing, its background fill, then the refs of the components it
        overlaps (overlaps.py), and its events, each run ended by a 0 word.
        Returns its record's places."""
        places = {"drawing": self._place(start)}
        at = self._size()
        if self.names is not None:
            # On P, a component has no drawing blocks, nor a background
            # fill's run: its drawing's blocks are the 0 word alone.
            self.blocks.append(b"")
            self._blocks_piece(self._name(place.object_id, "drawing"), at)
            self._named_events(page_object, module.EVENTS, start, places)
            return places
        drawing = module.drawing(page_object, self.project, place)
        # A drawing without blocks, as a timer's or a hotspot's, gives the
        # record no first block's place.
        if drawing:
            places[_FIRST_BLOCK] = places["drawing"]
        self.blocks += drawing + [b""]
        self._blocks_piece(self._name(place.object_id, "drawing"), at)
        # A component that is not drawn, as a variable, has no background
        # fill's run.
        if _drawn(module):
            run = (module.background_fill(page_object, self.project, place)
                   + overlaps.ref_blocks(self.context, self.areas, place.object_id))
            # The record gives the run's place when the run has blocks. On a
            # page with no background, it has some only when it has refs.
            if run:
                places[_BACKGROUND_FILL] = self._place(start)
            at = self._size()
            self.blocks += run + [b""]
            self._blocks_piece(self._name(place.object_id, "background-fill"), at)
        event_starts = {}
        if hasattr(module, "event_start"):
            event_starts = {name: module.event_start(page_object, self.project, place, name)
                            for name in module.EVENTS}
        self._named_events(page_object, module.EVENTS, start, places, event_starts)
        return places


# What follows a page's drawing on T, K, and F, in its piece of the user
# code: the drawing's 0 word, then an empty background fill.
AFTER_PAGE_DRAWING = [b"", b""]


def page_drawing(page_object, first_entry: int) -> list:
    """Returns the blocks of the drawing of the page `page_object`, whose
    first entry is `first_entry`, on T, K, and F: a fill with its bco, its
    pic at its place, or, for a page with no background, no blocks. On P and
    E, a page has no drawing but its 0 word."""
    x, y, w, h = place_and_size(page_object)
    background = entry_operand(first_entry + page_entry(page_object, PAGE_BACKGROUND_ENTRY))
    sta = page_sta(page_object)
    if sta == COLOUR:
        return [FILL + b"%d,%d,%d,%d," % (x, y, w, h) + background]
    if sta == PICTURE:
        return [PIC + b"%d,%d," % (x, y) + background]
    return []


def _placed_after(project: Project, components: list, text_place: int, on_p: bool = False
                  ) -> tuple:
    """Returns `components`, each as (its object, its type's module, its
    place, its memory), each that keeps a text (page_text) or a buffer
    (buffer_size) given where it lies, and its memory with it; then the
    texts, in the order of `components`; then the total size of the
    buffers. The first text lies at `text_place`, and the others follow it.
    The first buffer starts at the word after the texts, and the others
    follow it in the same order. A page among `components` has no module.
    On P, `on_p`, each text of a type that has some (P_TEXTS) lies there, in
    the order its type gives them. Raises FrameError for a type whose
    memory's length changes once its text or buffer is placed."""
    places, texts = [], []
    for page_object, module, place, _ in components:
        if on_p and component_types.p_texts(module):
            text_places = {}
            for attribute, maxl, _ in component_types.p_texts(module).values():
                text_places[attribute] = text_place
                texts.append(component_types.p_text(module, page_object, attribute, maxl))
                text_place += len(texts[-1])
            place = replace(place, text_places=text_places)
        elif not on_p and hasattr(module, "page_text"):
            place = replace(place, text_place=text_place)
            texts.append(module.page_text(page_object, project))
            text_place += len(texts[-1])
        places.append(place)
    # The buffers start at the last word, after the texts.
    buffer_place = text_place
    for number, (page_object, module, _, _) in enumerate(components):
        if hasattr(module, "buffer_size"):
            places[number] = replace(places[number], buffer_place=buffer_place)
            buffer_place += module.buffer_size(page_object, project)
    placed = []
    for (page_object, module, _, memory), place in zip(components, places):
        if not on_p and _places_after(module):
            known = module.memory_at(page_object, project, place)
            if len(known) != len(memory):
                raise FrameError("%s's memory is %d bytes once its text or buffer is placed, "
                                 "but %d before" % (component_types.object_name(page_object),
                                                    len(known), len(memory)))
            memory = known
        placed.append((page_object, module, place, memory))
    return placed, texts, buffer_place - text_place


def _drawn(module) -> bool:
    """Whether the type of `module` is drawn: every type but one whose module
    sets DRAWN to False (component_types/__init__.py)."""
    return getattr(module, "DRAWN", True)


def _undrawn_place(module) -> tuple:
    """Returns the place and size the record of a component of the type of
    `module` gives when the type is not drawn: the type's UNDRAWN_PLACE, as
    an audio's, or 0, 0, 1, 1."""
    return getattr(module, "UNDRAWN_PLACE", _UNDRAWN_PLACE)


def _unload_lines(page_object) -> list:
    """Returns the lines the Nextion Editor adds for the component
    `page_object` at the end of its page's unload event (unload_lines in
    component_types/__init__.py), or none for a type without."""
    module = component_types.object_module(page_object)
    return module.unload_lines(page_object) if hasattr(module, "unload_lines") else []


def _places_after(module) -> bool:
    """Whether the type of `module` keeps a text or a buffer after its page's
    components' memory, so that its memory gives where (memory_at)."""
    return hasattr(module, "page_text") or hasattr(module, "buffer_size")


def _memory_run(objects: int) -> bytes:
    """Returns the run of 0xFF bytes that starts the memory of a page of
    `objects` objects, the page included: one byte each, rounded up to a
    multiple of 4. It is 4 bytes for up to 4 objects, 8 for 5 to 8."""
    return b"\xff" * (4 * -(-objects // 4))


def _p_memory_run(base: int, bases: list) -> bytes:
    """Returns what starts the memory of a page on P: the place of the
    page's own memory, `base`, then that of each of its components'
    memories, `bases`, in ID order, 4 bytes each, where T has a run of
    0xFF bytes (_memory_run)."""
    return struct.pack("<%dI" % (1 + len(bases)), base, *bases)


def _objects_table(objects: list) -> bytes:
    """Returns a page's objects' table: each object's name's CRC and its ID,
    the page's own included, in the order of their CRCs."""
    return b"".join(struct.pack("<IH", crc, object_id) for crc, object_id in sorted(
        (page_name_crc(page_object.attribute("objname")), object_id)
        for object_id, page_object in enumerate(objects)))


def _variable_table(variables: list) -> bytes:
    """Returns the int variables' table: for each, its name's CRC, its
    offset, and 9, in the order of their CRCs."""
    rows = sorted((byte_form_crc(name.encode("ascii")), 4 * offset)
                  for offset, (name, _) in enumerate(variables))
    return b"".join(struct.pack("<III", crc, offset, _VARIABLE_NUMBER) for crc, offset in rows)


def _page_entries(page, number: int, base: int, project: Project) -> bytes:
    """Returns the entries of the page whose ID is `number`, in `project`.
    Entries 23 and 24 give places counted from the memory base, and the
    others the page's own values; their highest values fit the page's sta
    and its background (_with_background_entry)."""
    entries = object_entries(page, 0)
    entries[page_entry(page, 23)] = (base + 4, 2, 0, 0x121)
    return _with_background_entry(entries, page, number, base, base + 6, project)


def _with_background_entry(entries: dict, page, number: int, base: int, place: int,
                           project: Project) -> bytes:
    """Returns the page's entries, `entries` {number: (value, highest,
    lowest, code)} and the entry of its background, whose value lies at
    `place` in memory: its bco's, any colour, or its pic's, up to the
    project's last picture. A page with no background has no such entry,
    and one entry fewer (component_types.page_entries)."""
    sta = page_sta(page)
    background = page_entry(page, PAGE_BACKGROUND_ENTRY)
    if sta == COLOUR:
        entries[background] = (place, 0xFFFF, 0, 0x232)
    elif sta == PICTURE:
        pictures = project.resource_count("picture")
        entries[background] = (place, pictures - 1, 0, 0x232)
    return packed_entries(entries, component_types.page_entries(page),
                          ObjectPlace(number, 0, 0, 0, base,
                                      two_byte_start=two_byte_start(project.settings.encoding)))


def _page_slots(page) -> dict:
    """Returns the slots of the page `page` that name an entry, its
    background's among them (_PAGE_BACKGROUND_SLOTS)."""
    slots = {slot: page_entry(page, entry) for slot, entry in _PAGE_SLOTS.items()}
    name = _BACKGROUND_NAMES.get(page_sta(page))
    if name:
        slots[_PAGE_BACKGROUND_SLOTS[name]] = page_entry(page, PAGE_BACKGROUND_ENTRY)
    return slots


def page_memory_of(page_object) -> bytes:
    """Returns the memory of the page `page_object` on T and K: its swipe
    targets up, down, left, and right, 1 byte each, then its sta and its
    background (_page_background), 2 bytes each."""
    up, down, left, right = (component_types.attribute_number(page_object, name)
                             for name in ("up", "down", "left", "right"))
    return struct.pack(PAGE_MEMORY_FORMAT, up, down, left, right, page_sta(page_object),
                       _page_background(page_object))


def _page_background(page_object) -> int:
    """Returns the background the page `page_object` keeps in its memory:
    its bco, its pic, or 0 for a page with no background."""
    name = _BACKGROUND_NAMES.get(page_sta(page_object))
    return component_types.attribute_number(page_object, name) if name else 0


def _p_page_entries(page, number: int, base: int, project: Project) -> bytes:
    """Returns the entries of the page whose ID is `number`, in `project`,
    on P: each a place in its memory, from its base (_P_PAGE_ENTRIES), and
    its background's entry, as on T. With an effect, its first's and its
    time's follow its effect's (component_types.with_p_effect)."""
    entries = {entry: (base + offset, highest, lowest, code)
               for entry, (_, offset, highest, lowest, code)
               in component_types.with_p_effect(_P_PAGE_ENTRIES, page).items()}
    return _with_background_entry(entries, page, number, base, base + _P_BACKGROUND_PLACE,
                                  project)


def _p_page_memory(page_object, places: dict, base: int) -> bytes:
    """Returns the page's memory on P: its record's head but for the place
    of its run, then its values (_P_PAGE_VALUES), each its own or its
    default, its first and its time 0 without an effect, then its
    background (_page_background)."""
    values = b""
    of_an_effect = {name for name, *_ in component_types.P_EFFECT_ENTRIES.values()}
    for name, form, default in _P_PAGE_VALUES:
        value = page_object.attribute(name)
        if name in of_an_effect and not component_types.has_effect(page_object):
            value = None
        values += struct.pack(form, default if value is None
                              else int.from_bytes(value, "little"))
    return (_p_memory_head(page_object, _record_head(page_object, 0, places, base)[:_HEAD_SIZE])
            + values + struct.pack("<H", _page_background(page_object)))


# Where an object's memory on P gives its drag, then its movex and its
# movey, in its record's head, where the record itself gives zeros.
P_DRAG_PLACE, P_MOVES_PLACE = 32, 36


def _p_head_size(module) -> int:
    """Returns how many bytes of its record's head a component's memory on P
    starts with: its type's own size (P_HEAD_SIZE), or a whole head's."""
    return getattr(module, "P_HEAD_SIZE", _HEAD_SIZE)


def _p_component_memory(page_object, module, place: ObjectPlace, places: dict,
                        project: Project) -> bytes:
    """Returns the memory on P of the component `page_object`, which `module`
    describes, at `place`, its blocks at `places` (_record_head), in
    `project`: its record's head but for its last place, with its drag, its
    movex, and its movey (_p_memory_head), or as much of its record's head as
    its type gives (P_HEAD_SIZE); then its values
    (component_types.p_component_memory), with the bytes no entry gives
    (component_types.p_memory_extras), which may lie within its head."""
    head = _record_head(page_object, place.object_id, places, place.base, drawn=_drawn(module),
                        events=bool(module.EVENTS), undrawn_place=_undrawn_place(module))
    # A head of the type's own size, as a file stream's 4 bytes, ends before
    # the drag and the moves a whole head holds.
    head = (head[:_p_head_size(module)] if hasattr(module, "P_HEAD_SIZE")
            else _p_memory_head(page_object, head[:_HEAD_SIZE]))
    return component_types.p_component_memory(
        page_object, head, component_types.p_table(module, page_object, project),
        module.P_MEMORY_SIZE, component_types.p_memory_extras(module, page_object, project, place))


def _p_memory_head(page_object, head: bytes) -> bytes:
    """Returns `head`, the head of `page_object`'s record, as its memory on
    P holds it: with its drag, its movex, and its movey."""
    head = bytearray(head)
    head[P_DRAG_PLACE] = _number_or(page_object, "drag", 0)
    head[P_MOVES_PLACE:P_MOVES_PLACE + 4] = struct.pack(
        "<2H", _number_or(page_object, "movex", 0), _number_or(page_object, "movey", 0))
    return bytes(head)


def _page_record(page_object, places: dict, base: int, names: list = None) -> bytes:
    """Returns the record of the page `page_object`, whose blocks lie at
    `places` (_record_head) and whose memory starts at `base`. On T and K,
    its head, then the slots of its entries (_page_slots). On P, given the
    attributes the records name, `names` (_attribute_names): its head, then
    the entry of each of `names` the page has, or 0xFFFF for one it lacks
    (component_types.p_page_named_entries)."""
    if names is None:
        return _record(page_object, 0, places, base, _page_slots(page_object))
    named = component_types.p_page_named_entries(page_object)
    return _record_head(page_object, 0, places, base) + struct.pack(
        "<%dH" % len(names), *(named.get(name, 0xFFFF) for name in names))


def _component_record(page_object, module, place: ObjectPlace, places: dict,
                      names: list = None, table: dict = None) -> bytes:
    """Returns the record of the component `page_object`, of the type of
    `module`, at `place`, whose blocks lie at `places` (_record_head). On T
    and K, its head, then the slots its type gives (_record), each its
    entry counted from its page's. On P, given the attributes the records
    name, `names` (_attribute_names), and the component's P table `table`
    (component_types.p_table): its head, then the entry of each of `names`
    the table gives, counted the same way, or 0xFFFF for one it lacks."""
    def counted(entry: int) -> int:
        return place.first_entry - place.page_entry + entry
    if names is None:
        slots = {slot: counted(entry) for slot, entry in module.record_slots().items()}
        return _record(page_object, place.object_id, places, place.base, slots,
                       drawn=_drawn(module), events=bool(module.EVENTS))
    entries = {name: entry for entry, (name, *_) in table.items()}
    head = _record_head(page_object, place.object_id, places, place.base, drawn=_drawn(module),
                        events=bool(module.EVENTS), undrawn_place=_undrawn_place(module))
    return head + struct.pack("<%dH" % len(names), *(
        counted(entries[name]) if name in entries else 0xFFFF for name in names))


def _record(page_object, object_id: int, places: dict, base: int, slots: dict,
            drawn: bool = True, events: bool = True) -> bytes:
    """Returns the record of `page_object`, whose ID is `object_id`: its
    type, its ID, its vscope, a byte of what it is (_record_kind), the
    place of its drawing's first block, the places _RECORD_PLACES names,
    its base, its place, size, and right and bottom edges, the place of its
    drawing's run, then its slots. A component whose drawing has no blocks,
    as a timer or a hotspot, has no first block's place. One that is not
    `drawn`, as a variable or a timer, has a place and size of 0, 0, 1, 1."""
    object_slots = [0xFFFF] * _RECORD_SLOTS
    for slot, entry in slots.items():
        object_slots[slot] = entry
    return (_record_head(page_object, object_id, places, base, drawn, events)
            + struct.pack("<%dH" % _RECORD_SLOTS, *object_slots))


def _record_head(page_object, object_id: int, places: dict, base: int, drawn: bool = True,
                 events: bool = True, undrawn_place: tuple = _UNDRAWN_PLACE) -> bytes:
    """Returns the head of the record of `page_object`, before its slots,
    as _record gives it: 56 bytes. One not `drawn` gives `undrawn_place`,
    its type's (_undrawn_place), as its place and size."""
    x, y, w, h = place_and_size(page_object) if drawn else undrawn_place
    drawing = places["drawing"]
    # After the base: a 0 byte, its sendkey, its aph, and five 0 bytes. An
    # object without an aph, as a timer, gives 127, the most opaque.
    sendkey, aph = (_number_or(page_object, name, default)
                    for name, default in (("sendkey", 0), ("aph", _OPAQUE)))
    return (bytes([page_object.attribute("type")[0], object_id,
                   int(component_types.is_global(page_object)), _record_kind(drawn, events)])
            + struct.pack("<I", places.get(_FIRST_BLOCK, _NO_PLACE))
            + struct.pack("<5I", *(next((places[name] for name in names if name in places),
                                        _NO_PLACE) for names in _RECORD_PLACES))
            + struct.pack("<IxBBx2H", base, sendkey, aph, 0, 0)
            # Signed, as an audio's place starts left of the screen, at -50.
            + struct.pack("<6h", x, y, w, h, x + w - 1, y + h - 1) + struct.pack("<I", drawing))


def _number_or(page_object, name: str, default: int) -> int:
    """Returns the number of `page_object`'s attribute `name`, or `default`
    when it has none."""
    value = page_object.attribute(name)
    return default if value is None else int.from_bytes(value, "little")


def _record_kind(drawn: bool, events: bool) -> int:
    """Returns the byte after a record's type and ID: 0x07, plus 0x10 for an
    object that is drawn, plus 0x20 for one whose type has events. So 0x37
    for a page and every component drawn seen, 0x07 for a variable, and
    0x27 for a timer, which has an event but is not drawn."""
    return 0x07 | (0x10 if drawn else 0) | (0x20 if events else 0)


def _object_id(page_object) -> int:
    return int.from_bytes(page_object.attribute("id") or b"\x00", "little")
