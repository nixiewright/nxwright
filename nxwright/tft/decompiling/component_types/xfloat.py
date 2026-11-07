"""Reads an xfloat component back, on T, K, F, and P, as the compile's xfloat
module writes it (component_types/xfloat.py): as the number of its sta and
style is written, its vvs0 and vvs1 in the places of a number's lenth and
format (xfloat.DIGITS). So the number's decoder reads it, and its lenth and
format come back as the xfloat's vvs0 and vvs1.

Its key, and the lines the key adds, are read back as a number's are.

On P, the named entries give the xfloat's own names, vvs0 and vvs1, so
they need no renaming.
"""
from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, xfloat
from nxwright.tft.decompiling.component_types import number
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import ObjectValues


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the xfloat's ObjectValues (decompiling/objects.py). Raises
    DecodeError as the number's decoder does."""
    values = number.decoded_values(decoded_object, decoded_page, decoded_file)
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return values
    for name, (in_place_of, _) in xfloat.DIGITS.items():
        values.attributes[name] = values.attributes.pop(in_place_of)
    return values
