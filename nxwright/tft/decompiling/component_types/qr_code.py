"""Reads a QR code back, on T, K, and F, as the compile's QR code module
writes it (component_types/qr_code.py).

A QR code keeps its sta, dis, bco, pco, pic, and txt_maxl in its memory,
then where its txt lies: after its page's components' memory, or in the
int area for a global one. Its sta sets its variant: at a sta of 1 a logo,
its pic, shows in the code's middle, and it has an entry of its pic. Its
memory keeps 0 for its pic without a logo, so its pic is given at a sta of
1 alone. The Nextion Editor adds no code of its own for a QR code.

On P, a QR code's values lie where its named entries say, which
objects.p_values reads.
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, qr_code
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, has_entry, memory_at,
                                       object_memory, p_values, record_head, shared_values)


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the QR code's ObjectValues (decompiling/objects.py). Raises
    DecodeError when its entries are not those of the variant of its sta,
    or its memory or its txt does not lie where its places give."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return ObjectValues(p_values(decoded_object, decoded_page, decoded_file))
    head = record_head(decoded_object)
    attributes = shared_values(decoded_object)
    memory = dict(zip(qr_code.MEMORY_VALUES, struct.unpack(
        qr_code.MEMORY_FORMAT, object_memory(decoded_object, decoded_page, decoded_file,
                                             struct.calcsize(qr_code.MEMORY_FORMAT)))))
    module = described(head.type_number, {"sta": memory["sta"],
                                          "effect": attributes["effect"]})
    if module.ENTRIES != len(decoded_object.entries):
        raise DecodeError("QR code %d has %d entries, but a QR code of sta %d has %d"
                          % (decoded_object.object_id, len(decoded_object.entries),
                             memory["sta"], module.ENTRIES),
                          head.drawing_place, b"".join(decoded_object.entries))
    place = memory.pop("txt_place")
    if not has_entry(module, "pic"):
        del memory["pic"]
    attributes.update(memory)
    txt = memory_at(decoded_object, decoded_page, decoded_file, place, memory["txt_maxl"] + 1)
    attributes["txt"] = txt.split(b"\x00", 1)[0]
    return ObjectValues(attributes)
