"""Reads a dual-state button back, on T, K, and F, as the compile's
dual_state_button module writes it (component_types/dual_state_button.py).

A dual-state button is written as the button of its sta and style is, but
for its val and its events. So its attributes are read as a button's
(decompiling/component_types/button.py, button_attributes), its val among
them, from where a button's memory keeps it.

The Nextion Editor starts its down event with code of its own: a
checkbox's, which switches its val between 0 and 1, then a ref of itself
(dual_state_button.event_blocks). Its up event has none. The decoder checks
those blocks against what the compile writes, and gives them, so that the
source folder leaves them out.
"""
from nxwright.tft.component_types import SERIES_WRITTEN_AS_P
from nxwright.tft.decompiling.component_types.button import button_attributes, events_start
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import ObjectValues


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the dual-state button's ObjectValues (decompiling/objects.py).
    Raises DecodeError when its entries are not those of any variant, or
    when its down event does not start with the code the Nextion Editor
    adds."""
    attributes, module = button_attributes(decoded_object, decoded_page, decoded_file)
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return ObjectValues(attributes)
    return ObjectValues(attributes, events_start(
        decoded_object, decoded_page, decoded_file, module.EVENTS,
        lambda place, event: module.event_blocks(decoded_file.series, place, event)))
