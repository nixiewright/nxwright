"""The manifest ("main.HMI"), image records ("N.is", "N.i"), and the kinds
of resource stored as files byte for byte. A font's header ("N.zi") is
zi_font.py's.

All numbers are little-endian.

Manifest layout:
  +0   u32   stamp
  +4   u32   header size (96)
  +24  u32   offset of the resource table (96)
  +28  u32   resource count
  then 16 bytes per resource: an 8-byte extension ("i", "zi", "pa") and an
  8-byte name ("0.i"), both NUL-padded.
The other header bytes are not understood and are reported raw.

Fonts, animations, videos, and sounds are stored as blocks that dumps and
source folders hold as files, byte for byte (CopiedKind). An animation has
two blocks: "N.gmovs" is the file GmovMaker writes, and "N.gmov" the form the
Editor makes of it when it is added, which the screen shows. A video's "N.v"
is the file VideoBox writes. A sound's "N.wav" is the WAV file as the Editor
converts it when it is added.

Image record (".is" holds the picture's file the Editor shows; ".i" the
screen copy, described in screen_copy.py):
  +8   u32   header size
  +12  u16   width
  +14  u16   height
  then the payload. An ".is" header also holds 0a 64 01 01 at +0, the file's
  length at +16, and from +24 to its end the suffix the file had when it was
  added, lower-cased: "png", "jpg", "jpeg". The Editor keeps the file as it
  is given, a PNG, a JPEG, a BMP, or a GIF, whatever its suffix says of it
  (seen in Editor 3.1.73, tests/test_picture_files.py).
"""
from dataclasses import dataclass
import struct

from nxwright import NxwrightError
from nxwright.project.container import numbered_block

# The suffixes of the picture files nxwright keeps, as a picture's record
# names them: those the Editor's Picture panel offers (.png, .jpg, .bmp),
# and those it takes when typed (.jpeg, .gif). A dump and a source folder
# name a picture's file with the suffix its record gives: "0003.jpg".
PICTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".gif")
# A picture record's header, before its suffix.
_IMAGE_SOURCE_HEADER = struct.Struct("<4sIIHHII")


@dataclass(frozen=True)
class CopiedKind:
    """A kind of resource stored as blocks that dumps and source folders hold
    as files, byte for byte, one file per block."""
    folder: str     # the folder of its files, in a dump and in a source folder
    noun: str       # one of them, in messages: "font"
    listed: str     # the extension of the block the manifest lists, which gives its ID
    blocks: tuple   # (block extension, file suffix) of each of its blocks, in file order

    @property
    def suffixes(self) -> tuple:
        return tuple(suffix for _, suffix in self.blocks)


FONTS = CopiedKind("fonts", "font", "zi", (("zi", ".zi"),))
# GmovMaker's file first, as users make and share it, then the screen's form.
ANIMATIONS = CopiedKind("animations", "animation", "gmov",
                        (("gmovs", ".gmov"), ("gmov", ".screen.gmov")))
VIDEOS = CopiedKind("videos", "video", "v", (("v", ".video"),))
SOUNDS = CopiedKind("sounds", "sound", "wav", (("wav", ".wav"),))
MEDIA = (ANIMATIONS, VIDEOS, SOUNDS)
COPIED_KINDS = (FONTS,) + MEDIA

# The kinds the manifest lists, in the order the Editor lists them.
LISTED_IN_ORDER = ("i", "zi", "gmov", "v", "wav", "pa")
# The blocks the manifest leaves out, each the partner of a listed block of
# the same number: a picture's file, and an animation's GmovMaker file.
_PARTNERS = (("is", "i", "picture"), ("gmovs", "gmov", "animation"))


@dataclass
class Manifest:
    """The project's resource list, plus its header bytes that are not understood."""
    header_size: int
    table_offset: int
    resources: list           # (extension, name) pairs, in stored order
    unknown_header: bytes     # header bytes 8 to 23 and 32 to the end of the header

    def block_names(self, extension: str) -> list:
        """Returns the names of the listed blocks with `extension`, in ID order.

        The Editor's ID of a page ("pa"), picture ("i"), font ("zi"),
        animation ("gmov"), video ("v"), or sound ("wav") is its position in
        this list, not the number in its block name.
        """
        return [name for kind, name in self.resources if kind == extension]


def parse_manifest(block: bytes) -> Manifest:
    """Parses the "main.HMI" block.

    Raises NxwrightError when the resource table does not fit the block.
    """
    if len(block) < 32:
        raise NxwrightError("manifest is shorter than its header")
    header_size, = struct.unpack_from("<I", block, 4)
    table_offset, count = struct.unpack_from("<II", block, 24)
    if header_size < 32 or table_offset + 16 * count != len(block):
        raise NxwrightError("manifest resource table does not match its size")
    resources = []
    for index in range(count):
        entry = block[table_offset + 16 * index:table_offset + 16 * (index + 1)]
        resources.append((_padded_text(entry[:8]), _padded_text(entry[8:])))
    return Manifest(header_size, table_offset, resources,
                    block[8:24] + block[32:header_size])


def with_kind_in_order(resources: list, extension: str, names: list) -> list:
    """Returns `resources`, a manifest's (extension, name) list, with the
    entries of kind `extension` replaced by `names` in that order.

    The positions that kind occupied keep their places and are filled in
    order. Extra names go right after the kind's last position; when it had
    none, where the Editor would list them (LISTED_IN_ORDER), before the
    first entry of a kind it lists later, or at the end. Positions left over
    are dropped. Other kinds are untouched.
    """
    positions = [index for index, (kind, _) in enumerate(resources) if kind == extension]
    result = list(resources)
    for position, name in zip(positions, names):
        result[position] = (extension, name)
    extra = [(extension, name) for name in names[len(positions):]]
    later = LISTED_IN_ORDER[LISTED_IN_ORDER.index(extension) + 1:]
    insert_at = positions[-1] + 1 if positions else next(
        (index for index, (kind, _) in enumerate(result) if kind in later), len(result))
    result[insert_at:insert_at] = extra
    for position in reversed(positions[len(names):]):
        del result[position]
    return result


def encode_manifest(original: bytes, resources: list) -> bytes:
    """Returns a manifest block with the header of `original` (resource count
    updated) and the resource list `resources`, unstamped (stamp field zero)."""
    manifest = parse_manifest(original)
    header = bytearray(original[:manifest.table_offset])
    header[0:4] = bytes(4)
    struct.pack_into("<I", header, 28, len(resources))
    table = b"".join(kind.encode("latin-1").ljust(8, b"\0") + name.encode("latin-1").ljust(8, b"\0")
                     for kind, name in resources)
    return bytes(header) + table


def check_manifest_matches_blocks(manifest: Manifest, blocks: dict):
    """Stops unless the manifest lists every live block of each kind it lists
    (LISTED_IN_ORDER) exactly once and nothing else, and every listed picture
    ("N.i") has its file's block ("N.is"), and every listed animation ("N.gmov")
    its GmovMaker file ("N.gmovs"), and the reverse.

    IDs are positions in the manifest's lists, so any mismatch would make them
    ambiguous. `blocks` maps live block names to their bytes.
    """
    for extension in LISTED_IN_ORDER:
        listed = manifest.block_names(extension)
        live = [name for name in blocks if numbered_block(name, extension) is not None]
        if len(set(listed)) != len(listed) or set(listed) != set(live):
            raise NxwrightError("the manifest's list of .%s blocks does not match the "
                                "live blocks, so their IDs are ambiguous" % extension)
    for partner, listed, noun in _PARTNERS:
        partners = {partner_name(name, listed) for name in blocks
                    if numbered_block(name, partner) is not None}
        if partners != set(manifest.block_names(listed)):
            raise NxwrightError("the .%s %s blocks do not pair up with the listed .%s blocks"
                                % (partner, noun, listed))


def partner_name(block_name: str, extension: str) -> str:
    """Returns the name of the block of `extension` with the number of
    `block_name`: "3.gmovs" for "3.gmov" and "gmovs"."""
    return "%s.%s" % (block_name.split(".", 1)[0], extension)


def _padded_text(field: bytes) -> str:
    return field.split(b"\0")[0].decode("latin-1")


@dataclass
class ImageSource:
    """A picture's file the Editor shows, as its ".is" block holds it: the
    file as it was given, `data`; its suffix, lower-cased, as the record
    names it, such as ".jpg" (PICTURE_SUFFIXES); and the width and height
    the block's header stores."""
    width: int
    height: int
    data: bytes
    suffix: str


def parse_image_source(block: bytes) -> ImageSource:
    """Parses an ".is" block.

    Raises NxwrightError when it is cut short, or names the suffix of a file
    nxwright does not keep (PICTURE_SUFFIXES).
    """
    if len(block) < _IMAGE_SOURCE_HEADER.size:
        raise NxwrightError("image record is shorter than its header")
    _, _, header_size, width, height, _, _ = _IMAGE_SOURCE_HEADER.unpack_from(block)
    suffix = "." + block[_IMAGE_SOURCE_HEADER.size:header_size].decode("latin-1")
    if suffix not in PICTURE_SUFFIXES:
        raise NxwrightError("image record of a %s file; nxwright keeps %s files"
                            % (suffix, ", ".join(PICTURE_SUFFIXES)))
    return ImageSource(width, height, block[header_size:], suffix)


def encode_image_source(source: ImageSource) -> bytes:
    """Returns an ".is" block holding `source`, with the header the Editor
    writes, which ends with the file's suffix."""
    suffix = source.suffix[1:].encode("ascii")
    header = _IMAGE_SOURCE_HEADER.pack(b"\x0a\x64\x01\x01", 0,
                                       _IMAGE_SOURCE_HEADER.size + len(suffix), source.width,
                                       source.height, len(source.data), 0)
    return header + suffix + source.data

