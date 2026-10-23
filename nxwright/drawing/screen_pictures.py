"""Pictures of what a simulation's screen shows, for an agent driving the
simulator: each drawing of the screen (testing/preview.py,
Previews.simulation_drawing) painted as the simulator's panel paints it
(editors/vscode/media/preview-model.mjs, paint and paintScreen, and
media/simulator.mjs, paintDrawing).

A page without background is drawn over what the screen showed before, as
the panel keeps it: over black after a start; when the page is entered,
over the screen as it showed then; and when it is drawn again, over what it
was drawn over before (backdrop_choice). ScreenPictures keeps the drawings
that make that screen, and paints them only when a picture is asked for. A
page without background entered over another such page keeps that page's
drawing in turn. Past _MOST_KEPT of them, the oldest drawing is let go,
unpainted, so that an app turning between such pages keeps no endless chain
of them: what lay under it then shows black, where none of the later pages
painted.

The panel paints with a browser, this module with Pillow. Where the two may
differ, this one is the one compared with the Nextion Editor's pictures
(tests/test_page_drawing.py). The two kinds of shape the panel writes in a
browser's font, "plainText", a text whose font cannot be drawn, and
"outline", a component's frame with its name, are written in Pillow's
default font: close enough to read, not the same pixels.
"""
import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from nxwright import NxwrightError
from nxwright.drawing.page_drawing import OPAQUE
from nxwright.project.pictures import read_picture
from nxwright.project.screen_colours import rgb565_to_rgb
from nxwright.project.screen_copy import FORMAT_RAW, stored_pixels

# The colour of a component's outline, and the height of its name's letters,
# as the panel draws them (OUTLINE_COLOUR in preview-model.mjs).
OUTLINE_COLOUR = (255, 64, 255, 255)
_OUTLINE_LETTERS = 11
# How many pages without background entered in turn keep their drawings
# before the oldest is let go (the module's docstring).
_MOST_KEPT = 8
# What a page without background is drawn over (backdrop_choice).
BLACK, SCREEN, SAME = "black", "screen", "same"
# A picture's colours as the screen shows them (screenColours in
# preview-model.mjs). It keeps 5 bits of red, 6 of green, and 5 of blue, and
# widens each again by repeating its top bits. The alpha does not change.
# This is a lookup table for Image.point, one band after another.
_FIVE_BITS = [(level & 0xF8) | (level >> 5) for level in range(256)]
SCREEN_COLOURS = (_FIVE_BITS + [(level & 0xFC) | (level >> 6) for level in range(256)]
                  + _FIVE_BITS + list(range(256)))
# Pillow's turns, counterclockwise, that undo a screen's turn of each rotation.
_TURNS_BACK = {90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180,
               270: Image.Transpose.ROTATE_270}


class ScreenPictures:
    """The pictures of one simulation's screen. shown() is given each drawing
    the panel would get, the one sent as a page is left included, in order;
    picture() paints the latest."""

    def __init__(self):
        self._latest = None
        # The start and entry of the latest drawing, as (start, entry).
        self._last = None

    def shown(self, drawing: dict):
        """Takes `drawing` as what the screen now shows, with what a page
        without background is drawn over (backdrop_choice). Paints
        nothing."""
        choice = backdrop_choice(self._last, drawing)
        self._last = (drawing["start"], drawing["entry"])
        if choice == SCREEN:
            under = self._latest
        elif choice == SAME:
            under = self._latest.under
        else:
            under = None
        self._latest = _Screen(drawing, under if drawing["transparent"] else None)

    def picture(self) -> bytes:
        """Returns the PNG of the latest drawing, as the panel shows it:
        dimmed by the screen's brightness, `dim`, and dark while it sleeps.
        Raises ValueError before any drawing was shown."""
        if self._latest is None:
            raise ValueError("the screen has shown nothing yet")
        drawing = self._latest.drawing
        image = self._latest.image()
        dark = darkness(drawing)
        if dark > 0:
            image = image.point([round(level * (1 - dark)) for level in range(256)] * 3)
        written = io.BytesIO()
        image.save(written, "PNG")
        return written.getvalue()


class _Screen:
    """A drawing and what it is drawn over, `under`, another _Screen or None
    for black: the screen as the panel showed it, painted once asked for
    (image). The next drawing of the same page is drawn over the same
    `under`, so painting keeps it. At most _MOST_KEPT screens lie under one:
    below them, what lay under shows black, but in a screen already painted,
    which keeps its picture as it was."""

    def __init__(self, drawing: dict, under):
        self.drawing = drawing
        self.under = under
        self._image = None
        lowest = self
        for _ in range(_MOST_KEPT):
            if lowest.under is None:
                return
            lowest = lowest.under
        lowest.under = None

    def image(self) -> Image.Image:
        """Returns the screen as an RGB image, painted the first time."""
        if self._image is None:
            under = self.under.image() if self.under is not None else None
            self._image = paint_drawing(self.drawing, under)
        return self._image


def backdrop_choice(last, drawing: dict) -> str:
    """What `drawing` is drawn over, given (start, entry) of the drawing shown
    before it, or None at first (backdropChoice in preview-model.mjs):
    BLACK, for the first drawing since the screen started, or a page with a
    background, which covers the screen; SCREEN, for a page without
    background just entered, over what the screen showed; SAME, for the page
    shown, drawn again over what it was drawn over before."""
    if last is None or drawing["start"] != last[0]:
        return BLACK
    if drawing["entry"] == last[1]:
        return SAME
    return SCREEN if drawing["transparent"] else BLACK


def darkness(drawing: dict) -> float:
    """How dark the screen shows, from 0 to 1 (darkness in
    preview-model.mjs): `dim` 80 shows every colour at 80%, and a sleeping
    screen is dark."""
    if drawing.get("asleep"):
        return 1
    return min(max((100 - drawing.get("dim", 100)) / 100, 0), 1)


def paint_drawing(drawing: dict, under: Image.Image = None) -> Image.Image:
    """Returns the page of `drawing` as an RGB image, its shapes painted as
    the panel paints them, its pictures read from its "pictureFiles". Where
    no shape lies, the page is black, or shows `under` for a page without
    background: the screen it was drawn over. A "backdrop" shape shows its
    part of `under`, or black without it.
    Each shape is laid over what is under it by its alpha, and cut at the
    page's edges. An open list may run past the screen's edge.
    A shape marked with an `aph` is laid as opaque as aph / 127 of its alpha,
    by Pillow's blend. The Nextion Editor's simulator blends it by
    under + (colour - under) * aph / 127, the change cut toward zero. The two
    differ by a level or two at most.
    A picture that cannot be read is left out, as the panel leaves it out."""
    page = Image.new("RGBA", (drawing["width"], drawing["height"]), (0, 0, 0, 255))
    backdrop = under.convert("RGBA") if under is not None and drawing["transparent"] else None
    if backdrop is not None:
        page.paste(backdrop, (0, 0))
    pictures = _Pictures(drawing.get("pictureFiles", {}))
    for shape in drawing["shapes"]:
        laid = _laid(shape, backdrop, pictures)
        if laid is None:
            continue
        aph = shape.get("aph", OPAQUE)
        if aph != OPAQUE:
            laid.putalpha(laid.getchannel("A").point(
                [round(alpha * aph / OPAQUE) for alpha in range(256)]))
        _lay(page, laid, shape["x"], shape["y"])
    return page.convert("RGB")


def _laid(shape: dict, backdrop, pictures):
    """Returns the RGBA image a shape lays at its x and y, or None for one
    the panel leaves out."""
    x, y, w, h = shape["x"], shape["y"], shape["w"], shape["h"]
    kind = shape["kind"]
    if kind == "backdrop":
        return (backdrop.crop((x, y, x + w, y + h)) if backdrop is not None
                else Image.new("RGBA", (w, h), (0, 0, 0, 255)))
    if kind == "colour":
        return Image.new("RGBA", (w, h), _rgba(shape["colour"]))
    if kind == "picture":
        picture = pictures.get(shape["picture"], card=shape.get("card", False),
                               opaque=shape.get("opaque", False))
        if picture is None:
            return None
        if shape.get("rotation"):
            # A file turned for a turned screen, turned back, from the
            # component's top left corner, and cut at its right and bottom.
            picture = _turned_back(picture, shape["rotation"])
            return picture.crop((0, 0, min(w, picture.width), min(h, picture.height)))
        # As much of the picture from (sx, sy) as it holds and the shape takes.
        sx, sy = shape["sx"], shape["sy"]
        return picture.crop((sx, sy, sx + max(min(w, picture.width - sx), 0),
                             sy + max(min(h, picture.height - sy), 0)))
    if kind == "text":
        # A picture of its own, in its own colours: a frame stored for a
        # turned screen is turned back, and every one is cut to its shape,
        # so that a frame's padding is left out (paintFrame in
        # preview-model.mjs).
        image = _turned_back(_picture_of_data(shape["image"]), shape.get("rotation", 0))
        return image.crop((0, 0, min(w, image.width), min(h, image.height)))
    if kind == "plainText":
        return _plain_text(shape)
    if kind == "outline":
        return _outline(shape)
    return None


def _plain_text(shape: dict) -> Image.Image:
    """A text whose font cannot be drawn: in an ordinary font at its font's
    height, aligned as its xcen and ycen say, cut to its rectangle."""
    w, h = shape["w"], shape["h"]
    laid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    xcen, ycen = shape.get("xcen", 0), shape.get("ycen", 0)
    across = (0, w / 2, w)[xcen] if xcen in (0, 1, 2) else 0
    down = (0, h / 2, h)[ycen] if ycen in (0, 1, 2) else 0
    anchor = "lmr"[xcen if xcen in (0, 1, 2) else 0] + "amd"[ycen if ycen in (0, 1, 2) else 0]
    ImageDraw.Draw(laid).text((across, down), shape["text"], fill=_rgba(shape["colour"]),
                              font=ImageFont.load_default(max(shape["size"], 1)), anchor=anchor)
    return laid


def _outline(shape: dict) -> Image.Image:
    """A component's frame, a pixel wide, with its name at its top left."""
    w, h = shape["w"], shape["h"]
    laid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if w > 0 and h > 0:
        draw = ImageDraw.Draw(laid)
        draw.rectangle((0, 0, w - 1, h - 1), outline=OUTLINE_COLOUR)
        draw.text((3, 3), shape["label"], fill=OUTLINE_COLOUR,
                  font=ImageFont.load_default(_OUTLINE_LETTERS))
    return laid


class _Pictures:
    """A drawing's pictures, read from its "pictureFiles" ({name: what the
    panel loads it from}, testing/preview.py, picture_file) as each is first
    painted: a project's picture in the screen's colours, flattened on white
    on a screen that keeps no alpha; an SD card's file in its own colours,
    through its mask when it has one."""

    def __init__(self, files: dict):
        self._files = files
        self._read = {}

    def get(self, name: str, card: bool, opaque: bool):
        """Returns the picture `name` as an RGBA image ready to lay, or None
        for one the drawing does not give, or that cannot be read."""
        key = (name, card, opaque)
        if key not in self._read:
            self._read[key] = self._prepared(name, card, opaque)
        return self._read[key]

    def _prepared(self, name: str, card: bool, opaque: bool):
        found = self._files.get(name)
        try:
            if found is None:
                return None
            if "data" in found:
                picture = _picture_of_data(found["data"])
            elif "path" in found:
                picture = read_picture(Path(found["path"]).read_bytes())
            else:
                return None
            if card:
                if "mask" in found:
                    picture.putalpha(_picture_of_data(found["mask"]).getchannel("A"))
                return picture
        except (OSError, NxwrightError, ValueError):
            # A file gone, damaged, or not a picture, or a mask of another
            # size: the panel leaves such a picture out, and so does this.
            return None
        if opaque:
            picture = _flattened(picture)
        return picture.point(SCREEN_COLOURS)


def _flattened(picture: Image.Image) -> Image.Image:
    """`picture` as a screen that keeps no alpha stores it: each channel
    multiplied by alpha, rounding, with white added for the transparent
    share, then 5 bits of red, 6 of green, and 5 of blue
    (screen_copy.stored_pixels), widened again; wholly opaque."""
    stored = stored_pixels(picture, FORMAT_RAW)
    widened = {colour: bytes(rgb565_to_rgb(colour) + (255,)) for colour in set(stored.colours)}
    return Image.frombytes("RGBA", picture.size,
                           b"".join(widened[colour] for colour in stored.colours))


def _rgba(colour: str) -> tuple:
    """The colour "#rrggbb" as (red, green, blue, alpha), wholly opaque."""
    return tuple(int(colour[index:index + 2], 16) for index in (1, 3, 5)) + (255,)


def _picture_of_data(url: str) -> Image.Image:
    """The picture of a "data:" URL, as an RGBA image."""
    return read_picture(base64.b64decode(url.split(",", 1)[1]))


def _lay(page: Image.Image, laid: Image.Image, x: int, y: int):
    """Lays the RGBA image `laid` over `page` at (x, y), by its alpha. The
    part of `laid` past the page's edges is left out."""
    left, top = max(x, 0), max(y, 0)
    right, bottom = min(x + laid.width, page.width), min(y + laid.height, page.height)
    if left < right and top < bottom:
        page.alpha_composite(laid, (left, top), (left - x, top - y, right - x, bottom - y))


def _turned_back(image: Image.Image, rotation: int) -> Image.Image:
    """Returns `image`, stored for a screen turned `rotation` degrees, turned
    back by as much, as the panel turns it, so that it shows upright."""
    return image.transpose(_TURNS_BACK[rotation]) if rotation else image
