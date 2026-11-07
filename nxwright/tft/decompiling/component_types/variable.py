"""Reads a variable's attributes back, as the compile's variable module writes
them on T, K, and F (component_types/variable.py).

A variable is not drawn, so its record's place and size mean nothing. Its
record's head gives its vscope, and its entries give its sta, which tells
whether it holds a number, at 0, or a text, at 1. A variable of a number
keeps its val in its memory, 4 bytes, signed. A variable of a text keeps
its txt_maxl in its entry, and its txt in its memory, after the 4 bytes a
val would take (TXT_PLACE), padded with zeros up to txt_maxl + 1 bytes. The
Nextion Editor adds no code of its own for a variable.

On P, a variable's values lie where its named entries say, which
objects.p_values reads.
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, variable
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, entry_value, object_memory,
                                       p_values, record_head)


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of the variable `decoded_object`, of
    `decoded_page`. Raises DecodeError when its sta is neither 0 nor 1, when
    it has not the entries its sta's variant has, and when its memory does
    not lie where its base gives it."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return ObjectValues(p_values(decoded_object, decoded_page, decoded_file))
    head = record_head(decoded_object)
    # Every variable has its sta at the same entry, whatever it holds.
    sta_entry = described(head.type_number, {}).attribute_place("sta")
    sta = (entry_value(decoded_object, sta_entry) if len(decoded_object.entries) > sta_entry
           else None)
    module = described(head.type_number, {"sta": sta or 0})
    if sta not in (0, 1) or len(decoded_object.entries) != module.ENTRIES:
        raise DecodeError("variable %d has %d entries and the sta %s, but a variable of a "
                          "number, its sta 0, has %d, and one of a text, its sta 1, has %d"
                          % (decoded_object.object_id, len(decoded_object.entries), sta,
                             described(head.type_number, {"sta": 0}).ENTRIES,
                             described(head.type_number, {"sta": 1}).ENTRIES),
                          head.drawing_place, b"".join(decoded_object.entries))
    values = {"vscope": int(head.is_global), "sta": sta}
    # Only a variable of a text gives where its txt lies in its memory.
    if not hasattr(module, "TXT_PLACE"):
        (values["val"],) = struct.unpack(variable.MEMORY_FORMAT, object_memory(
            decoded_object, decoded_page, decoded_file, struct.calcsize(variable.MEMORY_FORMAT)))
        return ObjectValues(values)
    maxl = entry_value(decoded_object, module.attribute_place("txt_maxl"))
    memory = object_memory(decoded_object, decoded_page, decoded_file,
                           module.TXT_PLACE + maxl + 1)
    values.update({"txt": memory[module.TXT_PLACE:].split(b"\x00", 1)[0], "txt_maxl": maxl})
    return ObjectValues(values)
