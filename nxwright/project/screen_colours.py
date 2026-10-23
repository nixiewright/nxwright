"""The colours a screen holds. A page file stores a colour as RGB565: 5
bits of red, 6 of green, and 5 of blue. nxwright's files write it as
"#rrggbb" (rgb565_to_hex, hex_to_rgb565), and the drawing paints it as
(red, green, blue) (rgb565_to_rgb)."""
import re

# A colour as nxwright's files write it: "#rrggbb".
COLOUR_TEXT = re.compile(r"#[0-9a-fA-F]{6}")


def rgb565_to_rgb(colour: int) -> tuple:
    """Returns an RGB565 colour as (red, green, blue), each channel scaled to
    the full range from 0 to 255."""
    red, green, blue = colour >> 11 & 31, colour >> 5 & 63, colour & 31
    return red << 3 | red >> 2, green << 2 | green >> 4, blue << 3 | blue >> 2


def rgb565_to_hex(colour: int) -> str:
    """Returns an RGB565 colour as "#rrggbb", as rgb565_to_rgb scales it.
    hex_to_rgb565 gives back the exact colour."""
    return "#%02x%02x%02x" % rgb565_to_rgb(colour)


def nearest_screen_colour(text: str) -> str:
    """Returns the colour the screen holds that is nearest the "#rrggbb"
    colour `text`, as rgb565_to_hex writes it, so that the build stores it
    unchanged. Each channel takes the nearest of its levels as
    rgb565_to_rgb writes them, the lower of two equally near. A text that
    is no colour comes back as it is, for the build's check to refuse."""
    if not COLOUR_TEXT.fullmatch(text):
        return text
    picked = [int(text[i:i + 2], 16) for i in (1, 3, 5)]
    nearest = 0
    for channel, shift, count in ((0, 11, 32), (1, 5, 64), (2, 0, 32)):
        levels = [rgb565_to_rgb(level << shift)[channel] for level in range(count)]
        level = min(range(count), key=lambda index: (abs(levels[index] - picked[channel]), index))
        nearest |= level << shift
    return rgb565_to_hex(nearest)


def hex_to_rgb565(text: str) -> int:
    """Returns a "#rrggbb" colour as RGB565, keeping each channel's top bits."""
    red, green, blue = (int(text[i:i + 2], 16) for i in (1, 3, 5))
    return (red >> 3) << 11 | (green >> 2) << 5 | blue >> 3
