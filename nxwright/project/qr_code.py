"""QR codes as the Editor makes them for a QR code component: the grid of
modules a text makes, by the QR code standard, ISO/IEC 18004, through the
qrcode library, given the Editor's choices.

A QR code is a square of dark and light modules. Its version, 1 to 40, sets
its size: version v is 4v + 17 modules wide. It holds its text as a list of
segments, each in one mode: numeric, digits three to 10 bits; alphanumeric,
the digits, the capitals, and ` $%*+-./:`, two to 11 bits; or byte, any byte
in 8 bits.

The Editor's choices, worked out from the codes its simulator drew for
texts nxwright gave it:
  - error correction level L, the lowest, and mask 0, always, where other
    encoders pick the mask that scores best;
  - the smallest version that holds the text;
  - the text's segments split to cost the fewest bits, as the Editor's
    split does for most texts (`segments`): nxwright splits the text, and
    qrcode takes the segments as they are;
  - each byte the text's character in the project's encoding, with no
    marker saying which encoding.
"""
from qrcode import QRCode
from qrcode.constants import ERROR_CORRECT_L
from qrcode.exceptions import DataOverflowError
from qrcode.util import MODE_8BIT_BYTE, MODE_ALPHA_NUM, MODE_NUMBER, QRData

from nxwright import NxwrightError

NUMERIC, ALPHANUMERIC, BYTE = "numeric", "alphanumeric", "byte"
# The characters of the alphanumeric mode.
ALPHANUMERIC_CHARACTERS = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"
# Each mode as qrcode names it.
_QRCODE_MODES = {NUMERIC: MODE_NUMBER, ALPHANUMERIC: MODE_ALPHA_NUM, BYTE: MODE_8BIT_BYTE}
# Each mode's period: the characters its bits come in groups of.
_PERIODS = {BYTE: 1, ALPHANUMERIC: 2, NUMERIC: 3}
# Among splits of as many bits whose last segments start at one place, the
# narrower mode first.
_RANK = {NUMERIC: 0, ALPHANUMERIC: 1, BYTE: 2}


def qr_modules(data: bytes) -> list:
    """Returns the QR code of `data`, as rows of modules from the top, each
    True for dark. It is the Editor's code but for the few texts the Editor
    splits otherwise (`segments`). For an empty text, it is a code holding
    no text, where the Editor draws none. Raises NxwrightError when version
    40 cannot hold `data`."""
    # The split depends on the version, whose count fields widen at 10 and
    # 27, so each version is tried with its own, the smallest first.
    for version in range(1, 41):
        code = QRCode(version=version, error_correction=ERROR_CORRECT_L, mask_pattern=0, border=0)
        for mode, chunk in segments(data, version):
            code.add_data(QRData(chunk, mode=_QRCODE_MODES[mode], check_data=False))
        try:
            code.make(fit=False)
        except DataOverflowError:
            continue
        return [list(row) for row in code.modules]
    raise NxwrightError("a QR code cannot hold %d bytes" % len(data))


def segments(data: bytes, version: int) -> list:
    """Returns `data` split into (mode, bytes) segments for a code of
    `version`: the split costing the fewest bits. Where splits tie, the one
    whose last segment starts latest wins, and at one start, the narrowest
    mode; the part before that segment is split by the same rule. So
    "abc123", 60 bits either way, is byte "abc" then numeric "123", as the
    Editor splits it.

    The Editor's own rule is not known. This one makes its splits for most
    texts, but not all: the Editor makes "ca-85y4dC2224-98" byte
    "ca-85y4dC" then alphanumeric "2224-98", 3 bits more than byte
    "ca-85y4d" then alphanumeric "C2224-98", which this rule makes. A
    reader reads the same text from both codes."""
    headers = {mode: 4 + _count_bits(mode, version) for mode in _PERIODS}
    # The cheapest split of each beginning of `data`: (bits, its last
    # segment's start and mode).
    best = [(0, None)]
    # The segments that can still grow by the next character: by mode, and
    # by their start's place in the mode's period, (bits before the segment
    # with its header, start). The bits of two such segments grow alike, so
    # the cheaper stays the cheaper, and only it is kept.
    growing = {}
    for end in range(1, len(data) + 1):
        start = end - 1
        for mode, period in _PERIODS.items():
            if not _holds(mode, data[start]):
                for key in [key for key in growing if key[0] == mode]:
                    del growing[key]
                continue
            key = (mode, start % period)
            base = best[start][0] + headers[mode]
            kept = growing.get(key)
            # As many bits keeps the later start.
            if kept is None or base + _data_bits(mode, 1) <= kept[0] + _data_bits(
                    mode, end - kept[1]):
                growing[key] = (base, start)
        endings = [(base + _data_bits(mode, end - first), first, mode)
                   for (mode, _), (base, first) in growing.items()]
        bits, first, mode = min(endings, key=lambda ending: (ending[0], -ending[1],
                                                             _RANK[ending[2]]))
        best.append((bits, (first, mode)))
    found, end = [], len(data)
    while end > 0:
        start, mode = best[end][1]
        found.append((mode, data[start:end]))
        end = start
    return found[::-1]


def _mode_of(byte: int) -> str:
    if 0x30 <= byte <= 0x39:
        return NUMERIC
    return ALPHANUMERIC if byte in ALPHANUMERIC_CHARACTERS else BYTE


def _holds(mode: str, byte: int) -> bool:
    """Whether a segment of `mode` can hold `byte`."""
    narrowest = _mode_of(byte)
    return mode == BYTE or narrowest == mode or (mode == ALPHANUMERIC and narrowest == NUMERIC)


def _count_bits(mode: str, version: int) -> int:
    """The bits of a segment's character count, by mode and version."""
    band = 0 if version <= 9 else 1 if version <= 26 else 2
    return {NUMERIC: (10, 12, 14), ALPHANUMERIC: (9, 11, 13), BYTE: (8, 16, 16)}[mode][band]


def _data_bits(mode: str, count: int) -> int:
    """The bits of `count` characters in a segment of `mode`, its header aside."""
    if mode == NUMERIC:
        return 10 * (count // 3) + (0, 4, 7)[count % 3]
    if mode == ALPHANUMERIC:
        return 11 * (count // 2) + 6 * (count % 2)
    return 8 * count
