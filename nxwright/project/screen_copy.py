"""Screen copies (".i" blocks): the version of a picture compiled into the screen.

Header (24 bytes), all values little-endian:
  +0   u8[4]  R 64 01 F. F is the format: 0, 3, or 4. R is 0a plus the
              rotation divided by 90 (0a to 0d). R is always 0a in format 3,
              and for a raw 1-by-1 picture in a compressed project.
  +4   u32    0
  +8   u32    header size (24)
  +12  u16    width
  +14  u16    height
  +16  u32    size of everything after the header
  +20  u32    offset of the alpha section, counted from the end of the header;
              0 when there is none

Raw format (0, FORMAT_RAW): one RGB565 word per pixel. There is no alpha; the
Editor blends each pixel against white.

Raw format with a second header (3, FORMAT_RAW_WITH_HEADER): 20 bytes, then
the pixels. When the second header's first u32 is 0, all 20 bytes are zero and
the pixels are as in the raw format. When it is 1, the pixels are compressed in
a scheme this module does not decode. Pixels are always stored in the 0-degree
order, whatever the screen rotation.

Compressed format (4, FORMAT_COMPRESSED): a second header of 20 bytes holding
1, width, height, 0, 0 as u32 (width and height swapped at a 90 or 270 degree
rotation), then colour blocks until every pixel is covered, then the optional
alpha section. Each colour block starts with a u32 control word; its lowest 4
bits are the block's kind:
  1 to 13  short runs: 8 RGB565 words follow. Each 4-bit field of the control
           word, lowest first, is how many pixels repeat the matching word
           (0: the word is unused). The lowest field is also the kind, so the
           first word always repeats 1 to 13 times.
  14       long run: the control word shifted right by 4 is a pixel count.
           8 RGB565 words follow; the run uses the first.
  15       literals: the control word shifted right by 4 is a count of RGB565
           words that follow, one per pixel.
Alpha is stored in 7 bits (0 to 127). In the alpha section, a byte with its
top bit set is one pixel's alpha in its low 7 bits. A byte with the top bit
clear is an alpha value, and the next byte is how many pixels have it.

Pixel order follows the project's screen rotation, in the raw and compressed
formats:
  0     rows top to bottom, each left to right
  90    columns left to right, each bottom to top
  180   rows bottom to top, each right to left
  270   columns right to left, each top to bottom

docs/format.md gives the formats' background: which screen models use
which, and how they were worked out.
"""
from collections import deque
from dataclasses import dataclass
from itertools import groupby
import struct

from PIL import Image

from nxwright import NxwrightError

FORMAT_RAW = 0
FORMAT_RAW_WITH_HEADER = 3
FORMAT_COMPRESSED = 4
ROTATIONS = (0, 90, 180, 270)
OPAQUE = 127

_FORMATS = (FORMAT_RAW, FORMAT_RAW_WITH_HEADER, FORMAT_COMPRESSED)
_MARK = b"\x64\x01"
ROTATION_MARKER_0 = 0x0a
_HEADER = struct.Struct("<4sIIHHII")
_SECOND_HEADER_SIZE = 20
_COMPRESSED_PREFIX = struct.Struct("<5I")
_CONTROL = struct.Struct("<I")
_EIGHT_WORDS = struct.Struct("<8H")
_SHORT_RUN_MAX = 13
_LONG_RUN, _LITERALS = 14, 15
# Long runs are whole multiples of 8 pixels, as in every screen copy the
# Editor has written. A run that fits in one short-run block (8 words of 13
# pixels) stays there, as the Editor does.
_LONG_RUN_MIN = 8 * _SHORT_RUN_MAX + 1
# Short-run blocks only pay off over literals when their 8 words cover more
# pixels than this.
_SHORT_BLOCK_MIN_PIXELS = 10
_ALPHA_COUNT_MAX = 255


class UndecodedScreenCopyError(NxwrightError):
    """Raised for a screen copy in a known variant this module cannot decode:
    a compressed FORMAT_RAW_WITH_HEADER picture."""


@dataclass
class ScreenPixels:
    """A picture as a screen copy stores it: per pixel an RGB565 colour and a
    7-bit alpha (OPAQUE = fully opaque), row by row from the top-left corner."""
    width: int
    height: int
    colours: list
    alphas: list


def screen_copy_format(block: bytes) -> int:
    """Returns the format of the screen copy `block`.

    Raises NxwrightError when the block is not a screen copy in a known format.
    """
    if (len(block) < _HEADER.size or block[1:3] != _MARK or block[3] not in _FORMATS
            or not ROTATION_MARKER_0 <= block[0] <= ROTATION_MARKER_0 + 3):
        raise NxwrightError("not a screen copy in a known format")
    return block[3]


def decode_screen_copy(block: bytes, rotation: int) -> ScreenPixels:
    """Decodes a screen copy whose pixels are stored in the order of `rotation`
    (FORMAT_RAW_WITH_HEADER always uses the 0-degree order).

    Raises UndecodedScreenCopyError for a compressed FORMAT_RAW_WITH_HEADER
    picture, and NxwrightError when the block is malformed or does not fit
    the rotation.
    """
    kind = screen_copy_format(block)
    if kind == FORMAT_RAW_WITH_HEADER:
        if block[_HEADER.size:_HEADER.size + 4] == b"\x01\x00\x00\x00":
            raise UndecodedScreenCopyError("compressed pictures in screen copy format 3 are not "
                                           "decoded yet")
        rotation = 0
    _, _, header_size, width, height, size, alpha_at = _HEADER.unpack_from(block, 0)
    if header_size != _HEADER.size or size != len(block) - _HEADER.size:
        raise NxwrightError("screen copy header does not match its size")
    count = width * height
    if kind == FORMAT_COMPRESSED:
        stored_colours, stored_alphas = _CompressedReader(block, width, height, alpha_at,
                                                          rotation).read()
    else:
        start = _HEADER.size + (_SECOND_HEADER_SIZE if kind == FORMAT_RAW_WITH_HEADER else 0)
        if alpha_at or len(block) != start + 2 * count or any(block[_HEADER.size:start]):
            raise NxwrightError("raw screen copy has the wrong size or second header")
        stored_colours = struct.unpack_from("<%dH" % count, block, start)
        stored_alphas = [OPAQUE] * count
    colours, alphas = [0] * count, [0] * count
    for stored, pixel in enumerate(stored_order(width, height, rotation)):
        colours[pixel], alphas[pixel] = stored_colours[stored], stored_alphas[stored]
    return ScreenPixels(width, height, colours, alphas)


def stored_order(width: int, height: int, rotation: int) -> list:
    """Returns, for each stored pixel in turn, its row-by-row index in the picture."""
    if rotation == 0:
        return list(range(width * height))
    if rotation == 180:
        return list(range(width * height - 1, -1, -1))
    if rotation == 90:
        return [y * width + x for x in range(width) for y in range(height - 1, -1, -1)]
    if rotation == 270:
        return [y * width + x for x in range(width - 1, -1, -1) for y in range(height)]
    raise NxwrightError("rotation %r is not one of %s" % (rotation, ROTATIONS))


def stored_pixels(image: Image.Image, kind: int) -> ScreenPixels:
    """Returns what a screen copy of format `kind` stores for `image`, an
    RGBA image.

    Colours keep the top bits of each channel, after the Editor's handling of
    alpha. It premultiplies each channel by alpha, rounding. The raw formats
    then add white for the transparent share. The compressed format divides
    back by alpha instead, truncating, so a partly transparent colour can lose
    precision; a fully transparent pixel's colour is 0.
    """
    # Each pixel as one number of its four bytes. Pictures hold few distinct
    # colours, so each is worked out once.
    pixels = struct.unpack("<%dI" % (image.width * image.height), image.tobytes())
    colour_of, alpha_of = {}, {}
    for pixel in set(pixels):
        colour_of[pixel], alpha_of[pixel] = _stored_pixel(pixel.to_bytes(4, "little"), kind)
    return ScreenPixels(image.width, image.height, list(map(colour_of.__getitem__, pixels)),
                        list(map(alpha_of.__getitem__, pixels)))


def _stored_pixel(pixel: bytes, kind: int) -> tuple:
    """Returns (RGB565 colour, alpha) that a screen copy of format `kind`
    stores for one pixel, its red, green, blue, and alpha bytes, as
    stored_pixels describes."""
    red, green, blue, alpha = pixel
    premultiplied = [(channel * alpha + 127) // 255 for channel in (red, green, blue)]
    if kind != FORMAT_COMPRESSED:
        channels = [channel + 255 - alpha for channel in premultiplied]
        alpha = 255
    elif alpha == 0:
        channels = [0, 0, 0]
    else:
        channels = [min(255, channel * 255 // alpha) for channel in premultiplied]
    return rgb565(*channels), alpha * OPAQUE // 255


def rgb565(red: int, green: int, blue: int) -> int:
    """Packs 8-bit channels into RGB565 by keeping each channel's top bits."""
    return ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)


def matches_within_editor_rounding(decoded: ScreenPixels, image: Image.Image, kind: int) -> bool:
    """True when `decoded` matches what a screen copy of format `kind` stores for
    `image` as closely as the Editor's own screen copies do: same size and
    alphas, colours exact where the picture's pixel is opaque or fully transparent,
    and within one step per channel where it is partly transparent.
    (stored_pixels matches most of the Editor's partly transparent colours
    exactly, but not all: the rest differ by one step.)
    """
    expected = stored_pixels(image, kind)
    if (decoded.width, decoded.height, decoded.alphas) != (expected.width, expected.height,
                                                          expected.alphas):
        return False
    for colour, wanted, alpha in zip(decoded.colours, expected.colours,
                                     image.getchannel("A").tobytes()):
        if colour != wanted and (alpha in (0, 255) or not _within_one_step(colour, wanted)):
            return False
    return True


def _within_one_step(first: int, second: int) -> bool:
    """Returns whether two RGB565 colours differ by at most one step in each channel."""
    return all(abs((first >> shift & mask) - (second >> shift & mask)) <= 1
               for shift, mask in ((11, 31), (5, 63), (0, 31)))


def encode_screen_copy(pixels: ScreenPixels, kind: int, rotation: int) -> bytes:
    """Encodes `pixels` as a screen copy of format `kind`, in the pixel order of
    `rotation` (FORMAT_RAW_WITH_HEADER: always the 0-degree order, uncompressed).

    Raises NxwrightError for a 1-by-1 picture in the compressed format, which
    the Editor itself failed to add to a project of that format.
    """
    count = pixels.width * pixels.height
    if max(pixels.width, pixels.height) > 0xFFFF:
        raise NxwrightError("a picture side longer than 65535 pixels cannot be stored")
    if len(pixels.colours) != count or len(pixels.alphas) != count:
        raise NxwrightError("picture data does not match its size")
    if kind not in _FORMATS:
        raise NxwrightError("screen copy format %r is not supported" % kind)
    if kind == FORMAT_RAW_WITH_HEADER:
        rotation = 0     # this format ignores the screen rotation
    order = stored_order(pixels.width, pixels.height, rotation)
    colours = list(map(pixels.colours.__getitem__, order))
    alpha_at = 0
    if kind == FORMAT_COMPRESSED:
        if count < 2:
            raise NxwrightError("a 1-by-1 picture cannot be stored in the compressed format")
        sides = (pixels.height, pixels.width) if rotation in (90, 270) else (pixels.width, pixels.height)
        body = _COMPRESSED_PREFIX.pack(1, *sides, 0, 0) + _encode_colours(colours)
        alphas = list(map(pixels.alphas.__getitem__, order))
        # OPAQUE is the highest alpha: below it, some pixel is not opaque.
        if min(alphas) < OPAQUE:
            alpha_at = len(body)
            body += encode_alphas(alphas)
    else:
        second_header = bytes(_SECOND_HEADER_SIZE) if kind == FORMAT_RAW_WITH_HEADER else b""
        body = second_header + struct.pack("<%dH" % count, *colours)
    marker = ROTATION_MARKER_0 + (0 if kind == FORMAT_RAW_WITH_HEADER else rotation // 90)
    header = _HEADER.pack(bytes([marker]) + _MARK + bytes([kind]), 0, _HEADER.size,
                          pixels.width, pixels.height, len(body), alpha_at)
    return header + body


class _CompressedReader:
    """Reads the colour blocks and alpha section of one compressed screen copy."""

    def __init__(self, block: bytes, width: int, height: int, alpha_at: int, rotation: int):
        self._block = block
        self._count = width * height
        self._end = _HEADER.size + alpha_at if alpha_at else len(block)
        if self._end > len(block):
            raise NxwrightError("screen copy alpha section starts past its end")
        sides = (height, width) if rotation in (90, 270) else (width, height)
        if self._unpack(_COMPRESSED_PREFIX, _HEADER.size) != (1, *sides, 0, 0):
            raise NxwrightError("compressed screen copy has a second header that does not fit "
                                "a %d degree rotation" % rotation)
        self._pos = _HEADER.size + _COMPRESSED_PREFIX.size
        self._has_alpha = bool(alpha_at)

    def read(self) -> tuple:
        """Returns (colours, alphas), both in stored order."""
        colours = self._read_colours()
        alphas = self._read_alphas() if self._has_alpha else [OPAQUE] * self._count
        return colours, alphas

    def _read_colours(self) -> list:
        colours = []
        while len(colours) < self._count:
            control, = self._unpack(_CONTROL, self._pos)
            self._pos += 4
            kind = control & 15
            if kind == 0:
                raise NxwrightError("screen copy has a colour block of unknown kind 0")
            # A corrupt count must fail here, before it builds a huge list.
            if kind in (_LITERALS, _LONG_RUN) and len(colours) + (control >> 4) > self._count:
                raise NxwrightError("screen copy colour block runs past the last pixel")
            if kind == _LITERALS:
                count = control >> 4
                colours += self._unpack(struct.Struct("<%dH" % count), self._pos)
                self._pos += 2 * count
            else:
                words = self._unpack(_EIGHT_WORDS, self._pos)
                self._pos += 16
                if kind == _LONG_RUN:
                    colours += [words[0]] * (control >> 4)
                else:
                    for index, word in enumerate(words):
                        colours += [word] * (control >> 4 * index & 15)
        if len(colours) != self._count or self._pos != self._end:
            raise NxwrightError("screen copy colour blocks do not cover the picture exactly")
        return colours

    def _read_alphas(self) -> list:
        alphas = decode_alphas(self._block[self._pos:], self._count)
        self._pos = len(self._block)
        return alphas

    def _unpack(self, layout: struct.Struct, pos: int) -> tuple:
        if pos + layout.size > self._end:
            raise NxwrightError("screen copy block runs past the end of its section")
        return layout.unpack_from(self._block, pos)


def _runs(values: list) -> deque:
    """Returns [value, count] pairs for each stretch of equal values."""
    return deque([value, len(list(stretch))] for value, stretch in groupby(values))


def _encode_colours(colours: list) -> bytes:
    """Encodes colours, already in stored order, as colour blocks.

    Long stretches of one colour become long runs; stretches where colours
    repeat become short-run blocks; the rest become literal blocks.
    """
    out = bytearray()
    literals = []
    pending = _runs(colours)
    while pending:
        value, count = pending[0]
        if count >= _LONG_RUN_MIN:
            out += _flush_literals(literals)
            long_count = count - count % 8
            out += struct.pack("<I8H", long_count << 4 | _LONG_RUN, *[value] * 8)
            pending[0][1] -= long_count
            if not pending[0][1]:
                pending.popleft()
            continue
        chunks = _short_run_chunks(pending)
        if sum(length for _, length in chunks) > _SHORT_BLOCK_MIN_PIXELS:
            out += _flush_literals(literals)
            out += _short_run_block(chunks)
            _consume(pending, sum(length for _, length in chunks))
        else:
            literals.append(value)
            _consume(pending, 1)
    out += _flush_literals(literals)
    return bytes(out)


def _short_run_chunks(pending: deque) -> list:
    """Returns up to 8 (value, length) chunks from the front of `pending`, each
    at most _SHORT_RUN_MAX long, stopping before a run long enough for a
    long-run block."""
    chunks = []
    for value, count in pending:
        if chunks and count >= _LONG_RUN_MIN:
            break
        while count and len(chunks) < 8:
            length = min(count, _SHORT_RUN_MAX)
            chunks.append((value, length))
            count -= length
        if len(chunks) == 8:
            break
    return chunks


def _short_run_block(chunks: list) -> bytes:
    """Returns one short-run colour block for up to 8 (value, length) chunks."""
    control = 0
    for index, (_, length) in enumerate(chunks):
        control |= length << 4 * index
    words = [value for value, _ in chunks] + [0] * (8 - len(chunks))
    return struct.pack("<I8H", control, *words)


def _consume(pending: deque, count: int):
    """Removes `count` pixels from the front of the run list `pending`."""
    while count:
        taken = min(count, pending[0][1])
        pending[0][1] -= taken
        count -= taken
        if not pending[0][1]:
            pending.popleft()


def _flush_literals(literals: list) -> bytes:
    """Returns a literal block for `literals` (empty if none) and clears it."""
    if not literals:
        return b""
    block = struct.pack("<I%dH" % len(literals), len(literals) << 4 | _LITERALS, *literals)
    literals.clear()
    return block


def decode_alphas(section: bytes, count: int) -> list:
    """Decodes an alpha section (encode_alphas) of `count` pixels into their
    7-bit alphas, in stored order. Raises NxwrightError unless the section
    covers them exactly. PictureBox codes a .xi file's alpha alike
    (media_files.py)."""
    alphas, at = [], 0
    while len(alphas) < count and at < len(section):
        value = section[at]
        if value & 0x80:
            alphas.append(value & OPAQUE)
            at += 1
        elif at + 1 < len(section):
            alphas += [value] * section[at + 1]
            at += 2
        else:
            break
    if len(alphas) != count or at != len(section):
        raise NxwrightError("screen copy alpha section does not cover the picture exactly")
    return alphas


def encode_alphas(alphas: list) -> bytes:
    """Encodes 7-bit alphas, already in stored order, as the alpha section."""
    out = bytearray()
    for value, count in _runs(alphas):
        while count:
            if count == 1:
                out.append(0x80 | value)
                count = 0
            else:
                taken = min(count, _ALPHA_COUNT_MAX)
                out += bytes([value, taken])
                count -= taken
    return bytes(out)
