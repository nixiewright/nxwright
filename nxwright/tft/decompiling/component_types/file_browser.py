"""Reads a file browser back, on P, as the compile's file_browser module writes it
(component_types/file_browser.py), with the reader the types of P share whose
entries their border and what lies behind them change (p_bordered_values).
"""
from nxwright.tft.decompiling.component_types import p_bordered_values
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import ObjectValues


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the file browser's ObjectValues (decompiling/objects.py). Raises
    DecodeError as p_bordered_values does."""
    return p_bordered_values(decoded_object, decoded_page, decoded_file)
