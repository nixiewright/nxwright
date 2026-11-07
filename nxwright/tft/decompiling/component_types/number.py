"""Reads a number component back, on T, K, F, and P, as the compile's number
module writes it (component_types/number.py).

A number keeps every value in its memory: its sta and style, its borderc
and borderw, font, what lies behind it, pco, xcen, ycen, val, lenth,
format, isbr, spax, and spay. Its variant, by its sta and its style, sets
which entries it has (that module's docstring), as a text's does
(objects.kept_style). Behind a picture or a crop, its memory keeps a style
of 0, and its borderc and borderw only at a style of 1.

An xfloat is written as a number is, and its decoder reads it with this
one (decompiling/component_types/xfloat.py).

A number's key adds lines at the end of its Touch Release event, which
open its keyboard page. The decoder reads them back as its key, and gives
them, so that the source folder leaves them out (objects.key_values).

On P, a number's values lie where its named entries say, which
objects.p_values reads. Behind anything but a colour, its style has no
entry, and a bordered style is known by its border's entries alone
(objects.p_kept_style). Its key is read as on T.
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, number
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, has_entry, kept_style,
                                       object_memory, p_kept_style, p_values, record_head,
                                       shared_values, with_key)

# What may lie behind a number, by the attribute that gives it.
_BEHIND = ("picc", "bco", "pic")
# The values its memory gives that its variant reads, and its border's.
_VARIANT_VALUES = ("sta", "style")
_BORDER_VALUES = ("borderc", "borderw")


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the number's ObjectValues (decompiling/objects.py). Raises
    DecodeError when its entries are not those of the variant its memory
    gives."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return with_key(p_kept_style(p_values(decoded_object, decoded_page, decoded_file),
                                     number.BORDERED), decoded_object, decoded_page,
                        decoded_file)
    head = record_head(decoded_object)
    attributes = shared_values(decoded_object)
    effect = attributes["effect"]

    def variant(sta: int, style: int):
        return described(head.type_number, {"sta": sta, "style": style, "effect": effect})

    memory = dict(zip(number.MEMORY_VALUES, struct.unpack(number.MEMORY_FORMAT, object_memory(
        decoded_object, decoded_page, decoded_file, struct.calcsize(number.MEMORY_FORMAT)))))
    sta = memory["sta"]
    style = kept_style(decoded_object, variant, sta, memory["style"], number)
    module = variant(sta, style or 0)
    if module.ENTRIES != len(decoded_object.entries):
        raise DecodeError("%s %d has %d entries, but one of sta %d and style %d has %d"
                          % (decoded_object.type_name, decoded_object.object_id,
                             len(decoded_object.entries), sta, style or 0, module.ENTRIES),
                          head.drawing_place, b"".join(decoded_object.entries))
    attributes["sta"] = sta
    if style is not None:
        attributes["style"] = style
    behind = [name for name in _BEHIND if has_entry(module, name)]
    for name, value in memory.items():
        if name == "background":
            if behind:
                attributes[behind[0]] = value
        elif name in _BORDER_VALUES:
            if style == number.BORDERED:
                attributes[name] = value
        elif name not in _VARIANT_VALUES:
            attributes[name] = value
    return with_key(attributes, decoded_object, decoded_page, decoded_file)
