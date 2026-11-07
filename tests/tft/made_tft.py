"""TFT files the tests make themselves, laid out as the Nextion Editor lays
them out (tft/tft_file.py), with made-up bytes in place of the firmware.
They hold no vendor file.

made_tft writes every checksum, size, and place the reader checks, so a
test can change one thing and see the reader name it.
"""
import struct

from nxwright.tft.packaging import Firmware
from nxwright.tft.tft_file import (HEADER_1_SIZE, HEADER_2_END, PAGE_INDEX_ENTRY_SIZE, SERIES,
                            TABLE_ROWS, TABLE_SIZE, UserCode, byte_form_crc, encode_blocks,
                            encode_f_header_2, file_checksum, firmware_names, header_2_key,
                            series_crc)

DEVICE_IDS = {"T": bytes.fromhex("18c03bb2"), "K": bytes.fromhex("be24d31b"),
              "P": bytes.fromhex("883d9555"), "E": bytes.fromhex("65afb221"),
              "F": bytes.fromhex("0376e41c")}
_SERIES_CODES = {letter: code for code, letter in SERIES.items()}
_FIRMWARE_ROWS = {"T": 6, "K": 6, "F": 6, "P": 2, "E": 2}


def page_blocks(page_id: int) -> list:
    """Returns a blank page's blocks, shaped as the Nextion Editor's: its
    drawing, its events, its objects' table, a block of values, a command,
    and the 0 word that ends them. The bytes are made up, but for the event
    names."""
    return [b"\x09\x0d\x04fill-%d" % page_id, b"", b"", b"down", b"", b"up", b"",
            b"unload", b"", b"table-%d" % page_id, b"values", b"\x09\x21\x08", b""]


def made_user_code(pages: int = 1, variables: int = 3, first_blocks: list = None,
                   index_entry: int = PAGE_INDEX_ENTRY_SIZE) -> UserCode:
    """Returns user code with `pages` blank pages and `variables` int
    variables, its page index giving each page's objects' table and data.
    It starts with `first_blocks`, one made-up block unless given, as the
    Nextion Editor 1.68.2 writes one; an older one writes several. Each
    entry of its page index takes `index_entry` bytes: 12 drops the page's
    memory, as the Nextion Editors before 1.63 do."""
    blocks = list(first_blocks or [b"first block"]) + [b"baud=9600", b"page 0", b""]
    tables, at = [], len(encode_blocks(blocks))
    for page in range(pages):
        page_part = page_blocks(page)
        tables.append(at + len(encode_blocks(page_part[:9])))
        at += len(encode_blocks(page_part))
        blocks += page_part
    variable_bytes = b"".join(struct.pack("<III", 0x1000 + n, 4 * n, 9) for n in range(variables))
    data_start = at + len(variable_bytes)
    data = b"".join(bytes([page]) * 24 for page in range(pages))
    index = b"".join(struct.pack("<HHIII", page, 1, tables[page], data_start + 24 * page,
                                 12)[:index_entry] for page in range(pages))
    return UserCode(blocks, b"", variable_bytes, data, index, b"records",
                    index_entry_size=index_entry)


def made_tft(series: str = "T", user_code: UserCode = None, pictures: bytes = b"",
             fonts: bytes = b"a font", version: tuple = (1, 68, 2), macros_unset: bool = False,
             first_blocks: int = 1, second_firmware: bool = True) -> bytes:
    """Returns a TFT file of `series` holding `user_code`, `pictures`, and
    `fonts`, and made-up firmware files, written by the Nextion Editor whose
    version header 1 gives as `version`. Each of these writes the file as an
    older Nextion Editor does (ResearchNotes/tft/older-editors.md):

    - `macros_unset`: with no macros, header 1 gives the macros' table's
      place as 0xffffffff and their number as 0xffff;
    - `first_blocks`: header 2's 0xFC gives the size of that many first
      blocks, with their size words;
    - not `second_firmware`: on P or E, the file holds no second firmware
      file, whose row of the section's table is then empty."""
    user_code = made_user_code() if user_code is None else user_code
    section_size = 0x20000 if series in ("P", "E") else 0x10000
    device_id = DEVICE_IDS[series]
    # Firmware files of made-up bytes, the main one (row 1) holding the two
    # values header 1 copies from its offsets 1 and 5.
    files = [b"input" * 3] + [b"\x00" + struct.pack("<II", 0x46, 0xD34C) + b"main"]
    files += [b"file %d" % row for row in range(2, _FIRMWARE_ROWS[series] + 1)]
    rows, at = [], TABLE_SIZE
    for row, part in enumerate(files):
        if row == 2 and not second_firmware:
            rows.append((0, 0))
            continue
        rows.append((at, len(part)))
        at += len(part)
    if not second_firmware:
        files = files[:2] + files[3:]
    rows += [(0, 0)] * (6 - _FIRMWARE_ROWS[series])
    for part in (pictures, fonts):
        rows.append((at, len(part)))
        at += len(part)
    rows += [(at, 0) if series in ("P", "E") else (0, 0)] * 3
    table = b"".join(struct.pack("<III", place, size, 0) for place, size in rows)
    section = table + b"".join(files) + pictures + fonts
    section += bytes(-len(section) % section_size)
    user_place = section_size + len(section)
    code = user_code.to_bytes()
    file_size = user_place + len(code) + 4

    header_1 = bytearray(b"\xff" * HEADER_1_SIZE)
    header_1[:0x4C] = bytes(0x4C)
    header_1[0x01:0x04] = bytes(version[:2]) + b"N"
    header_1[0x14:0x18] = bytes([0, _SERIES_CODES[series], 0, version[2]])
    header_1[0x2E:0x32] = device_id
    main_place, second = section_size + rows[1][0], rows[2]
    values = {0x18: section_size + second[0] if second_firmware else 0, 0x22: second[1],
              0x34: section_size,
              0x38: 0x0C, 0x3C: file_size, 0x40: len(section)}
    if series not in ("P", "E"):
        values.update({0x04: main_place + 0x46, 0x08: 0xD34C, 0x1E: section_size + second[0],
                       0x26: main_place, 0x2A: rows[1][1]})
    for place, value in values.items():
        struct.pack_into("<I", header_1, place, value)
    header_1[0x32:0x34] = b"\x21\x00"
    # Zeros from 0x54 to 0x6F, but for the page index's place at 0x58.
    header_1[0x54:0x70] = bytes(0x1C)
    if macros_unset:
        struct.pack_into("<I", header_1, 0x58, 0xFFFFFFFF)
        struct.pack_into("<H", header_1, 0x6E, 0xFFFF)
    else:
        struct.pack_into("<I", header_1, 0x58, user_code.places()["page index"][0])
    struct.pack_into("<I", header_1, 0x44, series_crc(section, series))
    struct.pack_into("<I", header_1, 0xC4, byte_form_crc(bytes(header_1[:0xC4])))

    places = user_code.places()
    pages = len(user_code.index_entries())
    words = [places["after the blocks"][0], places["variables"][0],
             len(user_code.variables) // 12, places["variables"][1], section_size, user_place,
             user_place + places["page index"][0], user_place + places["page index"][1],
             section_size + rows[7][0]]
    words += ([section_size + rows[row][0] for row in (9, 10, 11)] if series in ("P", "E")
              else [0, 0, 0])
    words += [section_size + rows[8][0], len(encode_blocks(user_code.blocks[:first_blocks])),
              pages | (pages << 16),
              1 if pictures else 0, 0, 1, 3]
    if series == "F":
        # F scrambles every word, those past the counts too, which hold
        # 0xFFFFFFFF before they are scrambled.
        words += [0xFFFFFFFF] * (49 - len(words))
        header_2 = b"".join(struct.pack("<I", word)
                            for word in encode_f_header_2(device_id, words))
    else:
        # The key covers the words with values; the rest hold 0xFFFFFFFF as
        # they are stored.
        key = header_2_key(device_id, series)
        header_2 = b"".join(struct.pack("<I", word ^ key) for word in words)
        header_2 += b"\xff" * 4 * (49 - len(words))
    header_2 += struct.pack("<I", byte_form_crc(header_2))
    body = bytes(header_1) + header_2 + b"\xff" * (section_size - HEADER_2_END) + section + code
    return body + struct.pack("<I", file_checksum(body, device_id, series))


def zeros_of_the_table(table: bytes, series: str) -> Firmware:
    """Returns zeros for the firmware, of the sizes the section's table
    `table` gives, row by row, as a probe's fixtures keep it."""
    sizes = [struct.unpack_from("<III", table, 12 * row)[1] for row in range(TABLE_ROWS)]
    return Firmware((1, 68, 2), {name: bytes(size)
                                 for name, size in zip(firmware_names(series), sizes)})
