"""Reads a switch back, on P, as the compile's switch module writes it
(component_types/switch.py). Every value its memory keeps lies where one of
its named entries says (objects.p_values), and the Nextion Editor adds no
code for it.
"""
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import ObjectValues, p_values


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the switch's ObjectValues (decompiling/objects.py). Raises
    DecodeError as p_values does."""
    return ObjectValues(p_values(decoded_object, decoded_page, decoded_file))
