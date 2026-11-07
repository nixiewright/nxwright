"""Reads a checkbox back, on T, K, and F, as the compile's checkbox module
writes it (component_types/checkbox.py).

A checkbox keeps its values in its memory: its style, its borderw and
borderc, which are 0 but at a style of 1, its bco, pco, and val. Its style
sets its variant: a style of 1 gives two more entries, its borderw's and
its borderc's.

The Nextion Editor starts a checkbox's down event with code of its own,
which switches its val between 0 and 1 (checkbox.val_switch). The decoder
checks those blocks against what the compile writes, and gives them, so
that the source folder leaves them out.

On P, a checkbox's values lie where its named entries say, which
objects.p_values reads, and the Nextion Editor adds no code to its down
event.
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, checkbox, entry_operand
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, object_memory, p_values,
                                       record_head, shared_values)

# The values its memory gives only at a style of 1.
_BORDER_VALUES = ("borderw", "borderc")


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the checkbox's ObjectValues (decompiling/objects.py). Raises
    DecodeError when its entries are not those of the variant of its style,
    or its down event does not start with the code that switches its val."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return ObjectValues(p_values(decoded_object, decoded_page, decoded_file))
    head = record_head(decoded_object)
    attributes = shared_values(decoded_object)
    memory = dict(zip(checkbox.MEMORY_VALUES, struct.unpack(
        checkbox.MEMORY_FORMAT, object_memory(decoded_object, decoded_page, decoded_file,
                                              struct.calcsize(checkbox.MEMORY_FORMAT)))))
    module = described(head.type_number, {"style": memory["style"],
                                          "effect": attributes["effect"]})
    if module.ENTRIES != len(decoded_object.entries):
        raise DecodeError("checkbox %d has %d entries, but a checkbox of style %d has %d"
                          % (decoded_object.object_id, len(decoded_object.entries),
                             memory["style"], module.ENTRIES),
                          head.drawing_place, b"".join(decoded_object.entries))
    attributes.update({name: value for name, value in memory.items()
                       if name not in _BORDER_VALUES or memory["style"] == checkbox.BORDERED})
    return ObjectValues(attributes, switch_added(decoded_object, module, decoded_file))


def switch_added(decoded_object: DecodedObject, module, decoded_file: DecodedFile) -> dict:
    """Returns ObjectValues' added of the code that starts the down event of
    `decoded_object`, which `module` describes (objects.described): the
    blocks that switch its val between 0 and 1 (checkbox.val_switch), as a
    checkbox's, a radio's, and a dual-state button's down events start.
    Raises DecodeError when its down event does not start with them."""
    switch = checkbox.val_switch(
        entry_operand(decoded_object.first_entry + module.attribute_place("val")),
        decoded_file.series)
    down = decoded_object.events["down"]
    if down.blocks[:len(switch)] != switch:
        raise DecodeError("%s %d's down event does not start with the code that switches its "
                          "val" % (decoded_object.type_name, decoded_object.object_id),
                          down.place, b"".join(down.blocks[:len(switch)]))
    return {"down": (len(switch), 0)}
