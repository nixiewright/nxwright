"""Reads a crop's attributes back, as the compile's crop module writes them
on T, K, and F (component_types/crop.py): what every drawn component keeps
in its record and its entries (objects.shared_values); its picc, the
project's picture it shows a part of or 65535 for none, from its memory;
and its vvs0 and vvs1, where its part of that picture starts, from their
entries. An effect gives a crop two more entries before its own, which
moves theirs two on, so their places come from the compile's description
of a crop with its effect (objects.described). The screen reads a vvs as 2
bytes, signed, and the compile writes its entry so, as 40000 is -25536.
The page file keeps those 2 bytes unsigned, as 40000, which is how each
comes back.
The Nextion Editor adds no code of its own for a crop.

On P, a crop's values lie where its named entries say, which
objects.p_values reads.
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, crop
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, entry_value, object_memory,
                                       p_values, record_head, shared_values)

# The page file keeps a vvs in 2 bytes, unsigned.
_VVS_BYTES = 0xFFFF


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of the crop `decoded_object`, of
    `decoded_page`. Raises DecodeError when its memory does not lie where
    its base gives it."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return ObjectValues(p_values(decoded_object, decoded_page, decoded_file))
    shared = shared_values(decoded_object)
    module = described(record_head(decoded_object).type_number, {"effect": shared["effect"]})
    (picc,) = struct.unpack(crop.MEMORY_FORMAT, object_memory(
        decoded_object, decoded_page, decoded_file, struct.calcsize(crop.MEMORY_FORMAT)))
    starts = {name: entry_value(decoded_object, module.attribute_place(name)) & _VVS_BYTES
              for name in ("vvs0", "vvs1")}
    return ObjectValues({**shared, "picc": picc, **starts})
