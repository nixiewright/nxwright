"""Reads a sliding text back, on P, as the compile's sliding_text module
writes it (component_types/sliding_text.py), with the reader the types of P
share whose entries their border and what lies behind them change
(p_bordered_values). That reader also reads its path in its txt's room at a
path_m of 0 (P_ROOMS_WHEN_ZERO), and its leftshow, which no entry gives.

Its key has no entry either. A key that binds a keyboard adds lines at the
end of its Touch Release event, which are read back as a text's are
(objects.with_key).
"""
from nxwright.tft.decompiling.component_types import p_bordered_values
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import ObjectValues, with_key


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the sliding text's ObjectValues (decompiling/objects.py).
    Raises DecodeError as p_bordered_values does."""
    values = p_bordered_values(decoded_object, decoded_page, decoded_file)
    keyed = with_key(values.attributes, decoded_object, decoded_page, decoded_file)
    return ObjectValues(keyed.attributes, {**values.added, **keyed.added})
