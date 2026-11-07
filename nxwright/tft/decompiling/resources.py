"""Turns the pictures, the fonts, and on P and E the animations, videos, and
sounds of a TFT file's resources section back into their project blocks, as
a source folder keeps them, undoing what the compile's packaging does to them
(packaging._headers_first and packaging._sounds).

The section keeps each kind's blocks in a part of their own, every header
first, then every block's rest. In the part, each header gives where its
block's rest lies in the part, and a picture's header gives its ID too. In
the project, a header gives where its rest lies in its block, right after
the header, and a picture's gives an ID of 0. So the decoder cuts each
block's rest out of the part, from its place to the next block's, and puts
those two fields back. One block alone is the same in both. An animation's
block is its screen form, which a project keeps beside GmovMaker's file of
it.

A sound's part is laid out otherwise: a header of its own for each sound,
which gives where the sound's WAV file lies in the part and its length,
then the files, each as it is.

Each font is given as the TFT file keeps it, at 0 degrees on F and at the
project's rotation on the other series (packaging.font_orientation), and
none is turned. A project may keep a font in any orientation, and the
compile writes one already in the TFT file's as it is.

A DecodeError of this module gives the place 0, as the resources section
lies before the user code, which a DecodeError's place is counted from.
"""
import struct

from nxwright.tft.decompiling import DecodeError
from nxwright.tft.packaging import (FONT_HEADER, FONT_PLACE_FIELD, MEDIA_HEADER,
                             MEDIA_PLACE_FIELD, PICTURE_HEADER, PICTURE_ID_FIELD,
                             PICTURE_PLACE_FIELD, SOUND_HEADER)


def picture_blocks(part: bytes, count: int) -> list:
    """Returns the project blocks of the `count` pictures of the section's
    part of pictures `part`, in ID order. Raises DecodeError for a part
    whose headers do not place each picture's rest after the one before."""
    return _blocks_of(part, count, PICTURE_HEADER, PICTURE_PLACE_FIELD, PICTURE_ID_FIELD)


def stored_font_blocks(part: bytes, count: int) -> list:
    """Returns the blocks of the `count` fonts of the section's part of
    fonts `part`, in ID order, as the file stores them, which on F is at 0
    degrees. Raises DecodeError for a part whose headers do not place each
    font's rest after the one before."""
    return _blocks_of(part, count, FONT_HEADER, FONT_PLACE_FIELD)


def media_blocks(part: bytes, count: int) -> list:
    """Returns the project blocks of the `count` animations or videos of
    the section's part of them `part`, in ID order: an animation's screen
    form, or a video's file. Raises DecodeError for a part whose headers do
    not place each one's rest after the one before."""
    return _blocks_of(part, count, MEDIA_HEADER, MEDIA_PLACE_FIELD)


def sound_blocks(part: bytes, count: int) -> list:
    """Returns the project blocks of the `count` sounds of the section's part
    of sounds `part`, in ID order, each its WAV file. Raises DecodeError for
    a part whose headers do not place each sound after the headers and
    within the part."""
    if len(part) < SOUND_HEADER.size * count:
        raise DecodeError("the section's part of %d sounds is shorter than their headers"
                          % count, 0, part)
    blocks = []
    for number in range(count):
        place, size = SOUND_HEADER.unpack_from(part, SOUND_HEADER.size * number)
        if not SOUND_HEADER.size * count <= place <= place + size <= len(part):
            raise DecodeError("the section's part of %d sounds places sound %d outside it"
                              % (count, number), 0,
                              part[SOUND_HEADER.size * number:SOUND_HEADER.size * (number + 1)])
        blocks.append(part[place:place + size])
    return blocks


def _blocks_of(part: bytes, count: int, header_size: int, place_field: int,
               id_field: int = None) -> list:
    """Returns the project blocks of the `count` resources of `part`, each a
    header of `header_size` bytes, which gives at `place_field` where its
    rest lies in the part, and at `id_field`, if any, its ID. In each block,
    those fields give where its rest lies in it, and 0."""
    if len(part) < header_size * count:
        raise DecodeError("the section's part of %d resources is shorter than their headers"
                          % count, 0, part)
    headers = [part[header_size * number:header_size * (number + 1)]
               for number in range(count)]
    places = [struct.unpack_from("<I", header, place_field)[0] for header in headers]
    ends = places[1:] + [len(part)]
    if not all(header_size * count <= place <= end <= len(part)
               for place, end in zip(places, ends)):
        raise DecodeError("the section's part of %d resources does not place each one's rest "
                          "after the one before" % count, 0, part[:header_size * count])
    blocks = []
    for header, place, end in zip(headers, places, ends):
        header = bytearray(header)
        struct.pack_into("<I", header, place_field, header_size)
        if id_field is not None:
            struct.pack_into("<I", header, id_field, 0)
        blocks.append(bytes(header) + part[place:end])
    return blocks
