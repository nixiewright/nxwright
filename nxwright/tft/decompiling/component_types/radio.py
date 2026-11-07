"""Reads a radio back, on T, K, and F, as the compile's radio module writes
it (component_types/radio.py): what every drawn component keeps alike
(objects.shared_values), and its bco, pco, and val, from its memory.

The Nextion Editor starts a radio's down event with a checkbox's code,
which switches its val between 0 and 1. The decoder checks it, and gives
it, as a checkbox's (checkbox.switch_added).

On P, a radio's values lie where its named entries say, which
objects.p_values reads, and the Nextion Editor adds no code to its down
event.
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, radio
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.component_types.checkbox import switch_added
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, object_memory, p_values,
                                       record_head, shared_values)


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the radio's ObjectValues (decompiling/objects.py). Raises
    DecodeError when its entries are not a radio's, or its down event does
    not start with the code that switches its val."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return ObjectValues(p_values(decoded_object, decoded_page, decoded_file))
    head = record_head(decoded_object)
    attributes = shared_values(decoded_object)
    module = described(head.type_number, {"effect": attributes["effect"]})
    if module.ENTRIES != len(decoded_object.entries):
        raise DecodeError("radio %d has %d entries, but a radio has %d"
                          % (decoded_object.object_id, len(decoded_object.entries),
                             module.ENTRIES),
                          head.drawing_place, b"".join(decoded_object.entries))
    attributes.update(zip(radio.MEMORY_VALUES, struct.unpack(radio.MEMORY_FORMAT, object_memory(
        decoded_object, decoded_page, decoded_file, struct.calcsize(radio.MEMORY_FORMAT)))))
    return ObjectValues(attributes, switch_added(decoded_object, module, decoded_file))
