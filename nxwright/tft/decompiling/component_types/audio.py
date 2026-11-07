"""Reads an audio's attributes back, as the compile's audio module writes
them on P (component_types/audio.py): its values, where its named entries
say, and, when it plays a file, the room of its path, where its memory
keeps it (p_played_values). Its from gives whether it plays one
of the project's sounds or a file, and so its variant. The Nextion Editor
adds the init block with its ID to its page's load section
(objects.p_init_blocks).
"""
from nxwright.tft.decompiling.component_types import p_played_values
from nxwright.tft.decompiling.decoded_file import DecodedFile, DecodedObject, DecodedPage
from nxwright.tft.decompiling.objects import ObjectValues


def decoded_values(decoded_object: DecodedObject, decoded_page: DecodedPage,
                   decoded_file: DecodedFile) -> ObjectValues:
    """Returns the ObjectValues of the audio `decoded_object`, of
    `decoded_page`. Raises DecodeError when a value does not lie in its
    memory, and when its page's load section lacks its init block."""
    return p_played_values(decoded_object, decoded_page, decoded_file)
