"""Reads a timer's attributes back, as the compile's timer module writes
them on T, K, and F (component_types/timer.py): its vscope, from its
record, and its tim and en, from its memory. A timer is not drawn, so it
keeps no place, size, aph, sendkey, or effect.

The Nextion Editor writes code of its own for each timer, which the source
folder leaves out:

  - the "S " block that starts its timer event;
  - in its page's load section, the command timerset and the "L " block,
    which give its en's and its tim's entries, its ID, and where its timer
    event's code starts, after that "S " block.

The decoder finds that pair of blocks by the "L " block's place, and checks
both against what the compile's timer module writes for the timer.

On P, a timer's values lie where its named entries say, which
objects.p_values reads. Its timer event starts with no "S " block, and its
page's load section holds init and its ID for it, in place of timerset and
the "L " block (objects.p_init_blocks).
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, VALUE_TAG, ObjectPlace, timer
from nxwright.tft.decompiling import DecodeError, numbers
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, object_memory, p_init_blocks, p_values,
                                       record_head)
from nxwright.tft.label_numbers import S_BLOCK_START

# The size of the "S " block that starts a timer's timer event: its start,
# then 03 and a number of 4 bytes; and a block's size word.
_S_BLOCK_SIZE = len(S_BLOCK_START) + 5
_SIZE_WORD = 4


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of the timer `decoded_object`, of
    `decoded_page`. Raises DecodeError when its timer event does not start
    with an "S " block, or when its page's load section has no timerset and
    "L " block written for it.
    On P, raises DecodeError when its page's load section lacks its init
    block."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        init = p_init_blocks(decoded_object, decoded_page, decoded_file)
        return ObjectValues(p_values(decoded_object, decoded_page, decoded_file),
                            {"load": (init, 0)})
    code = _code_place(decoded_object)
    head = record_head(decoded_object)
    tim, en = struct.unpack(timer.MEMORY_FORMAT, object_memory(
        decoded_object, decoded_page, decoded_file, struct.calcsize(timer.MEMORY_FORMAT)))
    place = ObjectPlace(decoded_page.page_id, decoded_object.object_id,
                        decoded_object.first_entry, decoded_page.objects[0].first_entry,
                        decoded_object.base)
    expected = [numbers.as_written(block, decoded_file.series, decoded_file.version)
                for block in timer.load_blocks(decoded_file.series, place, code)]
    section = decoded_page.load_section.blocks
    if not any(section[at:at + len(expected)] == expected for at in range(len(section))):
        raise DecodeError("timer %d's timerset and \"L \" block are not in its page's load "
                          "section" % decoded_object.object_id,
                          decoded_page.load_section.place, b"".join(section))
    return ObjectValues({"vscope": int(head.is_global), "tim": tim, "en": en},
                        {"timer": (1, 0), "load": (len(expected), 0)})


def _code_place(decoded_object: DecodedObject) -> int:
    """Returns where the code of the timer `decoded_object`'s timer event
    starts in the user code, after the "S " block that starts the event.
    Raises DecodeError when the event does not start with that block."""
    run = decoded_object.events["timer"]
    if not run.blocks or not (len(run.blocks[0]) == _S_BLOCK_SIZE
                              and run.blocks[0].startswith(S_BLOCK_START)
                              and run.blocks[0][len(S_BLOCK_START)] == VALUE_TAG):
        raise DecodeError("timer %d's timer event does not start with its \"S \" block"
                          % decoded_object.object_id, run.place,
                          run.blocks[0] if run.blocks else b"")
    return run.place + _SIZE_WORD + _S_BLOCK_SIZE
