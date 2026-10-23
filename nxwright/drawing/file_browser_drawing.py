"""Drawing a file browser: its background and border, its entries in rows
and columns (BrowserLayout), and its scroll bar, as page_drawing.py's
opening comment says. The simulation reads the layout too, to take a tap on
an entry.
"""
from dataclasses import dataclass
import fnmatch
import re

from nxwright import NxwrightError
from nxwright.drawing.drawing_shared import NO_RESOURCE, PLACE, border_width, box_of, part_within
from nxwright.drawing.sliding_text_drawing import ABOVE_BY_CODE, FURTHER_BY_CODE


# The attributes of a file browser that its drawing and the simulation read,
# at the type's defaults (component_defaults.toml), for a table marked
# defaults = false.
BROWSER_DEFAULTS = {"w": 240, "h": 240, "sta": 1, "style": 2, "borderw": 2, "dis": 3,
                    "spax": 24, "spay": 8, "pic1": 0, "pic2": 1, "psta": 1, "left": 1,
                    "font": 0, "bco": 0xFFFF, "pco": 0, "bco2": 31, "pco2": 0xFFFF,
                    "val": -1, "val_y": 0, "maxval_y": 0, "vvs2": ""}


@dataclass(frozen=True)
class BrowserLayout:
    """Where a file browser places its entries, in pixels from its corner,
    before it scrolls, as page_drawing.py's opening comment says."""
    left: int           # the first column's left edge
    top: int            # the first row's top: the border's width
    columns: int
    cell_width: int     # an icon's width, which a name wraps at
    icon_height: int
    names_height: int   # `dis` lines of the font
    across: int         # from a column's left edge to the next one's
    down: int           # from a row's top to the next one's

    def cell(self, index: int) -> tuple:
        """The top left corner of entry `index`'s cell, before scrolling."""
        row, column = divmod(index, self.columns)
        return self.left + column * self.across, self.top + row * self.down

    def most_scroll(self, count: int, height: int) -> int:
        """How far `count` entries scroll in a browser `height` high: its
        `maxval_y`, their rows' height past the browser's, less twice its
        border. The Editor's simulator gave 150 for four rows of 88 in a
        browser 200 high with a border of 1, and 200 for three rows of 120
        in one 140 high with a border of 10, 220 with none."""
        rows = -(-count // self.columns)
        return max(rows * self.down - height - 2 * self.top, 0)

    def place_at(self, x: int, y: int, scroll: int):
        """Where the browser's pixel (x, y) falls once scrolled by `scroll`:
        the number of the cell, an icon and its name, that holds it, counted
        along the rows from 0, whether an entry fills it or not; -1 between
        two cells; or None before the first column. A pixel above the first
        row, in the border, counts as just inside it, scrolled or not, as the
        Nextion Editor's simulator took a tap there."""
        if x < self.left:
            return None
        column, inside_x = divmod(x - self.left, self.across)
        row, inside_y = divmod(max(y - self.top, 0) + scroll, self.down)
        if column >= self.columns or inside_x >= self.cell_width or \
                inside_y >= self.icon_height + self.names_height:
            return -1
        return row * self.columns + column


def browser_icon_size(values: dict, picture_size) -> tuple:
    """Returns the size of a file browser's icons, (width, height), from its
    attributes `values`, `picture_size(id)` giving a picture's size or None:
    its file icon's, `pic2`, to which every icon is cut; None when `pic2` is
    no picture, as the Editor's simulator then drew no entry."""
    return picture_size(values["pic2"])


def browser_layout(values: dict, icon_size: tuple, font_height: int) -> BrowserLayout:
    """Places a file browser's entries, from its attributes `values`, the
    (width, height) of its icons, and its font's height. As many columns as
    fit an icon and `spax` between two inside its border, centred on its
    width; rows an icon, `dis` lines of names, and `spay` apart, from inside
    its border. So the Nextion Editor's simulator laid out browsers 360 to
    400 wide, with borders of 0, 1, and 10."""
    values = dict(BROWSER_DEFAULTS, **values)
    width, icon_height = icon_size
    spax, spay = values["spax"], values["spay"]
    border = border_width(values)
    across = width + spax
    columns = max((values["w"] - 2 * border + spax) // across, 1) if across > 0 else 1
    used = columns * width + (columns - 1) * spax
    names_height = max(values["dis"], 0) * font_height
    return BrowserLayout(left=max((values["w"] - used) // 2, 0), top=border,
                         columns=columns, cell_width=width, icon_height=icon_height,
                         names_height=names_height, across=max(across, 1),
                         down=max(icon_height + names_height + spay, 1))


def _own_icons(text) -> list:
    """A file browser's own icons for some files, from its `vvs2`, such as
    "*.txt/2*.data/3": [(pattern, picture ID)], the patterns in small letters,
    matched as `filter`'s are."""
    found = re.findall(r"([^/]+?)/(\d+)", text if isinstance(text, str) else "")
    return [(pattern.lower(), int(number)) for pattern, number in found]


def paint_file_browser(painter):
    """Paints a file browser: its background and border, its entries
    scrolled and cut to its inside, and its scroll bar, as
    page_drawing.py's opening comment says. The preview, which has no SD
    card, lists nothing."""
    painter.values = dict(BROWSER_DEFAULTS, **painter.values)
    values = painter.values
    painter.background({0: "picc", 1: "bco", 2: "pic"})
    border = border_width(values)
    x, y, w, h = (painter.box[key] for key in PLACE)
    # Inside the border, and a row short of it at the bottom, as the
    # Editor's simulator cut the entries.
    inside = box_of(x + border, y + border, w - 2 * border, h - 2 * border - 1)
    if painter.listing:
        _browser_entries(painter, painter.listing, inside)
    painter.border()
    painter.scroll_thumb(values["val_y"], values["maxval_y"])


def _browser_entries(painter, entries: list, inside: dict):
    """Paints a file browser's entries, each its icon and its name under
    it, the selected one over a box of `bco2`, its name in `pco2`."""
    values = painter.values
    icon = browser_icon_size(values, painter.resources.picture_size)
    if icon is None:
        if values["pic2"] != NO_RESOURCE:
            painter.note("picture %s is not a picture of the folder" % values["pic2"])
        return
    try:
        font = painter.resources.font(values["font"])
    except NxwrightError as error:
        painter.note("its names are not drawn: font %s: %s" % (values["font"], error))
        font = None
    layout = browser_layout(values, icon, font.height if font is not None else 0)
    own_icons = _own_icons(values["vvs2"])
    bottom = inside["y"] + inside["h"]
    # A `val_y` code set past what the screen settles it to is drawn there.
    scrolled = min(max(values["val_y"], -ABOVE_BY_CODE), values["maxval_y"] + FURTHER_BY_CODE)
    for index, name in enumerate(entries):
        column_x, row_y = layout.cell(index)
        left, top = painter.box["x"] + column_x, painter.box["y"] + row_y - scrolled
        cell = box_of(left, top, layout.cell_width, layout.icon_height + layout.names_height)
        if top >= bottom:
            break
        if top + cell["h"] <= inside["y"]:
            continue
        chosen = index == values["val"]
        if chosen:
            painter.colour_within(cell, inside, values["bco2"])
        if name.endswith("/"):
            picture = values["pic1"]
        else:
            picture = next((number for pattern, number in own_icons
                            if fnmatch.fnmatch(name.lower(), pattern)), values["pic2"])
        # Each icon is cut to the file icon's size.
        shown = part_within(box_of(left, top, *icon), inside)
        if shown is not None:
            _picture_within(painter, picture, left, top, shown)
        if font is not None and layout.cell_width > 0 and layout.names_height > 0:
            painter.text_within(name, font, {"isbr": 1, "xcen": 1, "ycen": 0},
                                box_of(left, top + layout.icon_height, layout.cell_width,
                                       layout.names_height),
                                values["pco2" if chosen else "pco"], inside)


def _picture_within(painter, picture_id: int, left: int, top: int, inside: dict):
    """Paints the part within `inside` of the picture `picture_id`, its
    corner at (left, top), or notes once why it cannot."""
    name, size = painter.resources.picture(picture_id), painter.resources.picture_size(picture_id)
    if name is None or size is None:
        painter.note("picture %s is not a picture of the folder" % picture_id)
        return
    shown = part_within(box_of(left, top, *size), inside)
    if shown is not None:
        painter.folder_picture(shown, name, (shown["x"] - left, shown["y"] - top))
