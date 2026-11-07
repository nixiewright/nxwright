"""Reads a picture's attributes back, as the compile's picture module writes
them on T, K, and F (component_types/picture.py): what every drawn
component keeps in its record and its entries (objects.shared_values), and
its pic, the project's picture it shows or 65535 for none, from its
memory. The Nextion Editor adds no code of its own for a picture.

On P, a picture's values lie where its named entries say, which
objects.p_values reads.
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, picture
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import ObjectValues, object_memory, p_values, shared_values


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of the picture `decoded_object`, of
    `decoded_page`. Raises DecodeError when its memory does not lie where
    its base gives it."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return ObjectValues(p_values(decoded_object, decoded_page, decoded_file))
    (pic,) = struct.unpack(picture.MEMORY_FORMAT, object_memory(
        decoded_object, decoded_page, decoded_file, struct.calcsize(picture.MEMORY_FORMAT)))
    return ObjectValues({**shared_values(decoded_object), "pic": pic})
