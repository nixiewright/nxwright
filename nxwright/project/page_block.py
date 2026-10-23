"""Page blocks ("N.pa"): parsing into objects and records, and encoding back.

Layout of a page block, all numbers little-endian:
  +0   u32       stamp, a checksum over the rest of the block (see stamp.py);
                 this module keeps it as stored and does not compute it
  +4   u32       total block size
  +8   u32       header size, 56 in every file seen
  +12  u32       object count
  +16  8 bytes   the system page mark (page_header.py)
  +24  char[16]  page name, NUL-padded
  +40  16 bytes  the project's character encoding (page_header.py)
  +56  object table: per object a u32 offset (from +56), a u32 length, and a
       u32 that is 0 (page files use 1 for the fonts they embed)
  then the object bodies, back to back.

An object body is a run of records, each a u32 length then that many bytes,
ended by a zero length. An event marker "codes<event>-<n>" means the next n
records are the lines of that event's code, whatever their length. Any other
record of 16 bytes or more is an attribute: a NUL-padded 16-byte name, then
the value. A shorter record is a marker, such as "att-39" (the component
class).
"""
from dataclasses import dataclass, field
import re
import struct

from nxwright import NxwrightError

HEADER_SIZE = 56
_NAME_SIZE = 16
_TABLE_ENTRY_SIZE = 12
_EMBEDDED_RESOURCE = 1
_EVENT_MARKER = re.compile(rb"codes([a-z]+)-(\d+)")
_ATTRIBUTE_NAME = re.compile(rb"[A-Za-z0-9_]+")


@dataclass
class Attribute:
    """A named value. `value` holds the stored bytes; their meaning depends on the name."""
    name: str
    value: bytes


@dataclass
class Marker:
    """A short record that is not an event marker, such as a component class "att-39"."""
    text: bytes


@dataclass
class Event:
    """The code attached to one event, such as "down" (Touch Press)."""
    name: str
    lines: list


@dataclass
class RawRecord:
    """A record whose shape the parser does not recognise, kept byte for byte."""
    body: bytes


@dataclass
class PageObject:
    """The page itself or one of its components: its records in stored order."""
    items: list = field(default_factory=list)

    def attribute(self, name: str):
        """Returns the value bytes of the first attribute called `name`, or None."""
        for item in self.items:
            if isinstance(item, Attribute) and item.name == name:
                return item.value
        return None


@dataclass
class PageBlock:
    """A parsed page block.

    `unknown_16` and `unknown_40` are the header bytes at +16 and +40, kept as
    stored. Size, object count, and the object table are not kept: encode_page
    derives them.
    """
    name: str
    header_size: int
    unknown_16: bytes
    unknown_40: bytes
    objects: list
    stamp: int = 0


def parse_page(block: bytes) -> PageBlock:
    """Parses a whole page block.

    Raises NxwrightError when the header, object table, or a record does not
    fit the layout described in this module's docstring.
    """
    if len(block) < HEADER_SIZE:
        raise NxwrightError("page block is shorter than its header")
    stamp, size, header_size, count = struct.unpack_from("<IIII", block, 0)
    if size != len(block):
        raise NxwrightError("page block says %d bytes but holds %d" % (size, len(block)))
    if header_size != HEADER_SIZE:
        raise NxwrightError("unexpected page header size %d" % header_size)
    name = _decode_padded_name(block[24:24 + _NAME_SIZE])
    if name is None:
        raise NxwrightError("page name field is not a plain NUL-padded name")
    objects = [PageObject(_parse_object_body(body)) for body in _object_bodies(block, count)]
    return PageBlock(name=name, header_size=header_size, unknown_16=block[16:24],
                     unknown_40=block[40:56], objects=objects, stamp=stamp)


def _object_bodies(block: bytes, count: int):
    """Returns the body of each of the `count` objects, as the object table
    places them."""
    table_end = HEADER_SIZE + count * _TABLE_ENTRY_SIZE
    if table_end > len(block):
        raise NxwrightError("object table runs past the end of the page block")
    bodies = []
    for index in range(count):
        offset, length, zero = struct.unpack_from("<III", block, HEADER_SIZE + index * _TABLE_ENTRY_SIZE)
        start = HEADER_SIZE + offset
        if zero != 0 or start + length > len(block):
            raise NxwrightError("object table entry %d is not understood" % index)
        bodies.append(block[start:start + length])
    return bodies


def _parse_object_body(body: bytes) -> list:
    """Returns an object body's records as Attribute, Marker, Event, and
    RawRecord items, in stored order."""
    records = _split_records(body)
    items = []
    position = 0
    while position < len(records):
        record = records[position]
        position += 1
        event = _EVENT_MARKER.fullmatch(record)
        if event:
            line_count = int(event.group(2))
            lines = records[position:position + line_count]
            if len(lines) != line_count:
                raise NxwrightError("event %s announces %d lines but the object ends first"
                                    % (event.group(1).decode(), line_count))
            items.append(Event(event.group(1).decode("ascii"), lines))
            position += line_count
        elif len(record) < _NAME_SIZE:
            items.append(Marker(record))
        else:
            items.append(_parse_attribute(record))
    return items


def _split_records(body: bytes) -> list:
    """Splits an object body into record bodies, checking that it ends exactly at
    the zero-length terminator."""
    records = []
    position = 0
    while True:
        if position + 4 > len(body):
            raise NxwrightError("object ends without its terminating record")
        length = struct.unpack_from("<I", body, position)[0]
        position += 4
        if length == 0:
            break
        if position + length > len(body):
            raise NxwrightError("record runs past the end of its object")
        records.append(body[position:position + length])
        position += length
    if position != len(body):
        raise NxwrightError("object holds data after its terminating record")
    return records


def _parse_attribute(record: bytes):
    """Returns an Attribute, or a RawRecord when the name field does not hold a
    plain attribute name."""
    name = _decode_padded_name(record[:_NAME_SIZE])
    if name is None or not _ATTRIBUTE_NAME.fullmatch(name.encode("ascii")):
        return RawRecord(record)
    return Attribute(name, record[_NAME_SIZE:])


def _decode_padded_name(field_bytes: bytes):
    """Returns the name in a NUL-padded field, or None when the name is not
    printable ASCII without spaces, or the padding is not all NUL, which a
    re-encode would not reproduce."""
    name = field_bytes.split(b"\0")[0]
    if name.ljust(len(field_bytes), b"\0") != field_bytes:
        return None
    if not all(0x20 < byte < 0x7f for byte in name):
        return None
    return name.decode("ascii")


def encode_page(page: PageBlock, embedded: tuple = ()) -> bytes:
    """Encodes `page` back into a page block, deriving size, object count, and
    the object table. The stamp field is written as stored in `page`; it is not
    recomputed.

    `embedded` lists resource blocks to append after the objects, as page files
    do with fonts. Their table entries carry 1 in the third field, where
    objects carry 0.
    """
    bodies = [_encode_object(page_object) for page_object in page.objects] + list(embedded)
    kinds = [0] * len(page.objects) + [_EMBEDDED_RESOURCE] * len(embedded)
    table = bytearray()
    offset = len(bodies) * _TABLE_ENTRY_SIZE
    for body, kind in zip(bodies, kinds):
        table += struct.pack("<III", offset, len(body), kind)
        offset += len(body)
    total = HEADER_SIZE + len(table) + sum(len(body) for body in bodies)
    header = (struct.pack("<IIII", page.stamp, total, page.header_size, len(bodies))
              + page.unknown_16 + page.name.encode("ascii").ljust(_NAME_SIZE, b"\0")
              + page.unknown_40)
    return header + bytes(table) + b"".join(bodies)


def _encode_object(page_object: PageObject) -> bytes:
    out = bytearray()
    for item in page_object.items:
        for record in _item_records(item):
            out += struct.pack("<I", len(record)) + record
    out += struct.pack("<I", 0)
    return bytes(out)


def _item_records(item) -> list:
    if isinstance(item, Attribute):
        return [item.name.encode("ascii").ljust(_NAME_SIZE, b"\0") + item.value]
    if isinstance(item, Marker):
        return [item.text]
    if isinstance(item, Event):
        marker = b"codes%s-%d" % (item.name.encode("ascii"), len(item.lines))
        return [marker] + list(item.lines)
    if isinstance(item, RawRecord):
        return [item.body]
    raise TypeError("not a page record: %r" % (item,))
