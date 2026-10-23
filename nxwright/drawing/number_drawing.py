"""Drawing a number and an xfloat: each is drawn as a text component draws
its `txt`, with its `val` written out in place of the text.

`val` is the screen's 32-bit number, read signed. A number's `format` 0
writes it in decimal, 1 with its thousands separated by commas, and 2 in
hexadecimal capitals, of its 32 bits, two digits a byte, without the bytes
of zeros before the first that is not: 0 is "00", 255 "FF", and -255
"FFFFFF01". A number's `lenth`, when not 0, is how many characters the
written number has, its sign aside: fewer are padded with zeros on the left,
and more are cut to the first ones. So 42 at `lenth` 5 is "00042", -42 is
"-00042", 1234567 at `lenth` 3 is "123", and in thousands "1,2".

An xfloat writes `val` divided by 10 to the power `vvs1`, with `vvs1` digits
after the point, and none when `vvs1` is 0. `vvs0`, when not 0, is how many
digits come before the point, padded and cut as a number's `lenth` pads and
cuts. So 12345 is "123.45" at `vvs0` 0 and `vvs1` 2, "12.45" at 2 and 2,
"12" at 2 and 0; 5 is "000.005" at 3 and 3, and -5 "-0.05" at 1 and 2. The
screen works this out in 32 bits, as C would: -2147483648, which has no
positive in 32 bits, stays negative once its sign is taken off, so that at
`vvs1` 3 it is written "--2147483.-648", as the Editor's simulator wrote it.
An xfloat's `vvs1` runs from 0 to 8, and its `vvs0` from 0 to 10: the
Editor refuses more as it compiles, and the running screen refuses code
setting more (page_source._RANGES, and attribute_descriptions.toml's
`code_range`),
as the Editor's simulator showed (tests/fixtures/drawing-assumptions/,
page7).

All of these matched the Editor's simulator (tests/fixtures/value-widgets/).
"""
from nxwright.project.screen_arithmetic import divide_toward_zero, int32

_FORMAT_DECIMAL, _FORMAT_THOUSANDS, _FORMAT_HEX = 0, 1, 2


def paint_number(painter):
    """Paints a number: its value written out, as a text is drawn."""
    painter.text_component(number_text(painter.values))


def paint_xfloat(painter):
    """Paints an xfloat: its value written out with its point, as a text is
    drawn."""
    painter.text_component(xfloat_text(painter.values))


def number_text(values: dict) -> str:
    """Returns a number's `val` written as the screen writes it, by its
    `format` and `lenth`."""
    value = int32(values.get("val", 0))
    form = values.get("format", _FORMAT_DECIMAL)
    if form == _FORMAT_HEX:
        digits, sign = "%X" % (value % 2 ** 32), ""
        digits = "0" * (len(digits) % 2) + digits
    else:
        digits, sign = ("{:,}" if form == _FORMAT_THOUSANDS else "{}").format(abs(value)), \
            "-" if value < 0 else ""
    return sign + _fitted(digits, values.get("lenth", 0))


def xfloat_text(values: dict) -> str:
    """Returns an xfloat's `val` written as the screen writes it, with
    `vvs1` digits after its point and `vvs0` before it."""
    value = int32(values.get("val", 0))
    places = values.get("vvs1", 0)
    # Taking off the sign in 32 bits: -2147483648 stays as it is.
    magnitude = int32(-value) if value < 0 else value
    scale = 10 ** places
    whole = divide_toward_zero(magnitude, scale)
    text = ("-" if value < 0 else "") + _fitted(str(whole), values.get("vvs0", 0))
    if places:
        text += "." + "%0*d" % (places, magnitude - whole * scale)
    return text


def _fitted(digits: str, length: int) -> str:
    """`digits` padded with zeros on the left to `length` characters, or cut
    to the first `length` of them; as they are when `length` is 0."""
    if length <= 0:
        return digits
    return digits.rjust(length, "0")[:length]
