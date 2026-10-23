"""Working out a page's list components as code sets their attributes, and
as their page opens, as the Nextion Editor's simulator did: file browsers,
selects, sliding texts, combo boxes, and data records' scroll values. The
test machine (editor_machine.py) works them after each store, and as a
test's page opens (EditorMachine.open_page); the simulation (simulation.py)
as a page opens and on a touch; so a test and the simulator work them alike.

- A file browser lists its folder, `dir`, as its page opens and when code
  sets `dir`: its folders, unless `psta` is 0, then the files its `filter`
  lets through, each in alphabetical order, capitals ignored. `qty` counts
  them, nothing is selected (`val` -1, `txt` empty), and it is scrolled to
  its top, as far as `maxval_y` lets its entries scroll, which its icons'
  size and its font's height give. Its `val` picks an entry, whose name
  `txt` gives, a folder's ending with "/"; its `val_y` scrolls it up to 32
  pixels past `maxval_y`, as a sliding text's does: the Editor gave 32 for
  60 to a browser whose entries all fit, and 110 for 500 to one of
  `maxval_y` 78. `up()` goes to the folder above, no higher than its card's
  own, and lists it. A listing code asks for leaves `maxval_y` to the next
  settle point, and its `val_y` then goes no further than `maxval_y`.
- A select's `val` picks a line of its `path`, whose text `txt` gives; the
  machine refuses a `val` past its last line, or below 0.
- A sliding text's new `txt` or `font` works out its `maxval_y` from its
  lines in its font (sliding_text_drawing.py); its `val_y` scrolls it as far
  as code may scroll it, no further than its last line lets it.
- A combo box's `val` within its items sets `txt` to that item; one past
  them is taken back to the last within them. Where its open list shows
  is its drawing's, the simulation's (combo_boxes.py).
- A data record's `val_y` scrolls it up to 32 pixels past `maxval_y`, and
  its `val_x` from 0 to `maxval_x`. Its table's values and its file are the
  machine's.

The three that scroll take a `val_y` up to 32 pixels above their top too.
Their scroll values settle within these limits only at a settle point: once
an event, or a typed instruction, ends, and at a `doevents` (settle), and as
their page opens. Until then, code reads back what it set, as the Nextion
Editor's simulator gave it.

What stays between stores is kept as records among the machine's values,
`records`, so that each event of a run, and each page of a simulation, sees
it: each browser's listing, which its `val` picks from, and each combo box's
last `val` within its items, both by (page, name).
"""
import fnmatch

from nxwright import NxwrightError
from nxwright.drawing.combo_box_drawing import items
from nxwright.drawing.file_browser_drawing import (BROWSER_DEFAULTS, browser_icon_size,
                                                   browser_layout)
from nxwright.drawing.page_drawing import inside_box
from nxwright.drawing.sliding_text_drawing import (ABOVE_BY_CODE, FURTHER_BY_CODE, SlidingLayout,
                                                   sliding_layout)
from nxwright.drawing.text_pictures import path_lines
from nxwright.testing.sd_cards import CardRefusal

# The records of what stays between stores, among the machine's values.
FILE_BROWSER_LISTINGS = "file browser listings"     # {(page, browser): [entry names]}
COMBO_BOX_CHOICES = "combo box choices"             # {(page, box): its last `val` within its items}
# {(page, list): whether it is a browser listed since}: the lists whose
# scroll values code changed since the last settle point (settle).
UNSETTLED = "unsettled scrolls"
# The attributes whose setting by code works each type.
_WORKED = {"file-browser": ("dir", "val", "val_y"), "select": ("val",),
           "sliding-text": ("txt", "font", "val_y"), "combo-box": ("val",),
           "data-record": ("val_y", "val_x")}
# The cards' and the RAM's own folders, which a file browser goes no higher than.
_CARD_FOLDERS = ("sd0/", "sd1/", "ram/")


class ListWorking:
    """Works the list components of a folder whose fonts and pictures are
    `resources` (folder_resources.FolderResources), on SD cards given
    folders, `cards` (sd_cards.FolderCards, or None), its texts in
    `encoding`. Each method takes a component's values in `values`, named
    as code names them ("fb0.dir"), writes what follows there directly,
    and keeps what stays between stores in `records`."""

    def __init__(self, resources, cards, encoding: str):
        self.resources, self.cards, self.encoding = resources, cards, encoding

    def works(self, kind: str, attribute: str) -> bool:
        """Whether code setting `attribute` of a component of type `kind`,
        such as "file-browser", works it."""
        return attribute in _WORKED.get(kind, ())

    def stored(self, page: str, component: str, kind: str, attribute: str, values,
               records: dict):
        """Code set `component`'s `attribute`, of type `kind`, on `page`."""
        name = component + "."
        if kind == "file-browser" and attribute == "dir":
            self.list_folder(page, component, values, records, by_code=True)
        elif kind == "file-browser" and attribute == "val":
            entries = self.listing(page, component, records)
            index = values.get(name + "val")
            values[name + "txt"] = entries[index] \
                if isinstance(index, int) and 0 <= index < len(entries) else ""
        elif attribute in ("val_y", "val_x"):
            # Read back as set until the screen settles it.
            records.setdefault(UNSETTLED, {}).setdefault((page, component), False)
        elif kind == "select":
            lines = path_lines(values.get(name + "path", ""))
            index = values.get(name + "val")
            values[name + "txt"] = lines[index] \
                if isinstance(index, int) and 0 <= index < len(lines) else ""
        elif kind == "sliding-text":
            self.slide(component, values)
            records.setdefault(UNSETTLED, {}).setdefault((page, component), False)
        elif kind == "combo-box":
            lines = items(_attributes(component, values))
            chosen = values.get(name + "val")
            choices = records.setdefault(COMBO_BOX_CHOICES, {})
            if isinstance(chosen, int) and 0 <= chosen < len(lines):
                choices[(page, component)] = chosen
                values[name + "txt"] = lines[chosen]
            else:
                values[name + "val"] = choices.get((page, component), 0)

    def opened(self, page: str, component: str, kind: str, values, records: dict):
        """`component`, of type `kind`, shows as `page` opens: a browser lists
        its folder, a sliding text works out how far it scrolls, and a combo
        box's `val` is the last within its items. Its scroll values settle,
        as its page is drawn: a data record's too, once its file is open,
        though code on another page set them."""
        if kind == "file-browser":
            self.list_folder(page, component, values, records)
        elif kind == "sliding-text":
            self.slide(component, values)
        elif kind == "combo-box":
            self.chose(page, component, values.get(component + ".val"), records)
        records.get(UNSETTLED, {}).pop((page, component), None)
        self.settle_one(page, component, kind, values, records)

    def chose(self, page: str, box: str, number, records: dict):
        """Keeps `number` as the combo box `box`'s last `val` within its items,
        as a touch chose it."""
        records.setdefault(COMBO_BOX_CHOICES, {})[(page, box)] = number

    def list_folder(self, page: str, browser: str, values, records: dict, by_code: bool = False):
        """Lists the file browser `browser`'s folder, as the module's
        docstring says. Listed `by_code`, its `maxval_y` waits for the
        screen to settle it (settle)."""
        name = browser + "."
        pattern = str(values.get(name + "filter", "*.*")).lower()
        names = self._entries(str(values.get(name + "dir", "")), records)
        folders = sorted((entry for entry in names if entry.endswith("/")), key=str.lower) \
            if values.get(name + "psta", BROWSER_DEFAULTS["psta"]) != 0 else []
        files = sorted((entry for entry in names if not entry.endswith("/")
                        and fnmatch.fnmatch(entry.lower(), pattern)), key=str.lower)
        listing = folders + files
        records.setdefault(FILE_BROWSER_LISTINGS, {})[(page, browser)] = listing
        values[name + "qty"] = len(listing)
        values[name + "val"] = -1
        values[name + "txt"] = ""
        values[name + "val_y"] = 0
        if by_code:
            records.setdefault(UNSETTLED, {})[(page, browser)] = True
        else:
            self._work_browser_scroll(page, browser, values, records)

    def _work_browser_scroll(self, page: str, browser: str, values, records: dict):
        """Works out how far the file browser `browser` scrolls, its
        `maxval_y`, from its listing."""
        layout = self.browser_layout(browser, values)
        values[browser + ".maxval_y"] = 0 if layout is None else layout.most_scroll(
            len(self.listing(page, browser, records)),
            values.get(browser + ".h", BROWSER_DEFAULTS["h"]))

    def up(self, page: str, browser: str, values, records: dict):
        """A file browser's `up()`, which code runs: to the folder above, no
        higher than its card's own, then listed. A folder may be named with
        or without its last "/"."""
        folder = str(values.get(browser + ".dir", "")).rstrip("/")
        if (folder + "/").lower() not in _CARD_FOLDERS and "/" in folder:
            values[browser + ".dir"] = folder.rsplit("/", 1)[0] + "/"
        self.list_folder(page, browser, values, records, by_code=True)

    def settle(self, page: str, kinds, values, records: dict):
        """Settles the scroll values of `page`'s list components that code
        changed since the last settle point, as the screen settles them once
        an event ends (editor_machine.py): `kinds(component)` gives a
        component's type, as "data-record". `val_y` from 32 pixels above the
        top to 32 past `maxval_y`; a sliding text's no further than its last
        line lets it; a browser listed meanwhile, its `maxval_y` worked out,
        no further than it. A data record's `val_x` from 0 to `maxval_x`. So
        the Nextion Editor's simulator settled them."""
        unsettled = records.get(UNSETTLED, {})
        for key in [key for key in unsettled if key[0] == page]:
            self.settle_one(page, key[1], kinds(key[1]), values, records, unsettled.pop(key))

    def settle_one(self, page: str, component: str, kind: str, values, records: dict,
                   listed: bool = False):
        """Settles one list component's scroll values, as settle says;
        `listed` when it is a browser listed since the last settle point."""
        name = component + "."
        scroll = values.get(name + "val_y", 0)
        if kind == "file-browser":
            if listed:
                self._work_browser_scroll(page, component, values, records)
            farthest = values.get(name + "maxval_y", 0) + (0 if listed else FURTHER_BY_CODE)
        elif kind == "data-record":
            farthest = values.get(name + "maxval_y", 0) + FURTHER_BY_CODE
            values[name + "val_x"] = min(max(values.get(name + "val_x", 0), 0),
                                         values.get(name + "maxval_x", 0))
        elif kind == "sliding-text":
            farthest = self.sliding_layout(component, values).farthest
        else:
            return
        values[name + "val_y"] = min(max(scroll, -ABOVE_BY_CODE), farthest)

    def listing(self, page: str, browser: str, records: dict) -> list:
        """The entries the file browser `browser` of `page` lists, or none."""
        return records.get(FILE_BROWSER_LISTINGS, {}).get((page, browser), [])

    def browser_layout(self, browser: str, values):
        """Where a file browser places its entries (file_browser_drawing.py), from
        its attributes in `values` and the folder's icons and font, laid out
        by its file icon's size (browser_icon_size); None when its file icon
        is no picture, so that it draws no entry, scrolls not at all, and a
        tap picks none."""
        attributes = dict(BROWSER_DEFAULTS, **_attributes(browser, values))
        icon = browser_icon_size(attributes, self.resources.picture_size)
        if icon is None:
            return None
        return browser_layout(attributes, icon,
                              self.resources.font_height(attributes.get("font", 0)))

    def sliding_layout(self, component: str, values) -> SlidingLayout:
        """How far a sliding text scrolls (sliding_text_drawing.py), from its
        attributes in `values`; not at all when its font cannot be read or
        lacks a character."""
        attributes = _attributes(component, values)
        font = self.resources.font(attributes.get("font", 0))
        try:
            return SlidingLayout(0, 0) if font is None else \
                sliding_layout(attributes, font, self.encoding, inside_box(attributes))
        except NxwrightError:
            return SlidingLayout(0, 0)

    def slide(self, component: str, values):
        """Works out a sliding text's `maxval_y`, as the screen does. Its
        `val_y` waits for the screen to settle it (settle_one)."""
        values[component + ".maxval_y"] = self.sliding_layout(component, values).most

    def _entries(self, folder: str, records: dict) -> set:
        """The names in a folder: of a card given a folder of the computer,
        or else of the card in memory, its files and the paths in
        "existing", a folder's ending with "/"."""
        if self.cards is not None and self.cards.owns(folder):
            try:
                return set(self.cards.entries(folder))
            except (CardRefusal, OSError):
                return set()
        folder = folder if folder.endswith("/") else folder + "/"
        names = set()
        for path in [*records.get("existing", ()), *records.get("file contents", {})]:
            if isinstance(path, str) and path.startswith(folder) and path != folder:
                rest = path[len(folder):]
                names.add(rest.split("/", 1)[0] + "/" if "/" in rest else rest)
        return names


def _attributes(component: str, values) -> dict:
    """The attributes of `component` in `values`, by their own names, the
    page file's beneath a test's (card_files.component_attributes)."""
    prefix = component + "."
    found = {}
    for layer in reversed(getattr(values, "maps", [values])):
        found.update({key[len(prefix):]: value for key, value in layer.items()
                      if key.startswith(prefix)})
    return found
