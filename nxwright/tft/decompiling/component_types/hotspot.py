"""Reads a hotspot's attributes back, as the compile's hotspot module writes
them on T, K, and F (component_types/hotspot.py): what every drawn
component keeps in its record (objects.shared_values), and whether it has
an effect. A hotspot draws nothing, and has no memory and no entries of its
own. So its first entry after a drawn object's is empty whether or not it
has an effect, and the effect is told from how many entries it has, as the
compile's description of a hotspot with one and without one gives them.
The Nextion Editor adds no code of its own for a hotspot.

On P, a hotspot's values lie where its named entries say, which
objects.p_values reads.
"""
from nxwright.tft.component_types import SERIES_WRITTEN_AS_P
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import (AN_EFFECT, ObjectValues, described, p_values,
                                       record_head, shared_values)


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of the hotspot `decoded_object`. Raises
    DecodeError when its number of entries is not one a hotspot has."""
    if decoded_file.series in SERIES_WRITTEN_AS_P:
        return ObjectValues(p_values(decoded_object, decoded_page, decoded_file))
    head = record_head(decoded_object)
    counts = {effect: described(head.type_number, {"effect": effect}).ENTRIES
              for effect in (0, AN_EFFECT)}
    effect = next((effect for effect, count in counts.items()
                   if count == len(decoded_object.entries)), None)
    if effect is None:
        raise DecodeError("hotspot %d has %d entries, but a hotspot has %d, or %d with an "
                          "effect" % (decoded_object.object_id, len(decoded_object.entries),
                                      counts[0], counts[AN_EFFECT]),
                          head.drawing_place, b"".join(decoded_object.entries))
    return ObjectValues({**shared_values(decoded_object), "effect": effect})
