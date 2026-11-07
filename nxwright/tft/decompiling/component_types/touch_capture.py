"""Reads a touch capture's attributes back, as the compile's touch capture
module writes them on T, K, and F (component_types/touch_capture.py): its
vscope, from its record, and its val, from its memory. A touch capture is
not drawn and has no place, so it keeps no place, size, aph, sendkey, or
effect.

The Nextion Editor adds a block to its page's load section for it, a
slider's command and its ID (slider.load_block). The decoder checks that
the block is there, and gives it, so that the source folder leaves it out.

On P, a touch capture's values lie where its named entries say, which
objects.p_values reads. Its page's load section holds init and its ID for
it, in place of T's block (objects.p_init_blocks).
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, slider, touch_capture
from nxwright.tft.decompiling import DecodeError, numbers
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, object_memory, p_init_blocks, p_values,
                                       record_head)


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of the touch capture `decoded_object`, of
    `decoded_page`. Raises DecodeError when its page's load section has no
    block for it."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        init = p_init_blocks(decoded_object, decoded_page, decoded_file)
        return ObjectValues(p_values(decoded_object, decoded_page, decoded_file),
                            {"load": (init, 0)})
    (val,) = struct.unpack(touch_capture.MEMORY_FORMAT, object_memory(
        decoded_object, decoded_page, decoded_file,
        struct.calcsize(touch_capture.MEMORY_FORMAT)))
    block = numbers.as_written(slider.load_block(decoded_file.series, decoded_object.object_id),
                               decoded_file.series, decoded_file.version)
    if block not in decoded_page.load_section.blocks:
        raise DecodeError("touch capture %d's page's load section has no block for it"
                          % decoded_object.object_id, decoded_page.load_section.place,
                          b"".join(decoded_page.load_section.blocks))
    return ObjectValues({"vscope": int(record_head(decoded_object).is_global), "val": val},
                        {"load": (1, 0)})
