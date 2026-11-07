"""Reads a slider's attributes back, as the compile's slider module writes
them on T, K, and F (component_types/slider.py): what every drawn
component keeps in its record and its entries (objects.shared_values), and
every other value from its memory, read through the compile's
slider.MEMORY_VALUES and MEMORY_FORMAT. Its sta and psta pick its variant,
which names the attributes that give what lies behind its track, by its
sta, and its cursor, by its psta. Behind a picture or a crop, its memory
keeps zeros for its dis and ch, so neither is given there.

The screen draws a slider from the block the Nextion Editor adds to its
page's load section, its command and its ID (slider.load_block). The
decoder checks that the block is there, and gives it, so that the source
folder leaves it out.

On P, a slider's values lie where its named entries say, which
objects.p_values reads. Its page's load section holds init and its ID for
it, in place of T's block (objects.p_init_blocks).
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, slider
from nxwright.tft.decompiling import DecodeError, numbers
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, object_memory, p_init_blocks,
                                       p_values, record_head, shared_values)

# The values a slider keeps behind a colour alone.
_COLOURED = ("dis", "ch")


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of the slider `decoded_object`, of
    `decoded_page`. Raises DecodeError for a sta or a psta that T, K, and F
    do not take, for entries that are not those of the variant they give,
    and when its page's load section has no block drawing it.
    On P, raises DecodeError when its page's load section lacks its init
    block."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        init = p_init_blocks(decoded_object, decoded_page, decoded_file)
        return ObjectValues(p_values(decoded_object, decoded_page, decoded_file),
                            {"load": (init, 0)})
    head = record_head(decoded_object)
    attributes = shared_values(decoded_object)
    memory = dict(zip(slider.MEMORY_VALUES, struct.unpack(slider.MEMORY_FORMAT, object_memory(
        decoded_object, decoded_page, decoded_file, struct.calcsize(slider.MEMORY_FORMAT)))))
    sta, psta = memory["sta"], memory["psta"]
    if sta not in slider.TRACKS or psta not in slider.CURSORS or psta == slider.SQUARE:
        raise DecodeError("slider %d has a sta of %d and a psta of %d, which no slider on T, "
                          "K, and F has" % (decoded_object.object_id, sta, psta),
                          head.drawing_place, decoded_object.record)
    module = described(head.type_number, {"sta": sta, "psta": psta,
                                          "effect": attributes["effect"]})
    if module.ENTRIES != len(decoded_object.entries):
        raise DecodeError("slider %d has %d entries, but a slider of sta %d and psta %d has %d"
                          % (decoded_object.object_id, len(decoded_object.entries), sta, psta,
                             module.ENTRIES),
                          head.drawing_place, b"".join(decoded_object.entries))
    attributes.update({module.names[name]: value for name, value in memory.items()
                       if module.coloured or name not in _COLOURED})
    block = numbers.as_written(slider.load_block(decoded_file.series, decoded_object.object_id),
                               decoded_file.series, decoded_file.version)
    if block not in decoded_page.load_section.blocks:
        raise DecodeError("slider %d's page's load section has no block drawing it"
                          % decoded_object.object_id, decoded_page.load_section.place,
                          b"".join(decoded_page.load_section.blocks))
    return ObjectValues(attributes, {"load": (1, 0)})
