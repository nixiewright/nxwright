"""nxwright's own keyboard pages, which a component's `key` opens
(docs/commands.md, keyboard): the full keyboard, keybdA, opened by `key` 1; the
numeric keypad, keybdB, by 2; the speed dial, keybdC, by 3; and the
Chinese keyboard, keybdAP, by 4.

A keyboard keeps the interface of the Editor's stock keyboards, so that the
screen, a project's code, and a caller work with it as with the stock page:
  - the page is marked in its header as the system page whose number is
    the caller's `key`;
  - it has two variables of global scope, loadpageid and loadcmpid, which
    the screen sets to the caller's page number and component ID before it
    opens the page;
  - on load, it reads the caller, p[loadpageid.val].b[loadcmpid.val]: a
    number (type 54) as its digits, an xfloat (59) as its digits with vvs1
    of them after a point, and any other as its txt, up to its txt_maxl
    bytes. A text (116) shows hidden, as the caller does, by its pw. The
    keyboard holds 100 bytes at most: a longer text is cut to its first 100,
    and OK writes it back so, as the stock keyboards cut theirs at 32. A
    number takes 11 bytes at most: a sign and ten digits, or eleven digits.
    One typed past the screen's 32-bit range, as 9999999999, wraps when OK
    writes it back;
  - OK writes the text back by the same types, then goes back to the caller
    with `page loadpageid.val`; cancel goes back without writing.

The full keyboard fills the page. The keypad and the speed dial are panels in
the middle of a page without background, as the stock ones are, so that the
caller's page shows around them. Each lays its keys out on a grid sized to
the page, in the colours of nxwright's demo (examples/thermostat). Their
labels, and the text typed, are in one font of Noto Sans, at the largest
height whose labels fit the keys.

The full keyboard's mode key changes its letter keys between small letters,
capitals, and numbers and signs. The speed dial's group keys, such as "abc",
show their characters on four choice keys, and a tap on one types it; its
mode key changes the groups to capitals, then to digits, which type at once.

The Chinese keyboard is laid out as the full keyboard, with a row above its
letters showing the pinyin syllable typed and six of its candidate
characters, which "<" and ">" page through. In its pinyin mode, a letter adds
to the syllable, and the screen gives its candidates (pa_q and pa_txt,
testing/pinyin_table.py); a tap on one types it. Its other modes type small
letters, capitals, and numbers and signs. Its font is a gb2312 font of the
folder's, or one drawn from a Chinese typeface, as Noto Sans has no Chinese
characters, so its height comes from that font (chinese_font_height).

The code is in the Editor's own language, and reads alike in nxlang: each
statement has at most one operator, so that the Editor's order, left to
right, and nxlang's agree, and no statement uses a form only one of them
has. A key passes its character to the hidden hotspot `typing`, whose
Touch Press event types it, so that typing is written once.
"""
from dataclasses import dataclass
import math

from nxwright.project.device_settings import TextCodec
from nxwright.project.font_drawing import draw_font_block, lacking_characters
from nxwright.project.truetype import noto_sans
from nxwright.project.zi_font import ONE_BYTE_ENCODINGS, UTF8, text_codes
from nxwright.source.page_source import page_file_text

# The pages, by the names SYSTEM_PAGES gives the keyboards they are.
KEYBOARD_PAGES = {"keyboard": "keybdA", "keypad": "keybdB", "speed-dial": "keybdC",
                  "chinese-input": "keybdAP"}
# The Chinese keyboard, whose font is not drawn from Noto Sans.
CHINESE_INPUT = "chinese-input"
# The demo's colours: the page, a panel, an edge, a key, a key pressed, the
# accent, and text.
_BACKGROUND = "#0d1116"
_PANEL = "#12161d"
_EDGE = "#232a35"
_KEY = "#212833"
_KEY_PRESSED = "#354050"
_ACCENT = "#ff8a45"
_TEXT = "#eff3f7"
# The most bytes a keyboard holds of a caller's text. Each byte takes the
# screen's memory, twice: in the text typed and in the field showing it.
TEXT_CAPACITY = 100
# The most characters of a number or an xfloat: a sign, ten digits, a point.
_NUMBER_CAPACITY = 12
# The heights of a keyboard's font. nxwright draws fonts from 12 pixels
# (font_drawing.py), but a keyboard's stays at 16 at least, so that its keys
# stay legible on the smallest screens.
_LOWEST_FONT, _HIGHEST_FONT = 16, 254
# The characters of a keyboard's font in utf-8: those of iso-8859-1, U+0000
# to U+00FF, as `nxwright font` draws by default, in a table of them alone.
UTF8_CHARACTERS = range(0x100)

# The full keyboard's letter keys, row by row, in each of its modes: small
# letters, capitals, and numbers and signs. The mode key shows the mode it
# changes to.
_LETTERS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
_KEYBOARD_MODES = (_LETTERS, tuple(row.upper() for row in _LETTERS),
                   ("1234567890", "@#$%&*-+=", "()/:;?!"))
_MODE_LABELS = ("ABC", "123", "abc")
# The speed dial's group keys in each of its modes: small letters, capitals,
# and digits; and its space key's character in each.
_GROUPS = ("abc", "def", "ghi", "jkl", "mno", "pqrs", "tuv", "wxyz", ".,-@")
_DIAL_MODES = (_GROUPS, tuple(group.upper() for group in _GROUPS),
               tuple("123456789"))
_DIAL_SPACES = (" ", " ", "0")
_CHOICES = 4
_DIGITS_MODE = 2
# The Chinese keyboard's letter keys in each of its modes: pinyin, typed
# into the syllable, small letters, capitals, and numbers and signs; the
# mode key's label in each, the mode it changes to; how many candidates it
# shows at a time; and the most letters of a syllable, as zhuang's six.
_CHINESE_MODES = (_LETTERS,) + _KEYBOARD_MODES
_CHINESE_MODE_LABELS = ("abc", "ABC", "123", "\u4e2d")
_CANDIDATES = 6
_SYLLABLE_CAPACITY = 6
# The Chinese keyboard's font is at most this tall: a font of every gb2312
# character is large, about 1.2 MB at 24 pixels.
_HIGHEST_CHINESE_FONT = 24
# The texts the Chinese keyboard's candidate keys and syllable show at the
# widest: a Chinese character, and the longest syllable.
_CANDIDATE_SAMPLE = "\u4e2d"
_LONGEST_SYLLABLE = "zhuang"


@dataclass(frozen=True)
class Key:
    """A key: its component's name, its place in the page, its label,
    whether it types its label, and its colours, idle and pressed."""
    name: str
    x: int
    y: int
    w: int
    h: int
    label: str
    types: bool = True
    colour: str = _KEY
    pressed: str = _KEY_PRESSED
    text_colour: str = _TEXT


@dataclass(frozen=True)
class Keyboard:
    """A keyboard page: its name, the text of its page file and of its code
    file, and the font its page names, by name and height."""
    page: str
    page_toml: str
    code: str
    font_name: str
    font_height: int


def keyboard(kind: str, width: int, height: int, font: tuple = None) -> Keyboard:
    """Returns the keyboard of `kind`, a name of KEYBOARD_PAGES, laid out
    for a page `width` by `height` pixels: the screen's size at the project's
    rotation. The Chinese keyboard takes its font, (name, height), as
    `font`; the others draw theirs from Noto Sans, at the height their
    labels fit."""
    if kind == CHINESE_INPUT:
        return _chinese_keyboard(width, height, *font)
    makers = {"keyboard": _full_keyboard, "keypad": _keypad, "speed-dial": _speed_dial}
    return makers[kind](width, height)


def chinese_font_height(width: int, height: int, width_of, capped: bool = True) -> int:
    """Returns the largest height of the Chinese keyboard's font whose labels
    fit its keys, laid out for a page `width` by `height` pixels, from
    _LOWEST_FONT, and when `capped` to _HIGHEST_CHINESE_FONT, as for a font
    nxwright draws. `width_of(text, height)` says how wide a text is in the
    font at a height (typeface_widths, font_widths)."""
    grid, keys, field = _chinese_layout(width, height)
    fitting = _fitting_font_height(keys + [field], _chinese_texts(keys), width_of)
    return min(_HIGHEST_CHINESE_FONT, fitting) if capped else fitting


def chinese_label_characters() -> str:
    """Returns the characters the Chinese keyboard's keys show in any mode,
    each once, but the space and the candidates: those its font must draw."""
    # The labels are the same at any size.
    keys = _chinese_layout(800, 480)[1]
    texts = [key.label for key in keys] + list(_CHINESE_MODE_LABELS)
    texts += [letters for mode in _CHINESE_MODES for letters in mode]
    return "".join(dict.fromkeys(character for text in texts for character in text
                                 if character != " "))


def typeface_widths(typeface):
    """Returns width_of(text, height) for a typeface file (truetype.py): a
    text's width in a font drawn from it at a height, as draw_font draws
    its advances. A character the file lacks counts as wide as the font is
    tall, as a gb2312 font draws one empty."""
    span = typeface.ascender - typeface.descender

    def width_of(text: str, height: int) -> int:
        widths = [height if glyph is None else round(typeface.advance(glyph) * height / span)
                  for glyph in map(typeface.glyph_of, text)]
        return sum(widths)
    return width_of


def font_widths(font, encoding: str):
    """Returns width_of(text, height) for a font (zi_font.Font) whose texts
    are in `encoding`: a text's width at the font's height, and at another
    in proportion. A character the font lacks counts as wide as the font is
    tall."""
    codec = TextCodec(encoding).codec_name

    def width_of(text: str, height: int) -> int:
        codes = text_codes(text.encode(codec), font.encoding)
        advances = sum(font.characters[code].advance if code in font.characters
                       else font.height for code in codes)
        return math.ceil(advances * height / font.height)
    return width_of


def font_name(height: int) -> str:
    """Returns the name of the keyboards' font of `height` pixels, as the
    demo names its fonts: NotoSans24."""
    return "NotoSans%d" % height


def noto_sans_covers(encoding: str) -> bool:
    """Whether Noto Sans has every character of `encoding`, a one-byte
    encoding. Those it lacks a character of are the ones whose keyboards
    took an iso-8859-1 font before nxwright drew one-byte fonts with a gap,
    as folders made then still hold (resource_adding.encodings_taken)."""
    return encoding in ONE_BYTE_ENCODINGS and not lacking_characters(noto_sans(), encoding)


def keyboard_font(page: Keyboard, rotation: int, project_encoding: str) -> bytes:
    """Returns the font block of the font a keyboard's page names, drawn from
    Noto Sans, turned to `rotation`, in the project's encoding,
    `project_encoding`: in utf-8, of UTF8_CHARACTERS; in an encoding whose
    characters Noto Sans lacks some of, without them, or in a two-byte
    encoding with them empty (font_drawing.drawn_codes)."""
    return draw_font_block(page.font_name, noto_sans(), page.font_height, project_encoding,
                           rotation,
                           characters=UTF8_CHARACTERS if project_encoding == UTF8 else None)


@dataclass(frozen=True)
class _Grid:
    """Rows of keys in a rectangle: `columns` units across and `rows` rows
    down, with `gap` pixels between keys."""
    left: int
    top: int
    width: int
    height: int
    columns: int
    rows: int
    gap: int

    def key(self, row: int, start: float, span: float, name: str, label: str,
            **keywords) -> Key:
        """Returns the key `span` units wide from unit `start` of `row`."""
        unit = (self.width + self.gap) / self.columns
        row_height = (self.height + self.gap) / self.rows
        left = self.left + round(start * unit)
        right = self.left + round((start + span) * unit) - self.gap
        top = self.top + round(row * row_height)
        bottom = self.top + round((row + 1) * row_height) - self.gap
        return Key(name, left, top, right - left, bottom - top, label, **keywords)


def _spacing(width: int, height: int) -> tuple:
    """Returns the margin around a keyboard and the gap between its keys."""
    return max(2, min(width, height) // 50), max(2, min(width, height) // 80)


def _full_keyboard(width: int, height: int) -> Keyboard:
    """The full keyboard, keybdA: the text and cancel above four rows of
    keys, filling the page."""
    margin, gap = _spacing(width, height)
    grid = _Grid(margin, margin, width - 2 * margin, height - 2 * margin, 10, 5, gap)
    keys = []
    for row, (letters, start) in enumerate(zip(_LETTERS, (0, 0.5, 1.5))):
        for column, letter in enumerate(letters):
            keys.append(grid.key(row + 1, start + column, 1, _letter_key(row, column), letter))
    keys += [grid.key(3, 0, 1.5, "mode", _MODE_LABELS[0], types=False),
             grid.key(3, 8.5, 1.5, "back", "Del", types=False),
             grid.key(4, 0, 1, "comma", ","),
             grid.key(4, 1, 6, "space", " "),
             grid.key(4, 7, 1, "period", "."),
             _ok_key(grid, 4, 8, 2),
             grid.key(0, 8.5, 1.5, "cancel", "X", types=False)]
    field = grid.key(0, 0, 8.5, "field", "", types=False)
    letter_keys = [key for key in keys if key.name.startswith("key")]
    mode_key = next(key for key in keys if key.name == "mode")
    texts = [(character, min(key.w for key in letter_keys))
             for mode in _KEYBOARD_MODES for row in mode for character in row]
    texts += [(label, mode_key.w) for label in _MODE_LABELS]
    events = [_load_event("keybdA"), _keyboard_mode_event()]
    return _page("keybdA", "keyboard", width, height, None, field, _PANEL, keys, texts, events)


def _keypad(width: int, height: int) -> Keyboard:
    """The numeric keypad, keybdB: a panel holding the text and cancel above
    digits, a minus sign, a point, delete, and OK."""
    panel, grid = _panel_grid(width, height, 3, 6, 0.7)
    keys = [grid.key(0, 2, 1, "cancel", "X", types=False)]
    for row, characters in enumerate(("123", "456", "789", "-0.")):
        for column, character in enumerate(characters):
            keys.append(grid.key(row + 1, column, 1, _keypad_key_names()[character], character))
    keys += [grid.key(5, 0, 1, "back", "Del", types=False), _ok_key(grid, 5, 1, 2)]
    field = grid.key(0, 0, 2, "field", "", types=False)
    return _page("keybdB", "keypad", width, height, panel, field, _BACKGROUND, keys, [],
                 [_load_event("keybdB")])


def _keypad_key_names() -> dict:
    """The keypad's keys' names, by the character each types."""
    names = {digit: "digit" + digit for digit in "0123456789"}
    return dict(names, **{"-": "minus", ".": "point"})


def _speed_dial(width: int, height: int) -> Keyboard:
    """The speed dial, keybdC: a panel holding the text and cancel, four
    choice keys, nine group keys, the mode key, space, delete, and OK."""
    panel, grid = _panel_grid(width, height, 12, 7, 0.8)
    keys = [grid.key(0, 9, 3, "cancel", "X", types=False)]
    keys += [grid.key(1, 3 * index, 3, "choice%d" % (index + 1), "") for index in range(_CHOICES)]
    for index, group in enumerate(_GROUPS):
        keys.append(grid.key(2 + index // 3, 4 * (index % 3), 4, "group%d" % (index + 1), group,
                             types=False))
    keys += [grid.key(5, 0, 4, "mode", _MODE_LABELS[0], types=False),
             grid.key(5, 4, 4, "space", " "),
             grid.key(5, 8, 4, "back", "Del", types=False),
             _ok_key(grid, 6, 0, 12)]
    field = grid.key(0, 0, 9, "field", "", types=False)
    choice = next(key for key in keys if key.name == "choice1")
    group = next(key for key in keys if key.name == "group1")
    mode_key = next(key for key in keys if key.name == "mode")
    texts = [(character, choice.w) for mode in _DIAL_MODES for labels in mode
             for character in labels]
    texts += [(label, group.w) for mode in _DIAL_MODES for label in mode]
    texts += [(label, mode_key.w) for label in _MODE_LABELS]
    events = [_load_event("keybdC"), _dial_mode_event()]
    events += [_group_event(key.name) for key in keys if key.name.startswith("group")]
    return _page("keybdC", "speed-dial", width, height, panel, field, _BACKGROUND, keys, texts,
                 events)


def _panel_grid(width: int, height: int, columns: int, rows: int, aspect: float) -> tuple:
    """Returns the panel of a keyboard shown over its caller's page,
    (x, y, w, h), in the middle of the page, `aspect` times as wide as it is
    high at most; and the grid of its keys, inside it."""
    margin, gap = _spacing(width, height)
    panel_height = (height - 2 * margin) * 9 // 10
    panel_width = min(width - 2 * margin, round(panel_height * aspect))
    x, y = (width - panel_width) // 2, (height - panel_height) // 2
    grid = _Grid(x + gap, y + gap, panel_width - 2 * gap, panel_height - 2 * gap, columns, rows,
                 gap)
    return (x, y, panel_width, panel_height), grid


def _ok_key(grid: _Grid, row: int, start: float, span: float) -> Key:
    return grid.key(row, start, span, "ok", "OK", types=False, colour=_ACCENT,
                    pressed=_KEY_PRESSED, text_colour=_BACKGROUND)


def _letter_key(row: int, column: int) -> str:
    """Returns the name of the full keyboard's letter key at `row` and
    `column`, counted from 0: key1_1 is q, in the first row and column."""
    return "key%d_%d" % (row + 1, column + 1)


def _page(page: str, system_page: str, width: int, height: int, panel, field: Key,
          field_colour: str, keys: list, texts: list, events: list) -> Keyboard:
    """Returns a keyboard: its page file, its code, and its font, whose
    height fits each key's label, and `texts`, [(text, width)], the other
    labels its keys show."""
    height_of_font = _fitting_font_height(keys + [field],
                                          texts + [(key.label, key.w) for key in keys])
    name = font_name(height_of_font)
    code_events = events + [_typing_event(), _ok_event(), _cancel_event(), _back_event()]
    code_events += ["on %s.up:\n  pending.txt=%s.txt\n  click typing,1\n" % (key.name, key.name)
                    for key in keys if key.types]
    page_toml = _page_toml(page, system_page, width, height, panel, field, field_colour, keys,
                           name)
    return Keyboard(page, page_toml, "\n".join(code_events), name, height_of_font)


def _fitting_font_height(boxes: list, texts: list, width_of=None) -> int:
    """Returns the largest height fonts are drawn at whose text is at most
    two fifths of each box's height, `boxes` being the keys and the field;
    and whose `texts`, [(text, width)], are each at most four fifths of their
    width, as `width_of(text, height)` measures them, by default in Noto
    Sans. The smallest height when none fits."""
    width_of = width_of or typeface_widths(noto_sans())
    tallest = min([_HIGHEST_FONT] + [box.h * 2 // 5 for box in boxes])
    for height in range(tallest, _LOWEST_FONT, -1):
        if all(width_of(text, height) <= width * 4 // 5 for text, width in texts):
            return height
    return _LOWEST_FONT


# The number variables of a keyboard's code. kind: the caller's type.
# numeric: 1 for a number or an xfloat. places: an xfloat's digits after its
# point, 0 for a number. limit: the most bytes to type. mode_shown: the mode
# shown. The others are working values.
_NUMBERS = ("kind", "numeric", "places", "limit", "mode_shown", "count", "bytes", "number",
            "scale", "whole", "digit", "negative", "afterpoint", "decimals", "accept")


def _page_toml(page: str, system_page: str, width: int, height: int, panel, field: Key,
               field_colour: str, keys: list, font: str, numbers: tuple = (),
               hotspots: tuple = (), texts: tuple = ()) -> str:
    """Returns a keyboard's page file: its variables, `numbers` among them,
    its panel if it has one, the field showing the text typed, the hotspot
    typing it and the `hotspots` named, its keys, and the tables of
    `texts`."""
    page_values = {"name": page, "type": "page", "system_page": system_page, "x": 0, "y": 0,
                   "w": width, "h": height}
    # A panel's page has no background, so that the caller's page shows around it.
    page_values.update({"sta": 0} if panel else {"bco": _BACKGROUND})
    tables = [page_values]
    tables += [{"name": name, "type": "variable", "vscope": 1}
               for name in ("loadpageid", "loadcmpid")]
    tables += [{"name": name, "type": "variable", "sta": 1, "txt": "", "txt_maxl": capacity}
               for name, capacity in (("typed", TEXT_CAPACITY), ("pending", 4),
                                      ("part", _NUMBER_CAPACITY))]
    tables += [{"name": name, "type": "variable"} for name in _NUMBERS + tuple(numbers)]
    if panel:
        x, y, w, h = panel
        tables.append(_box("panel", x, y, w, h, _PANEL))
    # Each hotspot is as small as the Editor allows, 2 pixels by 2, under the
    # field's box, which comes after it and so takes a touch there. They lie
    # side by side, because the Nextion Editor's compile warns of hotspots
    # that overlap.
    tables += [{"name": name, "type": "hotspot", "x": field.x + 2 * place, "y": field.y,
                "w": 2, "h": 2}
               for place, name in enumerate(("typing",) + tuple(hotspots))]
    # A text has no padding: the field sits inside a box of its own, so that
    # its text keeps clear of the border.
    tables.append(_box("fieldbox", field.x, field.y, field.w, field.h, field_colour))
    pad = max(2, field.h // 8)
    tables.append({"name": "field", "type": "text", "x": field.x + pad, "y": field.y + 1,
                   "w": field.w - 2 * pad, "h": field.h - 2, "font": font, "bco": field_colour,
                   "pco": _TEXT, "xcen": 0, "txt": "", "txt_maxl": TEXT_CAPACITY})
    for key in keys:
        tables.append({"name": key.name, "type": "button", "x": key.x, "y": key.y, "w": key.w,
                       "h": key.h, "style": 0, "font": font, "bco": key.colour,
                       "bco2": key.pressed, "pco": key.text_colour, "pco2": key.text_colour,
                       "txt": key.label})
    tables += texts
    return page_file_text(tables)


def _box(name: str, x: int, y: int, w: int, h: int, colour: str) -> dict:
    """Returns a text showing nothing but its colour and a border."""
    return {"name": name, "type": "text", "x": x, "y": y, "w": w, "h": h, "style": 1,
            "borderc": _EDGE, "borderw": 1, "bco": colour, "txt": "", "txt_maxl": 1}


def _load_event(page: str) -> str:
    return """\
on %s.load:
  // The caller, which the screen named before opening this page: a number
  // (54) or an xfloat (59) is shown as its digits, any other as its text.
  kind.val=p[loadpageid.val].b[loadcmpid.val].type
  numeric.val=0
  places.val=0
  if(kind.val==54)
  {
    numeric.val=1
  }
  if(kind.val==59)
  {
    numeric.val=1
    places.val=p[loadpageid.val].b[loadcmpid.val].vvs1
  }
  if(numeric.val==1)
  {
    number.val=p[loadpageid.val].b[loadcmpid.val].val
    typed.txt=""
    if(number.val<0)
    {
      typed.txt="-"
      number.val*=-1
    }
    // An xfloat holds its value times 10 to the power of its places.
    scale.val=1
    count.val=0
    while(count.val<places.val)
    {
      scale.val*=10
      count.val++
    }
    whole.val=number.val/scale.val
    covx whole.val,part.txt,0,0
    typed.txt+=part.txt
    // A sign and ten digits, and an xfloat's point.
    limit.val=%d
    if(places.val>0)
    {
      typed.txt+="."
      whole.val*=scale.val
      number.val-=whole.val
      covx number.val,part.txt,places.val,0
      typed.txt+=part.txt
      limit.val++
    }
  }else
  {
    typed.txt=p[loadpageid.val].b[loadcmpid.val].txt
    limit.val=p[loadpageid.val].b[loadcmpid.val].txt_maxl
    if(limit.val>%d)
    {
      limit.val=%d
    }
    if(kind.val==116)
    {
      field.pw=p[loadpageid.val].b[loadcmpid.val].pw
    }
  }
  field.txt=typed.txt
""" % (page, _NUMBER_CAPACITY - 1, TEXT_CAPACITY, TEXT_CAPACITY)


def _typing_event() -> str:
    return """\
on typing.down:
  // Types the character a key passed, while the text has room for it.
  btlen typed.txt,bytes.val
  if(bytes.val<limit.val)
  {
    typed.txt+=pending.txt
    field.txt=typed.txt
  }
"""


def _ok_event() -> str:
    return """\
on ok.up:
  // Writes the text back to the caller, as the type it read it by.
  if(numeric.val==1)
  {
    // The digits, before the point and up to the caller's places after it,
    // make the value, times 10 to the power of its places.
    number.val=0
    negative.val=0
    afterpoint.val=0
    decimals.val=0
    btlen typed.txt,bytes.val
    count.val=0
    while(count.val<bytes.val)
    {
      substr typed.txt,part.txt,count.val,1
      if(part.txt==".")
      {
        afterpoint.val=1
      }else if(part.txt=="-")
      {
        negative.val=1
      }else
      {
        accept.val=1
        if(afterpoint.val==1)
        {
          if(decimals.val>=places.val)
          {
            accept.val=0
          }
        }
        if(accept.val==1)
        {
          covx part.txt,digit.val,0,0
          number.val*=10
          number.val+=digit.val
          decimals.val+=afterpoint.val
        }
      }
      count.val++
    }
    while(decimals.val<places.val)
    {
      number.val*=10
      decimals.val++
    }
    if(negative.val==1)
    {
      number.val*=-1
    }
    p[loadpageid.val].b[loadcmpid.val].val=number.val
  }else
  {
    p[loadpageid.val].b[loadcmpid.val].txt=typed.txt
  }
  page loadpageid.val
"""


def _cancel_event() -> str:
    return "on cancel.up:\n  page loadpageid.val\n"


def _back_event() -> str:
    return "on back.up:\n  typed.txt-=1\n  field.txt=typed.txt\n"


def _mode_event(modes: list, labels: tuple = _MODE_LABELS) -> str:
    """Returns the mode key's event, `modes` being, for each mode in turn, the
    lines that show it, and `labels` the mode key's label in each: the event
    moves to the next mode, after the last to the first."""
    text = "on mode.up:\n"
    for mode, lines in enumerate(modes):
        following = (mode + 1) % len(modes)
        if mode == 0:
            text += "  if(mode_shown.val==%d)\n" % mode
        elif mode < len(modes) - 1:
            text += "  }else if(mode_shown.val==%d)\n" % mode
        else:
            text += "  }else\n"
        shown = ["mode_shown.val=%d" % following] + modes[following]
        shown.append('mode.txt="%s"' % labels[following])
        text += "  {\n" + "".join("    %s\n" % line for line in shown)
    return text + "  }\n"


def _keyboard_mode_event() -> str:
    """The full keyboard's mode key: its letter keys show small letters,
    capitals, then numbers and signs."""
    return _mode_event([['%s.txt="%s"' % (_letter_key(row, column), character)
                         for row, characters in enumerate(mode)
                         for column, character in enumerate(characters)]
                        for mode in _KEYBOARD_MODES])


def _dial_mode_event() -> str:
    """The speed dial's mode key: its groups show small letters, capitals,
    then digits; its space key types a space, then a zero; and the choice
    keys are emptied."""
    modes = []
    for groups, space in zip(_DIAL_MODES, _DIAL_SPACES):
        lines = ['group%d.txt="%s"' % (index + 1, group) for index, group in enumerate(groups)]
        lines += ['choice%d.txt=""' % (index + 1) for index in range(_CHOICES)]
        lines.append('space.txt="%s"' % space)
        modes.append(lines)
    return _mode_event(modes)


def _group_event(name: str) -> str:
    """Returns a group key's event: in digits, it types its digit; else its
    characters show on the choice keys, one each."""
    choices = "".join("    substr %s.txt,choice%d.txt,%d,1\n" % (name, index + 1, index)
                      for index in range(_CHOICES))
    return ("on %s.up:\n  if(mode_shown.val==%d)\n  {\n    pending.txt=%s.txt\n"
            "    click typing,1\n  }else\n  {\n%s  }\n" % (name, _DIGITS_MODE, name, choices))


def _chinese_layout(width: int, height: int) -> tuple:
    """Returns the Chinese keyboard's grid, its keys, and its field: the text
    and cancel; the syllable's place, "<", six candidates, and ">"; the
    letter keys, with the mode key and delete; then a comma, space, a period,
    and OK."""
    margin, gap = _spacing(width, height)
    grid = _Grid(margin, margin, width - 2 * margin, height - 2 * margin, 10, 6, gap)
    keys = [grid.key(1, 2, 1, "previous", "<", types=False)]
    keys += [grid.key(1, 3 + index, 1, "candidate%d" % (index + 1), "", types=False)
             for index in range(_CANDIDATES)]
    keys.append(grid.key(1, 9, 1, "next", ">", types=False))
    for row, (letters, start) in enumerate(zip(_LETTERS, (0, 0.5, 1.5))):
        for column, letter in enumerate(letters):
            keys.append(grid.key(row + 2, start + column, 1, _letter_key(row, column), letter,
                                 types=False))
    keys += [grid.key(4, 0, 1.5, "mode", _CHINESE_MODE_LABELS[0], types=False),
             grid.key(4, 8.5, 1.5, "back", "Del", types=False),
             grid.key(5, 0, 1, "comma", ","),
             grid.key(5, 1, 6, "space", " "),
             grid.key(5, 7, 1, "period", "."),
             _ok_key(grid, 5, 8, 2),
             grid.key(0, 8.5, 1.5, "cancel", "X", types=False)]
    field = grid.key(0, 0, 8.5, "field", "", types=False)
    return grid, keys, field


def _chinese_texts(keys: list) -> list:
    """The texts the Chinese keyboard's keys show besides their labels,
    [(text, width)]: each mode's letters and mode label, a candidate, and the
    longest syllable, in its place."""
    letter = min(key.w for key in keys if key.name.startswith("key"))
    mode_key = next(key for key in keys if key.name == "mode")
    candidate = next(key for key in keys if key.name == "candidate1")
    texts = [(character, letter) for mode in _CHINESE_MODES for row in mode
             for character in row]
    texts += [(label, mode_key.w) for label in _CHINESE_MODE_LABELS]
    texts += [(_CANDIDATE_SAMPLE, candidate.w), (_LONGEST_SYLLABLE, 2 * candidate.w)]
    return texts + [(key.label, key.w) for key in keys]


def _chinese_keyboard(width: int, height: int, font: str, font_height: int) -> Keyboard:
    """The Chinese keyboard, keybdAP, in the font `font`, `font_height`
    pixels tall: laid out as _chinese_layout says."""
    grid, keys, field = _chinese_layout(width, height)
    syllable = grid.key(1, 0, 2, "syllable", "", types=False)
    pad = max(2, syllable.h // 8)
    texts = ({"name": "syllable", "type": "text", "x": syllable.x + pad, "y": syllable.y + 1,
              "w": syllable.w - 2 * pad, "h": syllable.h - 2, "font": font, "bco": _BACKGROUND,
              "pco": _ACCENT, "xcen": 0, "txt": "", "txt_maxl": _SYLLABLE_CAPACITY},)
    events = [_load_event("keybdAP"), _chinese_typing_event(), _ok_event(), _cancel_event(),
              _chinese_back_event(), _letter_event(), _refresh_event(),
              _paging_events(), _chinese_mode_event()]
    events += ["on %s.up:\n  pending.txt=%s.txt\n  click letter,1\n" % (key.name, key.name)
               for key in keys if key.name.startswith("key")]
    events += [_candidate_event(index + 1) for index in range(_CANDIDATES)]
    events += ["on %s.up:\n  pending.txt=%s.txt\n  click typing,1\n" % (key.name, key.name)
               for key in keys if key.types]
    page_toml = _page_toml("keybdAP", CHINESE_INPUT, width, height, None, field, _PANEL, keys,
                           font, ("total", "first"), ("letter", "refresh"), texts)
    return Keyboard("keybdAP", page_toml, "\n".join(events), font, font_height)


def _chinese_typing_event() -> str:
    return """\
on typing.down:
  // Types the character a key passed, while the text has room for all of its
  // bytes: a Chinese character takes two.
  btlen typed.txt,bytes.val
  btlen pending.txt,count.val
  bytes.val+=count.val
  if(bytes.val<=limit.val)
  {
    typed.txt+=pending.txt
    field.txt=typed.txt
  }
"""


def _letter_event() -> str:
    return """\
on letter.down:
  // In pinyin, a letter adds to the syllable, up to %d letters, and its
  // candidates show from the first; in the other modes, it is typed.
  if(mode_shown.val==0)
  {
    strlen syllable.txt,count.val
    if(count.val<%d)
    {
      syllable.txt+=pending.txt
      first.val=0
      click refresh,1
    }
  }else
  {
    click typing,1
  }
""" % (_SYLLABLE_CAPACITY, _SYLLABLE_CAPACITY)


def _refresh_event() -> str:
    """The hotspot showing the syllable's candidates, from candidate
    `first`, as the screen gives them: an empty key past the last."""
    lines = ["on refresh.down:", "  pa_q syllable.txt,total.val", "  count.val=first.val"]
    for index in range(_CANDIDATES):
        if index > 0:
            lines.append("  count.val++")
        lines.append("  pa_txt syllable.txt,candidate%d.txt,count.val,1" % (index + 1))
    return "\n".join(lines) + "\n"


def _paging_events() -> str:
    return """\
on previous.up:
  if(first.val>0)
  {
    first.val-=%d
    click refresh,1
  }

on next.up:
  count.val=first.val+%d
  if(count.val<total.val)
  {
    first.val=count.val
    click refresh,1
  }
""" % (_CANDIDATES, _CANDIDATES)


def _candidate_event(number: int) -> str:
    return """\
on candidate%d.up:
  // Types the candidate, and empties the syllable.
  if(candidate%d.txt!="")
  {
    pending.txt=candidate%d.txt
    click typing,1
    syllable.txt=""
    first.val=0
    click refresh,1
  }
""" % (number, number, number)


def _chinese_back_event() -> str:
    return """\
on back.up:
  // Takes the syllable's last letter, or else the text's last character.
  if(syllable.txt!="")
  {
    syllable.txt-=1
    first.val=0
    click refresh,1
  }else
  {
    typed.txt-=1
    field.txt=typed.txt
  }
"""


def _chinese_mode_event() -> str:
    """The Chinese keyboard's mode key: its letter keys show small letters,
    for pinyin then for typing, capitals, then numbers and signs; and the
    syllable is emptied."""
    return _mode_event([['%s.txt="%s"' % (_letter_key(row, column), character)
                         for row, characters in enumerate(mode)
                         for column, character in enumerate(characters)]
                        + ['syllable.txt=""', "first.val=0", "click refresh,1"]
                        for mode in _CHINESE_MODES], _CHINESE_MODE_LABELS)
