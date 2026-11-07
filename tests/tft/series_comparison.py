"""Compares user code using the independently recorded series differences.

Only instruction tokens, a QR code's maximum text length, and a page's screen
geometry may change. Other bytes, including text and memory padding, must
match.

compare_user_code compares a follower's whole user code with its leader's.
instruction_piece and entries_piece give one piece of a leader's fixtures
as its follower writes it, so that a follower's unit test compares a
type's function on the follower's series with the leader's piece.
"""
from dataclasses import replace
import struct

from nxwright.tft.component_types import object_module
from nxwright.tft.series_differences import DIFFERENCES
from nxwright.tft.tft_file import encode_blocks, split_blocks

# Object records start with a fixed head, then two-byte attribute slots.
# T, K, and F have fixed-size records. P and E have one slot per name in
# the first block's attribute-name table.
_RECORD_HEAD_SIZE = 56
_T_RECORD_SIZE = 232
_RECORD_SLOT_SIZE = 2
_RECORD_VSCOPE_OFFSET = 2
_RECORD_BASE_OFFSET = 28
# w, h, endx, and endy are consecutive signed shorts in the record's head
# and in the page's starting memory on P and E.
_PAGE_GEOMETRY_OFFSET = 44

# An attribute entry gives base, value, maximum, minimum, owner, and code.
_ATTRIBUTE_ENTRY_SIZE = 24
_ATTRIBUTE_MAXIMUM_OFFSET = 8

# The first block starts with a region count and (place, size) pairs.
# Its second region is global memory; P and E add a fourth with name CRCs.
_P_REGION_COUNT = 4
_GLOBAL_MEMORY_OFFSET = 12
_ATTRIBUTE_NAMES_SIZE_OFFSET = 32
_ATTRIBUTE_NAME_SIZE = 4
# A page's starting memory begins with one four-byte place per object.
_MEMORY_PLACE_SIZE = 4


def difference_rows(differences: dict) -> set:
    """Returns the row identifiers that a comparison must exercise."""
    rows = {(kind, row) for kind in ("commands", "operands", "attribute_limits")
            for row in differences[kind]}
    if differences["page_size"] is not None:
        rows.add(("page_size", differences["page_size"]))
    return rows


def _instruction(block: bytes, differences: dict, used: set) -> bytes:
    expected = bytearray(block)
    at = 0
    if block.startswith(b"\x09") and len(block) >= 3:
        for row in differences["commands"]:
            _, table, before, after = row
            if block[1:3] == bytes((before, table)):
                expected[1] = after
                used.add(("commands", row))
                break
        at = 3
    quoted = False
    while at < len(block):
        marker = block[at]
        if quoted:
            if marker == 0x5C:
                at += 2
                continue
            if marker == 0x22:
                quoted = False
        elif marker == 0x22:
            quoted = True
        elif marker in (1, 3, 4, 5):
            if marker == 4:
                for row in differences["operands"]:
                    _, table, before, after = row
                    if block[at:at + 5] == bytes((4, table, before, 0, 0)):
                        expected[at + 2] = after
                        used.add(("operands", row))
                        break
            at += 5
            continue
        at += 1
    return bytes(expected)


def instruction_piece(piece: bytes, differences: dict, used: set) -> bytes:
    """Returns the piece `piece` of a leader's fixtures, its blocks back to
    back with their size words, as its follower writes it: each block's
    instruction tokens as `differences` changes them (the rows exercised
    added to `used`). A block's size does not change, so neither do the
    places of what follows it."""
    blocks = split_blocks(piece)
    if blocks is None:
        raise AssertionError("the piece is not blocks back to back")
    return encode_blocks([_instruction(block, differences, used) for block in blocks])


def entries_piece(piece: bytes, page_object, differences: dict, used: set) -> bytes:
    """Returns the piece `piece`, a leader's component's entries, as its
    follower writes them: each attribute's maximum that `differences`
    changes, as a QR code's txt_maxl's, the row's slot in the component's
    record giving its entry (record_slots). Raises AssertionError when the
    leader's maximum is not the row's."""
    data = bytearray(piece)
    module = object_module(page_object)
    for row in differences["attribute_limits"]:
        type_number, slot, before, after = row
        if page_object.attribute("type")[0] != type_number:
            continue
        at = module.record_slots()[slot] * _ATTRIBUTE_ENTRY_SIZE + _ATTRIBUTE_MAXIMUM_OFFSET
        maximum = struct.unpack_from("<i", data, at)[0]
        if maximum != before:
            raise AssertionError("entries: type %d, slot %d: attribute maximum expected %d, "
                                 "got %d" % (type_number, slot, before, maximum))
        struct.pack_into("<i", data, at, after)
        used.add(("attribute_limits", row))
    return bytes(data)


def _records(code):
    entries = code.index_entries()
    objects = sum(entry.objects for entry in entries)
    size = _T_RECORD_SIZE
    if struct.unpack_from("<I", code.blocks[0])[0] == _P_REGION_COUNT:
        names_size = struct.unpack_from("<I", code.blocks[0], _ATTRIBUTE_NAMES_SIZE_OFFSET)[0]
        size = _RECORD_HEAD_SIZE + names_size // _ATTRIBUTE_NAME_SIZE * _RECORD_SLOT_SIZE
    # The user code ends with up to three alignment bytes, outside the records.
    if not 0 <= len(code.records) - objects * size <= 3:
        raise AssertionError("records: invalid object record sizes")
    return entries, size


def _attribute_limits(code, differences: dict, used: set) -> bytes:
    if not differences["attribute_limits"]:
        return code.data
    data = bytearray(code.data)
    entries, record_size = _records(code)
    data_start = code.places()["data"][0]
    for page in entries:
        for object_id in range(page.objects):
            record_at = (page.objects_before + object_id) * record_size
            record = code.records[record_at:record_at + record_size]
            for row in differences["attribute_limits"]:
                type_number, slot, before, after = row
                if record[0] != type_number:
                    continue
                # The record's slot follows variant entry shifts, including effects.
                entry = struct.unpack_from(
                    "<H", record, _RECORD_HEAD_SIZE + slot * _RECORD_SLOT_SIZE)[0]
                at = (page.data_place - data_start
                      + entry * _ATTRIBUTE_ENTRY_SIZE + _ATTRIBUTE_MAXIMUM_OFFSET)
                maximum = struct.unpack_from("<i", data, at)[0]
                if maximum != before:
                    raise AssertionError(
                        "data: type %d, slot %d: attribute maximum expected %d, got %d" %
                        (type_number, slot, before, maximum))
                struct.pack_into("<i", data, at, after)
                used.add(("attribute_limits", row))
    return bytes(data)


def _page_geometry(code, differences: dict, rotation: int, used: set):
    row = differences["page_size"]
    if row is None:
        return code
    before, after = row
    if rotation in (90, 270):
        before, after = before[::-1], after[::-1]
    old = struct.pack("<4h", *before, before[0] - 1, before[1] - 1)
    new = struct.pack("<4h", *after, after[0] - 1, after[1] - 1)
    blocks = list(code.blocks)
    records = bytearray(code.records)
    entries, record_size = _records(code)
    starts = {place: number for number, place in enumerate(code.block_places())}
    int_start = struct.unpack_from("<I", blocks[0], _GLOBAL_MEMORY_OFFSET)[0]

    def patch(block: bytes, at: int) -> bytes:
        end = at + len(old)
        if block[at:end] != old:
            raise AssertionError("page geometry: leader differs from the recorded screen size")
        return block[:at] + new + block[end:]

    for page in entries:
        record_at = page.objects_before * record_size
        records[record_at:record_at + record_size] = patch(
            records[record_at:record_at + record_size], _PAGE_GEOMETRY_OFFSET)
        record = code.records[record_at:record_at + record_size]
        base = struct.unpack_from("<I", record, _RECORD_BASE_OFFSET)[0]
        if record[_RECORD_VSCOPE_OFFSET]:
            blocks[0] = patch(blocks[0], int_start + base + _PAGE_GEOMETRY_OFFSET)
        else:
            memory = starts[page.table_place] + 1
            blocks[memory] = patch(
                blocks[memory], _MEMORY_PLACE_SIZE * page.objects + _PAGE_GEOMETRY_OFFSET)
        used.add(("page_size", row))
    return replace(code, blocks=blocks, records=bytes(records))


def _equal(expected: bytes, actual: bytes, where: str):
    if expected != actual:
        at = next((n for n, pair in enumerate(zip(expected, actual))
                   if pair[0] != pair[1]), min(len(expected), len(actual)))
        raise AssertionError("%s, byte %d: expected %s, got %s (sizes %d and %d)" %
                             (where, at, expected[at:at + 8].hex(),
                              actual[at:at + 8].hex(), len(expected), len(actual)))


def compare_user_code(leader, follower, series: str, rotation: int = 0,
                      differences: dict = None) -> set:
    """Checks every user-code byte and returns the difference rows exercised.

    Raises AssertionError with the part and block for an unexplained change.
    Optional differences let a regression test remove a row without changing
    the compiler or the shared table.
    """
    differences = DIFFERENCES[series] if differences is None else differences
    used = set()
    expected = _page_geometry(leader, differences, rotation, used)
    expected = replace(expected, data=_attribute_limits(expected, differences, used))
    if len(expected.blocks) != len(follower.blocks):
        raise AssertionError("blocks: expected %d blocks, got %d" %
                             (len(expected.blocks), len(follower.blocks)))
    starts = {place: number for number, place in enumerate(expected.block_places())}
    binary = {0}
    for entry in expected.index_entries():
        table = starts[entry.table_place]
        binary.update((table, table + 1))
    parts = expected.block_parts()
    for number, (block, actual) in enumerate(zip(expected.blocks, follower.blocks)):
        if number not in binary:
            block = _instruction(block, differences, used)
        _equal(block, actual, "%s block %d" % (parts[number], number))
    for field, label in (("after_blocks", "after the blocks"), ("variables", "variables"),
                         ("data", "data"), ("macros", "macros"),
                         ("page_index", "page index"), ("records", "records")):
        _equal(getattr(expected, field), getattr(follower, field), label)
    return used
