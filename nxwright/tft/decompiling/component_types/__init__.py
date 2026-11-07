"""The component types' decoders, one module for each type the compile's
component_types/ writes, of the same name, as text.py for a text. Each has
a function decoded_values(decoded_object, decoded_page, decoded_file),
which returns the component's ObjectValues (decompiling/objects.py).

The types of P whose entries their border and what lies behind them change
share one reader, p_bordered_values: the select, the combo box, the sliding
text, the file browser, and the data record. The gmov, the video, and the
audio share another, p_played_values.
"""
from nxwright.tft import component_types
from nxwright.tft.component_types import P_BORDERED, p_texts
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, memory_at, p_init_blocks,
                                       p_kept_style, p_text_rooms, p_values,
                                       p_values_and_rooms)

# The bytes of the place of a text that a component keeps on P (P_TEXTS).
_TEXT_PLACE_SIZE = 4


def p_bordered_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                      decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of `decoded_object`, a component on P of a
    type whose entries its border and what lies behind it change
    (component_types.with_p_border and with_p_background):

    - its values, from its named entries (objects.p_values);
    - its style at 1 when its border's entries are there but its style's is
      not (objects.p_kept_style);
    - the rooms of its texts (objects.p_text_rooms), and each text that no
      entry gives, as a sliding text's path, from the place its memory
      keeps (P_TEXTS). A text whose room is 0 has another attribute's room,
      as its type's P_ROOMS_WHEN_ZERO gives, so it is read in that room;
    - each byte of its memory that no entry gives, where its type's
      P_UNENTERED places it.

    Its added code is the init block the Nextion Editor starts its page's
    load section with (objects.p_init_blocks). Raises DecodeError as those
    readers do."""
    attributes = p_kept_style(p_values(decoded_object, decoded_page, decoded_file),
                              P_BORDERED)
    module = described(decoded_object.type_number, attributes)
    attributes.update(p_text_rooms(decoded_object, decoded_page, decoded_file, module))
    own = component_types.type_module(decoded_object.type_name)
    base = decoded_object.base
    # A text no entry gives, or one in another attribute's room, is read from
    # the place its memory keeps.
    for at, (name, maxl, _) in p_texts(module).items():
        other = getattr(own, "P_ROOMS_WHEN_ZERO", {}).get(maxl)
        room = maxl if other is None or attributes[maxl] else other
        if name in attributes and room == maxl:
            continue
        place = int.from_bytes(memory_at(decoded_object, decoded_page, decoded_file,
                                         base + at, _TEXT_PLACE_SIZE), "little")
        attributes[name] = memory_at(decoded_object, decoded_page, decoded_file, place,
                                     attributes[room] + 1).split(b"\x00", 1)[0]
    for name, at in getattr(own, "P_UNENTERED", {}).items():
        attributes[name] = memory_at(decoded_object, decoded_page, decoded_file, base + at, 1)[0]
    init = p_init_blocks(decoded_object, decoded_page, decoded_file)
    return ObjectValues(attributes, {"load": (init, 0)})


def p_played_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                    decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of `decoded_object`, a gmov, a video, or an
    audio on P: its values, where its named entries say, and the room of
    any path it keeps (objects.p_values_and_rooms). Its added code is the
    init block the Nextion Editor starts its page's load section with
    (objects.p_init_blocks). Raises DecodeError as those readers do."""
    return ObjectValues(p_values_and_rooms(decoded_object, decoded_page, decoded_file),
                        {"load": (p_init_blocks(decoded_object, decoded_page, decoded_file), 0)})
