"""Reads a progress bar back, on T, K, and F, as the compile's progress bar
module writes it (component_types/progress_bar.py).

A progress bar keeps its values in its memory: its sta, dez, val, and dis,
then its empty part's colour or picture, and its filled part's. Its sta
sets which: its bco and pco in colours, or its bpic and ppic in pictures
(progress_bar.PARTS), and so which variant gives its entries. Drawn in
pictures, it keeps no dis, so its dis is not given there.

Its drawing is code of the Nextion Editor's own, which the compile writes
from these values, and no event holds code of the Nextion Editor's own.

On P, a progress bar's values lie where its named entries say, which
objects.p_values reads.
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, progress_bar
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, has_entry, object_memory,
                                       p_values, record_head, shared_values)


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the progress bar's ObjectValues (decompiling/objects.py).
    Raises DecodeError when its sta is not one the compile writes, or its
    entries are not those of the variant of its sta."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return ObjectValues(p_values(decoded_object, decoded_page, decoded_file))
    head = record_head(decoded_object)
    attributes = shared_values(decoded_object)
    memory = dict(zip(progress_bar.MEMORY_VALUES, struct.unpack(
        progress_bar.MEMORY_FORMAT, object_memory(
            decoded_object, decoded_page, decoded_file,
            struct.calcsize(progress_bar.MEMORY_FORMAT)))))
    sta = memory["sta"]
    module = described(head.type_number, {"sta": sta, "effect": attributes["effect"]})
    if sta not in progress_bar.PARTS or module.ENTRIES != len(decoded_object.entries):
        raise DecodeError("progress bar %d has %d entries and a sta of %d, which no progress "
                          "bar the compile writes has" % (decoded_object.object_id,
                                                          len(decoded_object.entries), sta),
                          head.drawing_place, b"".join(decoded_object.entries))
    parts = dict(zip(("empty", "filled"), progress_bar.PARTS[sta]))
    for value, number in memory.items():
        if value in parts:
            attributes[parts[value]] = number
        elif value != "dis" or has_entry(module, "dis"):
            attributes[value] = number
    return ObjectValues(attributes)
