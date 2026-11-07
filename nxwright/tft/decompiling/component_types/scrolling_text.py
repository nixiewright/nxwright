"""Reads a scrolling text back, on T, K, and F, as the compile's scrolling
text module writes it (component_types/scrolling_text.py).

A scrolling text keeps its values in its memory: its sta and style, its
border, font, what lies behind it, pco, xcen, ycen, dir, dis, tim, en,
txt_maxl, where its txt lies, isbr, spax, spay, and vvs0 to vvs3. Its txt
lies after its page's components' memory, or in the int area for a global
one. Its variant, by its sta and its style, sets which entries it has, as a
text's does (objects.kept_style).

The Nextion Editor writes code of its own for a scrolling text in its
page's load section: code that sets where the scrolling starts, an "L "
block past the rest, then its timer's code between two "S " blocks
(scrolling_text's load_blocks). The decoder writes that code again with the
compile, from the scrolling text's attributes and the number of the first
"S " block, finds it in the load section, and gives it, so that the source
folder leaves it out. A key's lines at the end of its Touch Release event
are read back as a text's are (objects.key_values).

On P, a scrolling text's values lie where its named entries say, which
objects.p_values reads. Behind anything but a colour, its style has no
entry, and a bordered style is known by its border's entries alone
(objects.p_kept_style). Its key is read as on T. Its page's load section
holds init and its ID for it, in place of T's code (objects.p_init_blocks).
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, VALUE_TAG, ObjectPlace, scrolling_text
from nxwright.tft.component_types.timer import TIMER_EVENT_START
from nxwright.tft.decompiling import DecodeError, numbers
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, candidate_object, described, has_entry,
                                       kept_style, memory_at, object_memory, p_init_blocks,
                                       p_kept_style, p_values, record_head, shared_values,
                                       with_key)

# What may lie behind a scrolling text, by the attribute that gives it.
_BEHIND = ("picc", "bco", "pic")
# The values its memory gives that its variant reads, its border's, and
# where its txt lies, which is no attribute.
_VARIANT_VALUES = ("sta", "style")
_BORDER_VALUES = ("borderc", "borderw")
_TXT_PLACE = "txt_place"
# An "S " block: its start, then 03 and its number, 4 bytes.
_S_BLOCK_SIZE = len(TIMER_EVENT_START) + 5


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the scrolling text's ObjectValues (decompiling/objects.py).
    Raises DecodeError when its entries are not those of the variant its
    memory gives, or its page's load section does not hold its code.
    On P, raises DecodeError when its page's load section lacks its init
    block."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        values = with_key(p_kept_style(p_values(decoded_object, decoded_page, decoded_file),
                                       scrolling_text.BORDERED), decoded_object,
                          decoded_page, decoded_file)
        values.added["load"] = (p_init_blocks(decoded_object, decoded_page, decoded_file), 0)
        return values
    head = record_head(decoded_object)
    attributes = shared_values(decoded_object)
    effect = attributes["effect"]

    def variant(sta: int, style: int):
        return described(head.type_number, {"sta": sta, "style": style, "effect": effect})

    memory = dict(zip(scrolling_text.MEMORY_VALUES, struct.unpack(
        scrolling_text.MEMORY_FORMAT, object_memory(
            decoded_object, decoded_page, decoded_file,
            struct.calcsize(scrolling_text.MEMORY_FORMAT)))))
    sta = memory["sta"]
    style = kept_style(decoded_object, variant, sta, memory["style"], scrolling_text)
    module = variant(sta, style or 0)
    if module.ENTRIES != len(decoded_object.entries):
        raise DecodeError("scrolling text %d has %d entries, but one of sta %d and style %d "
                          "has %d" % (decoded_object.object_id, len(decoded_object.entries), sta,
                                      style or 0, module.ENTRIES),
                          head.drawing_place, b"".join(decoded_object.entries))
    attributes["sta"] = sta
    if style is not None:
        attributes["style"] = style
    behind = [name for name in _BEHIND if has_entry(module, name)]
    for name, value in memory.items():
        if name == "background":
            if behind:
                attributes[behind[0]] = value
        elif name in _BORDER_VALUES:
            if style == scrolling_text.BORDERED:
                attributes[name] = value
        elif name not in _VARIANT_VALUES + (_TXT_PLACE,):
            attributes[name] = value
    attributes["txt"] = memory_at(decoded_object, decoded_page, decoded_file,
                                  memory[_TXT_PLACE],
                                  attributes["txt_maxl"] + 1).split(b"\x00", 1)[0]
    values = with_key(attributes, decoded_object, decoded_page, decoded_file)
    values.added["load"] = (_load_blocks(decoded_object, decoded_page, decoded_file, module,
                                         attributes), 0)
    return values


def _load_blocks(decoded_object: DecodedObject, decoded_page: DecodedPage,
                 decoded_file: DecodedFile, module, attributes: dict) -> int:
    """Returns how many blocks of its page's load section the scrolling text
    `decoded_object`, which `module` describes, with `attributes`, added:
    the code the compile writes for it there (load_blocks), at a place of
    the section where it lies whole, with the first "S " number the
    section's blocks give. Raises DecodeError when none does."""
    section = decoded_page.load_section
    places = section.block_places()
    candidate = candidate_object(decoded_object.type_number, attributes)

    def written(load_place: int, first: int) -> list:
        place = ObjectPlace(decoded_page.page_id, decoded_object.object_id,
                            decoded_object.first_entry, decoded_page.objects[0].first_entry,
                            decoded_object.base, load_place=load_place)
        return [numbers.as_written(block, decoded_file.series, decoded_file.version)
                for block in module.load_blocks(candidate, decoded_file.series, place, first)]

    def same(expected: list, found: list) -> bool:
        # An older file numbers its "S " blocks its own way, so they match
        # by their form alone (numbers.counts_labels).
        if numbers.counts_labels(decoded_file.version):
            return found == expected
        return len(found) == len(expected) and all(
            mine == theirs or _is_s_block(mine) and _is_s_block(theirs)
            for mine, theirs in zip(expected, found))

    # Its timer code starts with an "S " block one past its first number.
    firsts = [int.from_bytes(block[-4:], "little", signed=True) - 1
              for block in section.blocks if _is_s_block(block)]
    for first in firsts:
        opening = written(0, first)[:1]
        for at, place in enumerate(places):
            if not same(opening, section.blocks[at:at + 1]):
                continue
            expected = written(place, first)
            if same(expected, section.blocks[at:at + len(expected)]):
                return len(expected)
    raise DecodeError("scrolling text %d's code is not in its page's load section"
                      % decoded_object.object_id, section.place, b"".join(section.blocks))


def _is_s_block(block: bytes) -> bool:
    """Returns whether `block` is an "S " block that starts a timer's code,
    whatever its number."""
    return (len(block) == _S_BLOCK_SIZE and block.startswith(TIMER_EVENT_START)
            and block[len(TIMER_EVENT_START)] == VALUE_TAG)
