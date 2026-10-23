"""Drawing a QR code component: a square of `bco`, its code, and its logo,
as page_drawing.py's opening comment says.
"""
import functools

from nxwright import NxwrightError
from nxwright.drawing.drawing_shared import NO_RESOURCE, box_of
from nxwright.project.device_settings import TextCodec
from nxwright.project.pictures import data_url, write_png
from nxwright.project.qr_code import qr_modules
from nxwright.project.screen_colours import rgb565_to_hex, rgb565_to_rgb


# How much narrower than a QR code's code each side of its logo must be for
# the logo to be drawn.
LOGO_MARGIN = 4


@functools.lru_cache(maxsize=64)
def _qr_picture(data: bytes, side: int, colour: tuple):
    """Returns the PNG of the QR code of `data`, `side` pixels wide and high,
    its dark modules in `colour` and its light ones clear; or None when a
    module would be less than a pixel, as the Editor's simulator then draws
    no code. Module i of n covers the pixels from ceil(i * side / n) up to
    ceil((i + 1) * side / n), across and down. The run of dark modules in
    the code's last column that ends at its bottom right corner is left
    without the code's last column of pixels, as the Editor's simulator drew
    it at each size tried. Raises NxwrightError when no QR code can hold
    `data`."""
    modules = qr_modules(data)
    count = len(modules)
    if side < count:
        return None
    # The module each pixel shows, across or down.
    module_of = [pixel * count // side for pixel in range(side)]
    dark, clear = bytes((*colour, 255)), bytes(4)
    rows = [b"".join(dark if row[module] else clear for module in module_of) for row in modules]
    rgba = bytearray(b"".join(rows[module] for module in module_of))
    last = count - 1
    if modules[last][last]:
        top = last
        while top > 0 and modules[top - 1][last]:
            top -= 1
        for pixel_row in range(-(-top * side // count), side):
            end = (pixel_row + 1) * side * 4
            rgba[end - 4:end] = clear
    return write_png(side, side, bytes(rgba))


def paint_qr_code(painter):
    """Paints a QR code component: a square of `bco`, `w` pixels a side,
    its code, and its logo, as page_drawing.py's opening comment says."""
    values = painter.values
    x, y, w = painter.box["x"], painter.box["y"], painter.box["w"]
    painter.add("colour", box_of(x, y, w, w), colour=rgb565_to_hex(values.get("bco", 0)))
    dis = values.get("dis", 0)
    side = w - 2 * dis
    if side <= 0 or not painter.too_large(side, side, "its code"):
        colour = rgb565_to_rgb(values.get("pco", 0))
        try:
            data = TextCodec(painter.resources.encoding).encode_keeping_bytes(
                values.get("txt", ""), "its txt")
            # The Editor's simulator draws no code for an empty text.
            picture = _qr_picture(data, side, colour) if data else None
        except NxwrightError as error:
            painter.note("its code is not drawn: %s" % error)
            picture = None
        if picture is not None:
            painter.add("text", box_of(x + dis, y + dis, side, side), image=data_url(picture))
    if values.get("sta") == 1:
        _logo(painter, w, side)


def _logo(painter, width: int, code_width: int):
    """Paints a QR code's logo, the picture `pic`, at its own size, in the
    middle of the square `width` pixels wide, its corner rounded down;
    none when a side of it passes the code's width, `code_width`, less
    LOGO_MARGIN."""
    picture_id = painter.values.get("pic", NO_RESOURCE)
    size = None if picture_id == NO_RESOURCE else painter.resources.picture_size(picture_id)
    if size is None:
        painter.picture("pic", (0, 0))     # notes a picture the folder lacks
        return
    logo_width, logo_height = size
    if max(logo_width, logo_height) > code_width - LOGO_MARGIN:
        return
    painter.picture("pic", (0, 0), box_of(painter.box["x"] + (width - logo_width) // 2,
                                          painter.box["y"] + (width - logo_height) // 2,
                                          logo_width, logo_height))
