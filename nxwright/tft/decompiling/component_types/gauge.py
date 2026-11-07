"""Reads a gauge's attributes back, as the compile's gauge module writes
them on T, K, and F (component_types/gauge.py): what every drawn component
keeps in its record and its entries (objects.shared_values), and every
other value from its memory, read through the compile's gauge.MEMORY_VALUES
and MEMORY_FORMAT. Its sta picks its variant, which gives what lies behind
it: a crop of a picture, its picc, a colour, its bco, or a picture, its
pic. Its drawing is the compile's, from these values, and the Nextion
Editor adds no code of its own for a gauge.

On P, a gauge's values lie where its named entries say, which
objects.p_values reads. Its wid has no entry, so it is read from its memory,
which keeps its values from gauge.P_VALUES_AT as on T.
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, gauge
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, memory_at, object_memory,
                                       p_values, record_head, shared_values)


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of the gauge `decoded_object`, of
    `decoded_page`. Raises DecodeError for a sta that T, K, and F do not
    take, such as 3, nothing behind it, and for entries that are not those
    of the variant its sta gives."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        attributes = p_values(decoded_object, decoded_page, decoded_file)
        memory = dict(zip(gauge.MEMORY_VALUES, struct.unpack(gauge.MEMORY_FORMAT, memory_at(
            decoded_object, decoded_page, decoded_file, decoded_object.base + gauge.P_VALUES_AT,
            struct.calcsize(gauge.MEMORY_FORMAT)))))
        return ObjectValues({**attributes, "wid": memory["wid"]})
    head = record_head(decoded_object)
    attributes = shared_values(decoded_object)
    memory = dict(zip(gauge.MEMORY_VALUES, struct.unpack(gauge.MEMORY_FORMAT, object_memory(
        decoded_object, decoded_page, decoded_file, struct.calcsize(gauge.MEMORY_FORMAT)))))
    # A sta the compile does not take on T, K, and F has no variant here,
    # so it is refused before one is asked for.
    if memory["sta"] not in gauge.BACKGROUNDS:
        raise DecodeError("gauge %d has a sta of %d, but a gauge on T, K, and F has one of %s"
                          % (decoded_object.object_id, memory["sta"],
                             ", ".join(map(str, sorted(gauge.BACKGROUNDS)))),
                          head.drawing_place, decoded_object.record)
    module = described(head.type_number, {"sta": memory["sta"], "effect": attributes["effect"]})
    if module.ENTRIES != len(decoded_object.entries):
        raise DecodeError("gauge %d has %d entries, but a gauge of sta %d has %d"
                          % (decoded_object.object_id, len(decoded_object.entries),
                             memory["sta"], module.ENTRIES),
                          head.drawing_place, b"".join(decoded_object.entries))
    attributes.update({module.background if name == "background" else name: value
                       for name, value in memory.items()})
    return ObjectValues(attributes)
