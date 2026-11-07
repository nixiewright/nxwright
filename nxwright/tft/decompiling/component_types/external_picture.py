"""Reads an external picture's attributes back, as the compile's
external_picture module writes them on P (component_types/external_picture.py):
its values, where its named entries say, and the room of its path, where
its memory keeps it (objects.p_values_and_rooms). The Nextion Editor adds
no code of its own for an external picture.
"""
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import ObjectValues, p_values_and_rooms


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of the external picture `decoded_object`, of
    `decoded_page`. Raises DecodeError when a value does not lie in its
    memory."""
    return ObjectValues(p_values_and_rooms(decoded_object, decoded_page, decoded_file))
