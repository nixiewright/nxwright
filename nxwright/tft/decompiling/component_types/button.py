"""Reads a button back, on T, K, F, and P, as the compile's button module
writes it (component_types/button.py).

A button's variant, by its sta and its style, sets which entries it has
(that module's docstring). Its sta's entry comes first among its own. At a
sta of 1, a colour behind it, its style's entry follows. At any sta, a
style of 1 gives two more entries, its borderc's and its borderw's. So the
decoder reads the sta, then the style, or whether the border's entries are
there, and asks the compile for that variant.

The entries give the sta, the style, the border's colour and width, the
txt_maxl, and the spax and spay. The memory gives the font, the val, what
lies behind the button, released and pressed, its pco and pco2, xcen, ycen,
and isbr, then its txt. Behind a picture or a crop, a style draws as none,
and only a style of 1 leaves a trace, so the style is not given there
otherwise.

The Nextion Editor starts each of a button's events, down and up, with code
of its own: the button's val set to 1 or to 0, then a ref of itself
(button.event_blocks). The decoder checks those blocks against what the
compile writes, and gives them, so that the source folder leaves them out.

A dual-state button is written as the button of its sta and style is, but
for its val and its events, so its decoder reads it with this module's
button_attributes and events_start (dual_state_button.py).

On P, a button's values lie where its named entries say, which
objects.p_values reads. Behind anything but a colour, its style has no
entry, and a bordered style is known by its border's entries alone
(objects.p_kept_style). The Nextion Editor adds no code to its events. A
dual-state button's are read the same way.
"""
import struct

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, ObjectPlace, button
from nxwright.tft.decompiling import DecodeError, numbers
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (ObjectValues, described, entry_value, kept_style,
                                       object_memory, p_kept_style, p_values, record_head,
                                       shared_values)


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the button's ObjectValues (decompiling/objects.py). Raises
    DecodeError when its entries are not those of any variant, or when an
    event does not start with the code the Nextion Editor adds."""
    attributes, module = button_attributes(decoded_object, decoded_page, decoded_file)
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return ObjectValues(attributes)
    return ObjectValues(attributes, events_start(decoded_object, decoded_page, decoded_file,
                                                 module.EVENTS, module.event_blocks))


def button_attributes(decoded_object: DecodedObject, decoded_page: DecodedPage,
                      decoded_file: DecodedFile) -> tuple:
    """Returns (the attributes of `decoded_object`, a button or a dual-state
    button, the variant of its sta and style that its type's module gives).
    Raises DecodeError when its entries are not those of any variant."""
    head = record_head(decoded_object)
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        attributes = p_kept_style(p_values(decoded_object, decoded_page, decoded_file),
                                  button.BORDERED)
        return attributes, described(head.type_number, attributes)
    attributes = shared_values(decoded_object)
    effect = attributes["effect"]

    def variant(sta: int, style: int):
        return described(head.type_number, {"sta": sta, "style": style, "effect": effect})

    def value(module, name: str) -> int:
        return entry_value(decoded_object, module.attribute_place(name))

    sta = value(variant(button.COLOUR, 0), "sta")
    style = kept_style(decoded_object, variant, sta, value(variant(button.COLOUR, 0), "style"),
                       button)
    if style is not None:
        attributes["style"] = style
    module = variant(sta, style or 0)
    if sta not in button.BACKGROUNDS or module.ENTRIES != len(decoded_object.entries):
        raise DecodeError("%s %d has %d entries, but one of sta %d and style %d has %d"
                          % (decoded_object.type_name, decoded_object.object_id,
                             len(decoded_object.entries), sta, style or 0, module.ENTRIES),
                          head.drawing_place, b"".join(decoded_object.entries))
    attributes["sta"] = sta
    names = ["txt_maxl", "spax", "spay"]
    if style == button.BORDERED:
        names += ["borderc", "borderw"]
    attributes.update({name: value(module, name) for name in names})
    # What lies behind it, released and pressed, by its sta.
    behind = dict(zip(("background", "background2"), button.BACKGROUNDS[sta]))
    starting = struct.calcsize(button.MEMORY_FORMAT)
    memory = object_memory(decoded_object, decoded_page, decoded_file,
                           starting + attributes["txt_maxl"] + 1)
    for name, number in zip(button.MEMORY_VALUES,
                            struct.unpack(button.MEMORY_FORMAT, memory[:starting])):
        attributes[behind.get(name, name)] = number
    attributes["txt"] = memory[starting:].split(b"\x00", 1)[0]
    return attributes, module


def events_start(decoded_object: DecodedObject, decoded_page: DecodedPage,
                 decoded_file: DecodedFile, events: tuple, event_blocks) -> dict:
    """Returns ObjectValues' added of the blocks the Nextion Editor writes at
    the start of the `events` of `decoded_object`, a button or a dual-state
    button, as `event_blocks(place, event)` writes them, its variant's, as
    the version of `decoded_file` numbers them (numbers.as_written).
    Raises DecodeError when an event does not start with them."""
    place = ObjectPlace(decoded_page.page_id, decoded_object.object_id,
                        decoded_object.first_entry, decoded_page.objects[0].first_entry,
                        decoded_object.base)
    added = {}
    for event in events:
        expected = [numbers.as_written(block, decoded_file.series, decoded_file.version)
                    for block in event_blocks(place, event)]
        if not expected:
            continue
        run = decoded_object.events[event]
        if run.blocks[:len(expected)] != expected:
            raise DecodeError("%s %d's %s event does not start with the code the Nextion "
                              "Editor adds" % (decoded_object.type_name,
                                               decoded_object.object_id, event),
                              run.place, b"".join(run.blocks[:len(expected)]))
        added[event] = (len(expected), 0)
    return added
