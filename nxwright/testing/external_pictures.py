"""What an external picture shows for the file at its `path`.

A real screen does not show every kind of picture file, and the two series
that have external pictures differ. An NX8048P070, of the Intelligent
series, and an NX4848E040, of the Edge series, showed this:

    the file            Intelligent         Edge
    a .xi file          the picture         the picture
    a JPEG              the picture         the error marker
    another file        the error marker    nothing

A .xi file is a picture file in the form PictureBox writes
(media_files.card_picture_file). nxwright decides the kind of a file from
its bytes, whatever the file's name, because the NX4848E040 did.

The error marker is the text "Show Picture Error!" in red on blue, from the
component's top left. nxwright draws the text in a font of its own, so the
letters do not look like the screen's.
"""
import functools
import io
import math

from PIL import Image, ImageDraw, ImageFont

from nxwright import NxwrightError
from nxwright.project.media_files import is_card_picture, read_card_picture
from nxwright.project.pictures import read_picture
from nxwright.project.truetype import NOTO_SANS

# The kinds of file, by their bytes (file_kind).
XI = ".xi"
JPEG = "JPEG"
DAMAGED = "damaged"     # a .xi file or a JPEG that cannot be read
OTHER = "other"

# What an external picture shows for a file that is there (shown).
PICTURE = "picture"
MARKER = "marker"
NOTHING = "nothing"

# The series letter of the Edge series (screen_models.Model.series). The only
# other series with external pictures is the Intelligent, "P".
_EDGE = "E"

_JPEG_START = b"\xff\xd8"

MARKER_TEXT = "Show Picture Error!"
_MARKER_LINE = 16       # the height of a line of the marker, in pixels
_MARKER_FONT_SIZE = 14
_MARKER_BASELINE = 13   # where a line's text sits, in pixels below the line's top
_MARKER_MARGIN = 1      # the blue at each end of a line, in pixels
_RED, _BLUE = (255, 0, 0, 255), (0, 0, 255, 255)


def file_kind(data: bytes) -> str:
    """Returns the kind of the file whose bytes are `data`: XI, JPEG,
    DAMAGED for a file that starts like a .xi file or a JPEG and cannot be
    read, or OTHER."""
    try:
        if is_card_picture(data):
            read_card_picture(data)
            return XI
        if data.startswith(_JPEG_START):
            read_picture(data)
            return JPEG
    except (NxwrightError, OSError, ValueError):
        return DAMAGED
    return OTHER


def shown(kind: str, series) -> str:
    """Returns PICTURE, MARKER, or NOTHING: what an external picture shows
    for a file of `kind` (file_kind) on a screen whose series letter is
    `series`, such as "P". If nxwright does not know the screen, `series`
    is None, and the result is the same as for the Intelligent series.

    No screen was tried with a damaged file. nxwright assumes that a
    screen which starts to read a picture, and fails, shows the marker."""
    if kind == XI:
        return PICTURE
    if kind == DAMAGED:
        return MARKER
    if series == _EDGE:
        return MARKER if kind == JPEG else NOTHING
    return PICTURE if kind == JPEG else MARKER


def kinds_shown(series) -> str:
    """Returns the part of the simulator's log line that lists the kinds
    of file a screen of the series `series` shows, and gives the command
    that makes a .xi file."""
    if series == _EDGE:
        return ("this screen shows only .xi files. `nxwright sd-picture` converts a picture "
                "to a .xi file.")
    return ("this screen shows only JPEG and .xi files. `nxwright sd-picture` converts a "
            "picture to a .xi file.")


@functools.lru_cache(maxsize=64)
def error_marker(width: int, height: int) -> bytes:
    """Returns the error marker for a component of `width` by `height`
    pixels, as a PNG picture. The marker is MARKER_TEXT in red on blue,
    wrapped at the component's width, in lines _MARKER_LINE pixels high.
    The blue of each line is as wide as its text, and the picture is
    transparent beside a shorter line. A line that would start below the
    component is left out. The last line may reach below the component,
    and the component then cuts it."""
    font = ImageFont.truetype(str(NOTO_SANS), _MARKER_FONT_SIZE)
    lines = _wrapped(MARKER_TEXT, font, width - 2 * _MARKER_MARGIN)
    lines = lines[:max(1, -(-height // _MARKER_LINE))]
    widths = [_text_width(line, font) + 2 * _MARKER_MARGIN for line in lines]
    picture = Image.new("RGBA", (max(widths), len(lines) * _MARKER_LINE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(picture)
    for number, (line, line_width) in enumerate(zip(lines, widths)):
        top = number * _MARKER_LINE
        draw.rectangle((0, top, line_width - 1, top + _MARKER_LINE - 1), fill=_BLUE)
        draw.text((_MARKER_MARGIN, top + _MARKER_BASELINE), line, font=font, fill=_RED,
                  anchor="ls")
    file = io.BytesIO()
    picture.save(file, "PNG")
    return file.getvalue()


def _wrapped(text: str, font, width: int) -> list:
    """Returns `text` cut into lines that each fit in `width` pixels in
    `font`. A line has at least one character, however narrow the width."""
    lines, line = [], ""
    for character in text:
        if line and _text_width(line + character, font) > width:
            lines.append(line)
            line = ""
        line += character
    return lines + [line]


def _text_width(text: str, font) -> int:
    """Returns the width of `text` in `font`, in whole pixels."""
    return math.ceil(font.getlength(text))
