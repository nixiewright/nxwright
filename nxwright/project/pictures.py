"""Pictures, through Pillow: a picture file read as an RGBA image, whatever
its kind (PNG, JPEG, BMP, GIF, and the others Pillow reads), its size read
from its file's start alone, a PNG written, and a picture file as the data
URL a webview shows.
"""
import base64
import io
from pathlib import Path

from PIL import Image, ImageMath, UnidentifiedImageError

from nxwright import NxwrightError

# The errors Pillow raises for a file it cannot read as a picture, one of
# too many pixels among them.
_UNREADABLE = (UnidentifiedImageError, OSError, ValueError, SyntaxError,
               Image.DecompressionBombError)
# The kinds of file whose several images are views of one moment, not frames
# in time: an MPO photo's, the JPEG some phones write of a 3D scene. Such a
# file is one still picture, read by its first view.
_VIEWS_OF_ONE_MOMENT = ("MPO",)
# The EXIF tag of a picture's orientation.
_ORIENTATION = 0x0112
# How Pillow decodes a PNG of 16 bits a channel in colour, which it gives at
# 8 bits a channel: its tile's raw mode.
_COLOUR_16_BITS = "RGB;16B"


def read_picture(data: bytes) -> Image.Image:
    """Returns the picture file `data` as an RGBA image: its first frame, for
    a picture of several, such as a GIF. Raises NxwrightError for data
    Pillow does not read as a picture, as it opens it (picture_problem) or
    decodes its pixels."""
    with _opened(data) as opened:
        try:
            opened.load()
            return _rgba(opened)
        except _UNREADABLE as error:
            raise NxwrightError(_refusal(error)) from None


def picture_problem(data: bytes):
    """Returns why nxwright cannot read the picture file `data`, from opening
    it alone, without decoding its pixels, in the words read_picture gives;
    or None: Pillow refuses it as it opens it, or it is a PNG of 16 bits a
    channel in colour with a colour key (_check_colour_key). A picture whose
    pixels alone are damaged opens, so it has no problem here."""
    try:
        _opened(data).close()
    except NxwrightError as error:
        return str(error)
    return None


def _opened(data: bytes) -> Image.Image:
    """Opens the picture file `data` with Pillow, reading what comes before
    its pixels. Raises NxwrightError for one Pillow refuses as it opens it,
    or that _check_colour_key refuses."""
    try:
        opened = Image.open(io.BytesIO(data))
    except _UNREADABLE as error:
        raise NxwrightError(_refusal(error)) from None
    try:
        _check_colour_key(opened)
    except NxwrightError:
        opened.close()
        raise
    return opened


def _refusal(error: Exception) -> str:
    """The words of a refusal of Pillow's: its own, but for a file of no kind
    of picture it knows, whose words name a memory buffer."""
    if isinstance(error, UnidentifiedImageError):
        return "not a picture nxwright reads: no kind of picture Pillow knows"
    return "not a picture nxwright reads: %s" % error


def _check_colour_key(opened: Image.Image):
    """Raises NxwrightError for a PNG of 16 bits a channel in colour, which
    Pillow decodes as `_COLOUR_16_BITS`, with a colour key. The Editor
    matched a key on all 16 bits, as _rgba does for a grey picture. Pillow
    gives these channels at 8 bits, which would take a colour sharing only
    the key's high bytes for the key."""
    if "transparency" in opened.info and any(tile.args == _COLOUR_16_BITS
                                             for tile in opened.tile):
        raise NxwrightError("a PNG of 16 bits a channel, with a colour key, which nxwright cannot "
                            "match on 16 bits as the Nextion Editor does: save it with 8 bits a "
                            "channel, or with an alpha channel")


def _rgba(picture: Image.Image) -> Image.Image:
    """`picture` in RGBA. A 16-bit grey picture is scaled to 8 bits first,
    as Pillow's own conversion would clip it. Its colour key, which Pillow
    keeps at 16 bits, is matched on all 16 first, as the Editor matched it."""
    if not picture.mode.startswith("I;16"):
        return picture.convert("RGBA")
    samples = picture.convert("I")
    grey = samples.point(lambda value: value / 256).convert("L").convert("RGBA")
    key = picture.info.get("transparency")
    if key is not None:
        # 0 where a sample is the key, 255 elsewhere.
        grey.putalpha(ImageMath.lambda_eval(
            lambda names: names["convert"](names["notequal"](names["samples"], key) * 255, "L"),
            samples=samples))
    return grey


def picture_size(path: Path) -> tuple:
    """Returns the (width, height) of the picture file at `path`, read from
    its start alone. Raises NxwrightError for a file that does not open, or
    is no picture Pillow reads."""
    try:
        with Image.open(path) as opened:
            return opened.size
    except _UNREADABLE as error:
        raise NxwrightError("%s: not a picture nxwright reads: %s" % (Path(path).name, error)) \
            from None


def exif_orientation(path: Path) -> int:
    """Returns the EXIF orientation of the picture file at `path`, which
    tells a viewer how to turn or flip it: 2 to 8 ask for a turn or a flip,
    and 1 is the pixels as stored, as for a file without one, or that Pillow
    does not read. nxwright, as the Editor, keeps the pixels as stored
    whatever it says."""
    try:
        with Image.open(path) as opened:
            # The EXIF block Pillow finds as it opens the file: a JPEG's, or a
            # PNG's placed before its pixels. Pillow's getexif() would decode a
            # whole PNG to look past them, and a block there is not read.
            block = opened.info.get("exif")
            if not block:
                return 1
            exif = Image.Exif()
            exif.load(block)
            return exif.get(_ORIENTATION, 1)
    except _UNREADABLE:
        return 1


def still_picture_size(path: Path):
    """Returns the (width, height) of the file at `path` when Pillow reads it
    as a still picture, decoding it. Returns None for a file that is not a
    picture Pillow reads, such as a video it knows but cannot decode, or that
    holds several frames, as an animated GIF does, which is read through to
    count them. An MPO photo's views are one still picture, its first view's
    size. Raises NxwrightError for a file that cannot be read."""
    path = Path(path)
    try:
        file = path.open("rb")
    except OSError as error:
        raise NxwrightError("%s cannot be read: %s" % (path, error.strerror or error)) from None
    with file:
        try:
            with Image.open(file) as opened:
                several = getattr(opened, "n_frames", 1) != 1
                if several and opened.format not in _VIEWS_OF_ONE_MOMENT:
                    return None
                opened.load()
                return opened.size
        except _UNREADABLE:
            return None


def write_png(width: int, height: int, rgba: bytes) -> bytes:
    """Returns the PNG file of a picture `width` by `height`, whose pixels
    `rgba` holds as 4 bytes each, red, green, blue, and alpha, row by row
    from the top-left corner. Raises ValueError when `rgba` holds another
    number of bytes."""
    if len(rgba) != width * height * 4:
        raise ValueError("%d bytes do not make a picture %d by %d" % (len(rgba), width, height))
    out = io.BytesIO()
    Image.frombytes("RGBA", (width, height), rgba).save(out, "PNG")
    return out.getvalue()


def data_url(picture: bytes, media_type: str = "image/png") -> str:
    """Returns a picture file, a PNG one by default, as a data: URL, as a
    webview shows a picture sent to it."""
    return "data:%s;base64,%s" % (media_type, base64.b64encode(picture).decode("ascii"))
