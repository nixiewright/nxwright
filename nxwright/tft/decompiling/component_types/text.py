"""Reads a text component back, on T, K, F, and P, as the compile's text
module writes it (component_types/text.py).

A text's variant, by its sta and its style, sets which entries it has
(that module's docstring). Its sta's entry comes first among its own. At a
sta of 1, its style's entry follows. At any sta, a style of 1 gives two
more entries, its borderc's and its borderw's. So the decoder reads the sta,
then the style, or whether the border's entries are there, and asks the
compile for that variant.

The entries give the sta, the style, the border's colour and width, the
txt_maxl, and the spax and spay, and where in memory the others lie. The
memory gives the font, isbr, pco, what lies behind the text, its xcen,
ycen, and pw, then its txt. Behind a picture or a crop, a style draws as
none, and only a style of 1 leaves a trace, so the style is not given
there otherwise.

A text's key adds lines at the end of its Touch Release event, which open
its keyboard page. The decoder reads them back as its key, and gives them,
so that the source folder leaves them out (objects.key_values).

On P, a text's values lie where its named entries say, which
objects.p_values reads. Behind anything but a colour, its style has no
entry, and a bordered style is known by its border's entries alone
(objects.p_kept_style). Its key is read as on T.
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, text
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, entry_value, has_entry,
                                       kept_style, object_memory, p_kept_style, p_values,
                                       record_head, shared_values, with_key)

# What may lie behind a text, by the attribute that gives it.
_BEHIND = ("picc", "bco", "pic")


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the text's ObjectValues (decompiling/objects.py). Raises
    DecodeError when its entries are not those of any variant."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return with_key(p_kept_style(p_values(decoded_object, decoded_page, decoded_file),
                                     text.BORDERED),
                        decoded_object, decoded_page, decoded_file)
    head = record_head(decoded_object)
    attributes = shared_values(decoded_object)
    effect = attributes["effect"]

    def variant(sta: int, style: int):
        return described(head.type_number, {"sta": sta, "style": style, "effect": effect})

    def value(module, name: str) -> int:
        return entry_value(decoded_object, module.attribute_place(name))

    sta = value(variant(text.COLOUR, 0), "sta")
    style = kept_style(decoded_object, variant, sta, value(variant(text.COLOUR, 0), "style"),
                       text)
    if style is not None:
        attributes["style"] = style
    style = style or 0
    module = variant(sta, style)
    if module.ENTRIES != len(decoded_object.entries):
        raise DecodeError("text %d has %d entries, but a text of sta %d and style %d has %d"
                          % (decoded_object.object_id, len(decoded_object.entries), sta, style,
                             module.ENTRIES),
                          head.drawing_place, b"".join(decoded_object.entries))
    attributes["sta"] = sta
    names = ["txt_maxl", "spax", "spay"]
    if style == text.BORDERED:
        names += ["borderc", "borderw"]
    attributes.update({name: value(module, name) for name in names})
    behind = [name for name in _BEHIND if has_entry(module, name)]
    starting = struct.calcsize(text.MEMORY_FORMAT)
    memory = object_memory(decoded_object, decoded_page, decoded_file,
                           starting + attributes["txt_maxl"] + 1)
    for name, number in zip(text.MEMORY_VALUES,
                            struct.unpack(text.MEMORY_FORMAT, memory[:starting])):
        if name != "background":
            attributes[name] = number
        elif behind:
            attributes[behind[0]] = number
    attributes["txt"] = memory[starting:].split(b"\x00", 1)[0]
    return with_key(attributes, decoded_object, decoded_page, decoded_file)

