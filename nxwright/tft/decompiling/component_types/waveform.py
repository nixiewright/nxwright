"""Reads a waveform's attributes back, as the compile's waveform module
writes them on T, K, and F (component_types/waveform.py): what every drawn
component keeps in its record and its entries (objects.shared_values), and
every other value from its memory, read through the compile's
waveform.MEMORY_VALUES and MEMORY_FORMAT. Its ch and its sta pick its
variant, which gives what lies behind it. Its grid's three values are kept
behind a colour alone, and a colour for each of the channels it has alone,
so neither is given otherwise. The size of its buffer and where its buffer
lies are the compile's, from its ch and its width, and are not attributes.

The screen draws a waveform from the block the Nextion Editor adds to its
page's load section, a slider's command and its ID (slider.load_block).
The decoder checks that the block is there, and gives it, so that the
source folder leaves it out.

On P, a waveform's values lie where its named entries say, which
objects.p_values reads. Its objWid, objHig, and inittrue have no entry, so
they are read from its memory, which keeps its values from
waveform.P_VALUES_AT as on T. Its page's load section holds init and its ID
for it, in place of T's block (objects.p_init_blocks).
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, slider, waveform
from nxwright.tft.decompiling import DecodeError, numbers
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, has_entry, memory_at,
                                       object_memory, p_init_blocks, p_values, record_head,
                                       shared_values)

# The values of its memory that are not attributes.
_BUFFER = ("buffer size", "buffer place")


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of the waveform `decoded_object`, of
    `decoded_page`. Raises DecodeError for a sta that T, K, and F do not
    take, such as 3, nothing behind it, and a ch that no waveform has, for
    entries that are not those of the variant they give, and when its
    page's load section has no block drawing it.
    On P, raises DecodeError when its page's load section lacks its init
    block."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        attributes = p_values(decoded_object, decoded_page, decoded_file)
        memory = dict(zip(waveform.MEMORY_VALUES, struct.unpack(waveform.MEMORY_FORMAT, memory_at(
            decoded_object, decoded_page, decoded_file,
            decoded_object.base + waveform.P_VALUES_AT, struct.calcsize(waveform.MEMORY_FORMAT)))))
        attributes.update({name: memory[name] for name in waveform.P_UNNAMED_PLACES})
        init = p_init_blocks(decoded_object, decoded_page, decoded_file)
        return ObjectValues(attributes, {"load": (init, 0)})
    head = record_head(decoded_object)
    attributes = shared_values(decoded_object)
    memory = dict(zip(waveform.MEMORY_VALUES, struct.unpack(
        waveform.MEMORY_FORMAT, object_memory(decoded_object, decoded_page, decoded_file,
                                              struct.calcsize(waveform.MEMORY_FORMAT)))))
    sta, ch = memory["sta"], memory["ch"]
    if sta not in waveform.BACKGROUND or not 1 <= ch <= waveform.MOST_CHANNELS:
        raise DecodeError("waveform %d has a sta of %d and a ch of %d, which no waveform on T, "
                          "K, and F has" % (decoded_object.object_id, sta, ch),
                          head.drawing_place, decoded_object.record)
    module = described(head.type_number, {"sta": sta, "ch": ch, "effect": attributes["effect"]})
    if module.ENTRIES != len(decoded_object.entries):
        raise DecodeError("waveform %d has %d entries, but a waveform of sta %d and ch %d has %d"
                          % (decoded_object.object_id, len(decoded_object.entries), sta, ch,
                             module.ENTRIES),
                          head.drawing_place, b"".join(decoded_object.entries))
    # Its grid is kept where its variant has entries of it, behind a colour.
    unkept = set(_BUFFER) | {"pco%d" % number for number in range(ch, waveform.MOST_CHANNELS)}
    unkept |= {name for name in waveform.GRID if not has_entry(module, name)}
    attributes.update({module.background if name == "background" else name: value
                       for name, value in memory.items() if name not in unkept})
    block = numbers.as_written(slider.load_block(decoded_file.series, decoded_object.object_id),
                               decoded_file.series, decoded_file.version)
    if block not in decoded_page.load_section.blocks:
        raise DecodeError("waveform %d's page's load section has no block drawing it"
                          % decoded_object.object_id, decoded_page.load_section.place,
                          b"".join(decoded_page.load_section.blocks))
    return ObjectValues(attributes, {"load": (1, 0)})
