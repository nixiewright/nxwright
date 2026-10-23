"""Drawing a data record: a table of the records of its data file, as the
Editor's simulator draws it (tests/fixtures/data-record/).

Its background and border are a text's. Inside them, grid lines of `gdc`,
those across `gdw` wide and those up and down `gdh` wide, part a row of
titles from a row per record, each row `hig` high, its line along its top,
a last line under the last record, and nothing below it. The titles are
`dir`, split at `^`, in `pco1` on `bco1`; without titles (`dir` empty),
the top record takes their row, on `bco1`, in `pco`. The records are in
`pco`, the chosen one (`val`) in `pco2` on `bco2`, in the titles' row too;
`order` 0 shows the newest at the top, `order` 1 the oldest. Each
record's fields, split at `^`, go in `dez` columns, as wide as `format`
gives, split at `^`, or else sharing the inside's width; a text sits in
its cell from the cell's left edge, or as `xcen` places it, centred up and
down. A cell the screen's right edge cuts has its text placed in the part
left of it; one its left edge cuts, in the whole cell, so that a text at
the cell's left starts out of sight. So the Editor's simulator drew them
(tests/fixtures/drawing-assumptions/, page23 to page27), as it draws a
select's lines and a combo box's items; a cell the screen's bottom edge
cuts is taken to be placed as theirs are. Once the part of a cell left of
the screen's left edge is as wide as its text, the text is placed as if it
had no width: centred, it starts at the cell's middle, and right-aligned,
it shows nothing (tests/fixtures/data-record-scroll/).

`val_y` scrolls the records under the titles, which stay, as far as
`maxval_y`, or 32 pixels further, as code may set it, and as far as 32
pixels above their top, which leaves an empty band under the titles;
`val_x` scrolls
every column, titles with them, as far as `maxval_x`, which counts the
line at the right of the last column (table_layout). A scroll bar's thumb
shows by `left`, at the right of the records, as a sliding text's does
(ComponentPainter.scroll_thumb).

The page preview has no SD card, so it draws the titles and lines alone; a
simulation gives the records, read from the data file
(testing/data_files.py). A record that could not open its file, as another
record holds it, or 8 others are open, a simulation lists as UNOPENED: it
is drawn black inside its border, with "Cannot open file:" and its path in
white, as the Editor's simulator drew it
(tests/fixtures/data-record/unopened.png). A record of
no `path` is drawn alike with "File Lost:", in the page preview too, as
the Editor's simulator and page view drew it
(tests/fixtures/data-record/file-lost.png).
"""
from dataclasses import dataclass

from nxwright import NxwrightError
from nxwright.drawing.sliding_text_drawing import ABOVE_BY_CODE, FURTHER_BY_CODE
from nxwright.drawing.text_pictures import text_size

# The attributes the table reads, at the type's defaults
# (component_defaults.toml), for a table marked defaults = false.
DEFAULTS = {"path": "sd0/1.data", "dez": 3, "hig": 32, "gdw": 1, "gdh": 1, "gdc": 50712,
            "order": 0, "val": -1, "val_y": 0, "val_x": 0, "xcen": 0,
            "dir": "head0^head1^head2", "format": ""}
NEWEST_FIRST = 0
# What a simulation lists for a data record that could not open its file,
# as another record holds it, or 8 others are open, in place of its records.
UNOPENED = object()
# The colours of such a record's message, in RGB565.
_BLACK, _WHITE = 0, 0xFFFF


def value(values: dict, attribute: str):
    """A data record's `attribute`, its type's default when `values` lack it."""
    return values.get(attribute, DEFAULTS[attribute])


def fields(text: str) -> list:
    """A record's or the titles' fields: `text` split at `^`."""
    return text.split("^") if text else []


@dataclass(frozen=True)
class TableLayout:
    """Where a data record's table lies, from the inside of its border."""
    columns: tuple     # (left, width) of each column, its line at its left
    width: int         # the columns' width
    height: int        # every row's height, the titles' included, and the last line
    most_y: int        # `maxval_y`: how far the records scroll up
    most_x: int        # `maxval_x`: how far the columns scroll left


def table_layout(values: dict, records: int, inside: dict) -> TableLayout:
    """Returns where a data record with the attributes `values` lays out
    `records` records inside its border, `inside`: a row each, and the
    titles' row, which the top record takes when there are no titles."""
    rows = records + (1 if fields(value(values, "dir")) else 0)
    count = max(value(values, "dez"), 1)
    down = value(values, "gdh")
    widths = [int(width) if width.strip().isdecimal() else 0
              for width in fields(value(values, "format"))[:count]]
    if widths:
        widths += [0] * (count - len(widths))
        lefts = [sum(widths[:column]) for column in range(count + 1)]
        width = lefts[-1]
    else:
        # Sharing the inside, less the last line's width.
        room = max(inside["w"] - down, 0)
        lefts = [column * room // count for column in range(count + 1)]
        width = inside["w"]
    columns = tuple((lefts[column], lefts[column + 1] - lefts[column]) for column in range(count))
    height = rows * value(values, "hig") + value(values, "gdw")
    # The line at the right of the last column scrolls into view too.
    return TableLayout(columns, width, height, max(height - inside["h"], 0),
                       max(lefts[-1] + down - inside["w"], 0))


def table_rows(values: dict, records: int) -> tuple:
    """Returns which of `records` records each row of a data record with
    the attributes `values` shows, by their numbers from 0, the oldest:
    (top, below). `top` is the record in the titles' row, which takes it
    when there are no titles, or None; `below` holds the records of the
    rows under the titles' row, top to bottom."""
    numbers = list(range(records))
    if value(values, "order") == NEWEST_FIRST:
        numbers.reverse()
    if numbers and not fields(value(values, "dir")):
        return numbers[0], numbers[1:]
    return None, numbers


def record_at(values: dict, records: int, inside: dict, y: int):
    """Returns the number of the record whose row is at the page's row `y`
    in a data record with the attributes `values`, holding `records`
    records inside its border, `inside`; None on the titles' row, below the
    last record, or outside the table. As the Editor's simulator chose
    them under a tap (tests/fixtures/data-record/)."""
    top, below = table_rows(values, records)
    titled = top is not None or bool(fields(value(values, "dir")))
    hig = max(value(values, "hig"), 1)
    if not inside["y"] <= y < inside["y"] + inside["h"]:
        return None
    if titled and y < inside["y"] + hig:
        return top
    row = (y - _records_top(values, table_layout(values, records, inside), inside, titled)) // hig
    return below[row] if 0 <= row < len(below) else None


def _records_top(values: dict, layout: TableLayout, inside: dict, titled: bool) -> int:
    """The page's row where the line of the first record under the titles'
    row is, as `val_y` scrolls them, as far as code may scroll them past
    `layout`'s farthest."""
    scrolled = min(max(value(values, "val_y"), -ABOVE_BY_CODE), layout.most_y + FURTHER_BY_CODE)
    return inside["y"] + (value(values, "hig") if titled else 0) - scrolled


def paint_data_record(painter):
    """Paints a data record: its background, its titles and records in their
    table, its scroll bar's thumb, and its border."""
    values = painter.values
    painter.background({0: "picc", 1: "bco", 2: "pic"})
    inside = painter.inside()
    if inside["w"] <= 0 or inside["h"] <= 0:
        painter.border()
        return
    try:
        font = painter.resources.font(values.get("font", 0))
    except NxwrightError as error:
        painter.note("its table is not drawn: %s" % error)
        painter.border()
        return
    if painter.listing is UNOPENED:
        _paint_unopened(painter, font, inside,
                        "Cannot open file:\r\n%s" % painter.values.get("path", ""))
        painter.border()
        return
    if not value(values, "path"):
        _paint_unopened(painter, font, inside, "File Lost:")
        painter.border()
        return
    texts = list(painter.listing or [])
    layout = table_layout(values, len(texts), inside)
    top, numbers = table_rows(values, len(texts))
    titles, title_colours = fields(value(values, "dir")), ("bco1", "pco1")
    if top is not None:
        # The top record takes the titles' row, in its own text's colour, or
        # in the chosen one's. An empty record still has its row.
        titles = texts[top].split("^")
        title_colours = ("bco2", "pco2") if top == value(values, "val") else ("bco1", "pco")
    titled = bool(titles)
    scrolled_x = min(max(value(values, "val_x"), 0), layout.most_x)
    left = inside["x"] - scrolled_x
    title_height = value(values, "hig") if titled else 0
    # The records show below the titles, which stay.
    below = {"x": inside["x"], "y": inside["y"] + title_height, "w": inside["w"],
             "h": inside["h"] - title_height}
    first_top = _records_top(values, layout, inside, titled)
    _Table(painter, values, font, layout, left).paint(
        titles, title_colours, [texts[number] for number in numbers], numbers, inside, below,
        first_top)
    if below["h"] > 0:
        painter.scroll_thumb(below["y"] - first_top, layout.most_y, below)
    painter.border()


def _paint_unopened(painter, font, inside: dict, message: str):
    """Paints a data record that has no file open in place of its table:
    black inside its border, and `message` in white whatever its colours,
    in its font, from the top left, wrapped at the width."""
    painter.colour_within(inside, inside, _BLACK)
    painter.text_within(message, font,
                        {"font": painter.values.get("font", 0), "isbr": 1, "xcen": 0,
                         "ycen": 0, "spax": 0}, inside, _WHITE, inside)


class _Table:
    """Paints one data record's rows and lines, its columns from `left`."""

    def __init__(self, painter, values: dict, font, layout: TableLayout, left: int):
        self.painter, self.values, self.font, self.layout = painter, values, font, layout
        self.left = left
        self.hig, self.across, self.down = (value(values, key) for key in ("hig", "gdw", "gdh"))
        self.placing = {"font": values.get("font", 0), "xcen": value(values, "xcen"), "ycen": 1,
                        "spax": values.get("spax", 0)}

    def paint(self, titles: list, title_colours: tuple, records: list, numbers: list,
              inside: dict, below: dict, first_top: int):
        """Paints the titles' row at the top of `inside`, if any, in
        `title_colours` (background, text), and the records' rows from
        `first_top`, cut to `below`, then the lines."""
        chosen = value(self.values, "val")
        if titles:
            self.row(titles, inside["y"], *title_colours, inside)
        for index, (record, number) in enumerate(zip(records, numbers)):
            colours = ("bco2", "pco2") if number == chosen else (None, "pco")
            self.row(fields(record), first_top + index * self.hig, *colours, below)
        # The titles' row has its line along its top; the line under it is
        # the first record's, which scrolls with the records.
        if titles:
            self.lines([inside["y"]], inside["y"], inside["y"] + self.hig, inside)
        bottom = first_top + len(records) * self.hig
        self.lines(range(first_top, bottom + 1, self.hig), first_top, bottom + self.across, below)

    def row(self, texts: list, top: int, back, ink: str, shown: dict):
        """Paints a row whose line is at `top`: its background `back`, if
        any, and each column's text in `ink`, cut to `shown`."""
        cell_top, cell_height = top + self.across, self.hig - self.across
        if back is not None:
            self.painter.colour_within({"x": self.left, "y": cell_top, "w": self.layout.width,
                                        "h": cell_height}, shown, self.values.get(back, 0))
        for (left, width), text in zip(self.layout.columns, texts):
            cell = {"x": self.left + left + self.down, "y": cell_top, "w": width - self.down,
                    "h": cell_height}
            # A cell the screen's right or bottom edge cuts has its text
            # placed in the part shown; at its left edge, in the whole cell.
            box = self.painter.before_screen_end(cell)
            if text and box is not None:
                placing, box = self._placed(text, cell, box)
                if box is not None:
                    self.painter.text_within(text, self.font, placing, box,
                                             self.values.get(ink, 0), shown)

    def _placed(self, text: str, cell: dict, box: dict) -> tuple:
        """Returns (placing, box), how `text` is placed in its cell: as
        `xcen` places it in `box`. Once the part of the cell left of the
        screen's left edge is as wide as the text, the Editor's simulator
        placed it as if it had no width. So a centred text starts at the
        middle of `box`, and a right-aligned one shows nothing (box None)."""
        xcen = self.placing["xcen"]
        if xcen not in (1, 2) or cell["x"] >= 0:
            return self.placing, box
        try:
            width = text_size(text, self.font, self.painter.resources.encoding,
                              self.placing["spax"])[0]
        except NxwrightError:
            return self.placing, box        # text_within notes the lacking character
        if -cell["x"] < width:
            return self.placing, box
        if xcen == 2:
            return self.placing, None
        middle = box["w"] // 2
        return dict(self.placing, xcen=0), dict(box, x=box["x"] + middle, w=box["w"] - middle)

    def lines(self, across: list, top: int, bottom: int, shown: dict):
        """Paints the grid lines: those across at the rows `across`, and the
        columns' lines from `top` down to `bottom`, cut to `shown`."""
        colour = value(self.values, "gdc")
        if self.across > 0:
            for line in across:
                self.painter.colour_within({"x": self.left, "y": line,
                                            "w": self.layout.width + self.down,
                                            "h": self.across}, shown, colour)
        if self.down > 0 and bottom > top:
            last_left, last_width = self.layout.columns[-1]
            for edge in [left for left, _ in self.layout.columns] + [last_left + last_width]:
                self.painter.colour_within({"x": self.left + edge, "y": top, "w": self.down,
                                            "h": bottom - top}, shown, colour)
