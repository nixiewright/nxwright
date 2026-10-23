"""The text form of a page block: readable, and exact enough to rebuild the block.

Example:

  page settings
  header_size = 56
  header_16 = 00000000004f2100
  header_40 = 01430100000000000000000000000000

  object 0 settings
    marker att-28
    type = 121
    objname = "settings"
    x = 0
    val:u8 = 0
    event load
      | if(pic_dialog!=0)
      | {
      | }
    event down

Rules:
  - Records appear in stored order. The object table, block size, and object
    count are not written; they are derived when the block is encoded.
  - The "object" line repeats the object's index and objname as a label. The
    parser checks that the label matches.
  - Numbers are unsigned little-endian values written in decimal. Their byte
    width comes from the width tables below, keyed by the object's "type"
    attribute and the attribute name. A width the tables do not predict is
    written explicitly, as in "val:u8". A value that is not 1, 2, or 4 bytes
    long is written as a quoted string of its bytes.
  - Strings are quoted. Printable ASCII is written as is; quotes, backslashes
    and every other byte are escaped ("\\x0d").
  - Event code lines follow "| ". A line that is not printable ASCII, or that
    ends in a space, is written as "raw <hex>" so the text stays exact.
  - A record the parser did not recognise is written as "raw <hex>".
"""
import re

from nxwright import NxwrightError
from nxwright.project.page_block import (Attribute, Event, Marker, PageBlock, PageObject,
                                         RawRecord)

# Attributes whose values are text on every object. The page text treats every
# other attribute as a number, but for those of _TYPE_STRING_ATTRIBUTES.
STRING_ATTRIBUTES = frozenset({"objname", "txt", "path", "filter"})

# Byte width of each numeric attribute, as found in project files the Editor saved.
_DEFAULT_WIDTHS = {
    "aph": 1, "autoleft": 1, "bco": 2, "bco1": 2, "bco2": 2, "borderc": 2, "borderw": 1,
    "bpic": 2, "buff": 4, "buffsize": 4, "ch": 1, "close": 4, "dez": 1, "dir_m": 2, "dis": 1,
    "down": 1, "drag": 1, "effect": 1, "en": 1, "endx": 2, "endy": 2, "filter_m": 2, "find": 4,
    "first": 1, "font": 1, "fwarning": 1, "groupid0": 4, "groupid1": 4, "h": 2, "hig": 1,
    "id": 1, "isbr": 1, "key": 1, "left": 1, "lockobj": 1, "maxval": 2, "maxval_y": 4,
    "minval": 2, "mode": 1, "molloc": 4, "molloc_s": 4, "movex": 2, "movey": 2, "open": 4,
    "path_m": 2, "pco": 2, "pco1": 2, "pco2": 2, "pic": 2, "pic1": 2, "pic2": 2, "picc": 2,
    "picc1": 2, "picc2": 2, "ppic": 2, "psta": 1, "pw": 1, "qty": 4, "read": 4, "right": 1,
    "sendkey": 1, "spax": 1, "spay": 1, "sta": 1, "style": 1, "tim": 2, "time": 2, "txt_m": 2,
    "txt_maxl": 2, "type": 1, "up": 1, "val": 4, "val_y": 4, "vscope": 1, "vvs0": 2, "vvs1": 2,
    "vvs2_m": 2, "w": 2, "wid": 1, "write": 4, "x": 2, "xcen": 1, "y": 2, "ycen": 1,
}
# Widths that differ by component type, keyed by (type, attribute). They come
# from a sample project with one newly added component of each type.
_TYPE_WIDTHS = {
    (0, "dir"): 1, (0, "dis"): 2, (0, "gdc"): 2, (0, "gdh"): 1, (0, "gdw"): 1, (0, "inittrue"): 1,
    (0, "objHig"): 2, (0, "objWid"): 2, (0, "pco0"): 2, (0, "pco3"): 2,
    (1, "val"): 2,
    (2, "dis"): 2, (2, "from"): 1, (2, "loop"): 1, (2, "stim"): 4, (2, "tim"): 4, (2, "vid"): 2,
    (3, "dis"): 2, (3, "fps"): 1, (3, "from"): 1, (3, "loop"): 1, (3, "stim"): 4, (3, "tim"): 4,
    (3, "vid"): 2,
    (4, "dis"): 2, (4, "fps"): 1, (4, "from"): 1, (4, "loop"): 1, (4, "stim"): 4, (4, "tim"): 4,
    (4, "vid"): 2,
    (5, "val"): 1,
    (53, "val"): 1,
    (54, "format"): 1, (54, "lenth"): 1,
    (55, "dir"): 1, (55, "vvs2"): 2, (55, "vvs3"): 2,
    (56, "val"): 1,
    (57, "val"): 1,
    (59, "vvs0"): 1, (59, "vvs1"): 1,
    (61, "dir"): 1, (61, "drastate"): 1, (61, "pco3"): 2, (61, "qty"): 1, (61, "val"): 1, (61, "vvs0"): 1,
    (61, "vvs1"): 1,
    (62, "leftshow"): 1,
    (65, "up"): 4,
    (66, "clear"): 4, (66, "delete"): 4, (66, "dez"): 2, (66, "format_m"): 2, (66, "gdc"): 2,
    (66, "gdh"): 1, (66, "gdw"): 1, (66, "init"): 1, (66, "insert"): 4, (66, "lenth"): 4,
    (66, "maxval"): 4, (66, "maxval_x"): 4, (66, "order"): 1, (66, "up"): 4, (66, "val_x"): 4,
    (67, "val"): 1,
    (98, "val"): 1,
    (106, "val"): 1,
    (122, "down"): 2, (122, "format"): 2, (122, "left"): 2, (122, "up"): 2, (122, "val"): 2,
    (122, "vvs0"): 1, (122, "vvs1"): 1, (122, "vvs2"): 1,
}

_EXPLICIT_WIDTHS = {1: "u8", 2: "u16", 4: "u32"}
_WIDTH_BY_SUFFIX = {suffix: width for width, suffix in _EXPLICIT_WIDTHS.items()}

_ATTRIBUTE_LINE = re.compile(r"([A-Za-z0-9_]+)(?::(u8|u16|u32))? = (.*)")
_OBJECT_LINE = re.compile(r"object (\d+)(?: (\S+))?")
_EVENT_NAME = re.compile(r"[a-z]+")
_DECIMAL = re.compile(r"[0-9]+")


# Attributes that hold text on some types only; elsewhere the name is a
# number. A data record's `dir` holds its columns' titles, and a file
# browser's the folder it shows; a scrolling text's, a combo box's, and a
# waveform's is a direction. A file browser's `vvs2` holds its icons; a
# scrolling text's is its text's width, and a gauge's a width of its needle.
_TYPE_STRING_ATTRIBUTES = frozenset({(66, "format"), (65, "dir"), (66, "dir"), (65, "vvs2")})
# Number attributes that page files and defaults files held as texts of their
# stored bytes, before nxwright told them apart from the texts of the same
# name: a scrolling text's `dir` of 1 was written "\u0001".
_ONCE_TEXTS = frozenset({"dir", "vvs2"})


def is_string_attribute(object_type, name: str) -> bool:
    """True when attribute `name` holds text on an object whose "type"
    attribute is `object_type`."""
    return name in STRING_ATTRIBUTES or (object_type, name) in _TYPE_STRING_ATTRIBUTES


def text_form_number(object_type, name: str, text: str, encode):
    """Returns the number that `text` stands for, given to the number
    attribute `name` of an object of type `object_type` as page files and
    defaults files nxwright wrote before held it (_ONCE_TEXTS): the text's
    bytes, by `encode`, are the number's stored bytes, low byte first. None
    for another attribute, and for bytes of another count than the
    attribute's width."""
    if name not in _ONCE_TEXTS or is_string_attribute(object_type, name):
        return None
    data = encode(text)
    if len(data) != expected_width(object_type, name):
        return None
    return int.from_bytes(data, "little")


def expected_width(object_type, name: str):
    """Returns the byte width the tables predict for attribute `name` on an
    object whose "type" attribute is `object_type`, or None when they have no
    entry. `object_type` is None while the object's type is not yet known; then
    only the default widths apply."""
    return _TYPE_WIDTHS.get((object_type, name), _DEFAULT_WIDTHS.get(name))


def page_to_text(page: PageBlock) -> str:
    """Returns the text form of `page`. The stamp is not written."""
    lines = ["page " + page.name,
             "header_size = %d" % page.header_size,
             "header_16 = " + page.unknown_16.hex(),
             "header_40 = " + page.unknown_40.hex()]
    for index, page_object in enumerate(page.objects):
        lines.append("")
        lines.extend(_object_to_lines(index, page_object))
    return "\n".join(lines) + "\n"


def _object_to_lines(index: int, page_object: PageObject) -> list:
    label = "object %d" % index
    label_name = _label_name(page_object)
    if label_name is not None:
        label += " " + label_name
    lines = [label]
    object_type = None
    for item in page_object.items:
        if isinstance(item, Attribute):
            lines.append("  " + _attribute_to_text(item, object_type))
            if item.name == "type" and len(item.value) == 1:
                object_type = item.value[0]
        elif isinstance(item, Event):
            lines.append("  event " + item.name)
            lines.extend("    " + _code_line_to_text(line) for line in item.lines)
        elif isinstance(item, Marker) and _is_plain_text(item.text):
            lines.append("  marker " + item.text.decode("ascii"))
        else:
            body = item.text if isinstance(item, Marker) else item.body
            lines.append("  raw " + body.hex())
    return lines


def _attribute_to_text(attribute: Attribute, object_type) -> str:
    value = attribute.value
    if is_string_attribute(object_type, attribute.name):
        return "%s = %s" % (attribute.name, escape_string(value))
    number = int.from_bytes(value, "little")
    if len(value) == expected_width(object_type, attribute.name):
        return "%s = %d" % (attribute.name, number)
    if len(value) in _EXPLICIT_WIDTHS:
        return "%s:%s = %d" % (attribute.name, _EXPLICIT_WIDTHS[len(value)], number)
    return "%s = %s" % (attribute.name, escape_string(value))


def _code_line_to_text(line: bytes) -> str:
    if all(0x20 <= byte < 0x7f for byte in line) and not line.endswith(b" "):
        return "| " + line.decode("ascii")
    return "raw " + line.hex()


def _label_name(page_object: PageObject):
    """Returns the objname shown on an object line, or None when there is no
    objname, or it is empty or holds a space or a byte outside printable
    ASCII, which a label cannot show."""
    objname = page_object.attribute("objname")
    if objname is None or not _is_plain_text(objname):
        return None
    return escape_string(objname)[1:-1]


def _is_plain_text(text: bytes) -> bool:
    """Returns whether `text` is non-empty printable ASCII without spaces."""
    return len(text) > 0 and all(0x20 < byte < 0x7f for byte in text)


def escape_string(value: bytes) -> str:
    """Returns `value` as a quoted string: printable ASCII as is, quotes and
    backslashes escaped with a backslash, every other byte as \\xNN."""
    out = []
    for byte in value:
        if byte in (0x22, 0x5c):
            out.append("\\" + chr(byte))
        elif 0x20 <= byte < 0x7f:
            out.append(chr(byte))
        else:
            out.append("\\x%02x" % byte)
    return '"' + "".join(out) + '"'


def unescape_string(text: str) -> bytes:
    """Reverses escape_string. `text` includes the surrounding quotes.

    Raises NxwrightError on a missing quote or an unknown escape.
    """
    if len(text) < 2 or text[0] != '"' or text[-1] != '"':
        raise NxwrightError("expected a quoted string, got %s" % text)
    out = bytearray()
    body = text[1:-1]
    position = 0
    while position < len(body):
        char = body[position]
        if char != "\\":
            if char == '"' or not 0x20 <= ord(char) < 0x7f:
                raise NxwrightError("unescaped character %r in string" % char)
            out.append(ord(char))
            position += 1
        elif body[position + 1:position + 2] in ('"', "\\"):
            out.append(ord(body[position + 1]))
            position += 2
        elif body[position + 1:position + 2] == "x" and re.fullmatch(
                r"[0-9a-f]{2}", body[position + 2:position + 4]):
            out.append(int(body[position + 2:position + 4], 16))
            position += 4
        else:
            raise NxwrightError("unknown escape in string %s" % text)
    return bytes(out)


def page_from_text(text: str) -> PageBlock:
    """Parses the text form of a page. The stamp of the result is 0.

    Raises NxwrightError, naming the line, when the text does not follow the
    rules in this module's docstring.
    """
    return _PageTextParser(text).parse()


class _PageTextParser:
    """Parses the text form of a page one line at a time. Indentation tells the
    levels apart: page lines at column 0, object records at 2 spaces, event
    code lines at 4 spaces."""

    def __init__(self, text: str):
        self._lines = text.split("\n")
        self._line_number = 0
        self._header = {}
        self._page_name = None
        self._objects = []
        self._labels = []
        self._object_type = None
        self._event = None

    def parse(self) -> PageBlock:
        """Returns the page the text describes."""
        for self._line_number, line in enumerate(self._lines, start=1):
            if line.strip():
                self._parse_line(line)
        self._check_labels()
        for key in ("header_size", "header_16", "header_40"):
            if key not in self._header:
                raise NxwrightError("page text has no %s line" % key)
        if self._page_name is None:
            raise NxwrightError("page text has no page line")
        return PageBlock(name=self._page_name, header_size=self._header["header_size"],
                         unknown_16=self._header["header_16"],
                         unknown_40=self._header["header_40"], objects=self._objects)

    def _error(self, message: str) -> NxwrightError:
        return NxwrightError("page text line %d: %s" % (self._line_number, message))

    def _parse_line(self, line: str):
        # Every byte outside printable ASCII is escaped or hex, so the text is pure ASCII.
        if not line.isascii():
            raise self._error("non-ASCII character; use an escape or a raw line")
        if line.startswith("    "):
            self._parse_code_line(line[4:])
        elif line.startswith("  "):
            self._parse_object_line(line[2:])
        else:
            self._parse_page_line(line)

    def _parse_page_line(self, line: str):
        self._event = None
        if line.startswith("page "):
            self._page_name = line[5:]
            return
        match = _OBJECT_LINE.fullmatch(line)
        if match:
            self._objects.append(PageObject())
            self._labels.append((self._line_number, int(match.group(1)), match.group(2)))
            self._object_type = None
            return
        key, separator, value = line.partition(" = ")
        if not separator or key not in ("header_size", "header_16", "header_40"):
            raise self._error("unexpected line: %s" % line)
        if key == "header_size":
            if not _DECIMAL.fullmatch(value):
                raise self._error("bad value for header_size")
            self._header[key] = int(value)
        else:
            self._header[key] = self._hex(value)

    def _parse_object_line(self, line: str):
        if not self._objects:
            raise self._error("record before the first object line")
        self._event = None
        items = self._objects[-1].items
        if line.startswith("marker "):
            items.append(Marker(line[7:].encode("ascii")))
        elif line.startswith("raw "):
            items.append(RawRecord(self._hex(line[4:])))
        elif line.startswith("event "):
            if not _EVENT_NAME.fullmatch(line[6:]):
                raise self._error("bad event name")
            self._event = Event(line[6:], [])
            items.append(self._event)
        else:
            items.append(self._parse_attribute(line))

    def _parse_attribute(self, line: str) -> Attribute:
        match = _ATTRIBUTE_LINE.fullmatch(line)
        if not match:
            raise self._error("unexpected line: %s" % line)
        name, suffix, value_text = match.groups()
        if value_text.startswith('"'):
            try:
                value = unescape_string(value_text)
            except NxwrightError as error:
                raise self._error(str(error)) from None
        else:
            value = self._number(name, suffix, value_text)
        if name == "type" and len(value) == 1:
            self._object_type = value[0]
        return Attribute(name, value)

    def _number(self, name: str, suffix, value_text: str) -> bytes:
        width = _WIDTH_BY_SUFFIX[suffix] if suffix else expected_width(self._object_type, name)
        if width is None:
            raise self._error("no known width for %s; write it as %s:u8, :u16 or :u32"
                              % (name, name))
        if not _DECIMAL.fullmatch(value_text):
            raise self._error("bad number for %s" % name)
        try:
            return int(value_text).to_bytes(width, "little")
        except OverflowError:
            raise self._error("%s does not fit in %d bytes" % (name, width)) from None

    def _parse_code_line(self, line: str):
        if self._event is None:
            raise self._error("code line outside an event")
        if line.startswith("| "):
            self._event.lines.append(line[2:].encode("ascii"))
        elif line.startswith("raw "):
            self._event.lines.append(self._hex(line[4:]))
        else:
            raise self._error("code lines start with '| ' or 'raw '")

    def _hex(self, text: str) -> bytes:
        try:
            return bytes.fromhex(text)
        except ValueError:
            raise self._error("bad hex") from None

    def _check_labels(self):
        """Checks each object line's index and name against the object it labels."""
        for index, (line_number, label_index, label_name) in enumerate(self._labels):
            expected_name = _label_name(self._objects[index])
            if label_index != index or label_name != expected_name:
                raise NxwrightError("page text line %d: object label does not match "
                                    "index %d and objname %s" % (line_number, index, expected_name))
