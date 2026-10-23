"""Editing a component's table in a page file's text: the edits that set its
attributes, and a text with such edits applied. The page preview's
properties panel makes them (language_server/page_editing.py), and so does
a change of the folder's screen (device_change.py).

Every change is an edit of the file's text, a TextEdit of the editor's
protocol, so that an editor applies it and its undo works. A page file's
table is changed one line at a time:
  - a value set to its type's default is removed from the table, as extract
    writes tables; `x`, `y`, `w`, and `h` stay, being always written, and a
    table marked `defaults = false` keeps every key;
  - another value replaces its line, or takes a new line, before the first
    attribute that comes after it in the type's order, else after the
    table's last attribute.
Their places count columns in Python's characters; the language server gives
them to the editor in its own units (language_server/server.py).
"""
import tomllib

import tomli_w

from nxwright import NxwrightError
from nxwright.project.component_defaults import PLACEMENT_ATTRIBUTES
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.project.screen_colours import nearest_screen_colour
from nxwright.source.page_source import (COLOUR_ATTRIBUTES, KEY_LINE, attribute_value,
                                         component_properties, page_toml_path, stored_value)
from nxwright.source.source_folder import read_page_toml


class ComponentTable:
    """One table of a page file: the object it describes, its ID, its lines,
    and the line of each of its keys. `index` is the source folder's
    FolderIndex (folder_index.py), and `read` reads a file of it, as the
    editor has it."""

    def __init__(self, index, read, page: str, name: str):
        self.page, self.name, self.path = page, name, page_toml_path(page)
        self.page_toml = read_page_toml(read, page)
        try:
            data = tomllib.loads(self.page_toml.text)
        except tomllib.TOMLDecodeError as error:
            raise NxwrightError("%s: %s" % (self.path, error)) from None
        tables = [data.get("page", {})] + list(data.get("component", []))
        ids = [number for number, table in enumerate(tables) if table.get("name") == name]
        found = [entry for entry in index.page_objects.get(page, []) if entry.name == name]
        if not ids or not found:
            raise NxwrightError("page %s has no object %s" % (page, name))
        self.table, self.object_id, self.object = tables[ids[0]], ids[0], found[0]
        self.where = "%s, %s" % (self.path, name)
        self.type, self.full, self.properties = component_properties(
            self.table, self.object_id, self.page_toml.names, self.page_toml.defaults,
            self.page_toml.encoding, self.where)
        lines = self.lines = index.lines(self.path) or [""]
        self.key_lines = {}
        for number in range(self.object.first_line + 1, self.object.last_line + 1):
            match = KEY_LINE.match(lines[number])
            if match:
                self.key_lines.setdefault(match[1], number)

    def property(self, attribute: str):
        found = [entry for entry in self.properties if entry.attribute == attribute]
        if not found:
            raise NxwrightError("%s: type %s has no attribute %s" % (self.where, self.type,
                                                                     attribute))
        return found[0]


def attribute_edits(index, read, page: str, name: str, values: dict,
                    nearest_colours: bool = False) -> list:
    """Returns the protocol's TextEdits of the page file setting attributes of
    the object `name`, {attribute: its value as typed}. With
    `nearest_colours`, as for a colour picked rather than typed, a colour is
    set to the nearest the screen holds (screen_colours.nearest_screen_colour).
    Raises NxwrightError, as the build would, for a value the attribute
    cannot hold."""
    table = ComponentTable(index, read, page, name)
    toml = table.page_toml
    order = [entry.attribute for entry in table.properties]
    type_defaults = dict(toml.defaults[TYPES_BY_NAME[table.type]].attributes) \
        if TYPES_BY_NAME.get(table.type) in toml.defaults else {}
    edits, inserted = [], {}    # inserted: {line: [(place in the order, key line)]}
    for attribute, text in values.items():
        table.property(attribute)
        text = str(text)
        if nearest_colours and attribute in COLOUR_ATTRIBUTES:
            text = nearest_screen_colour(text)
        value = attribute_value(table.type, attribute, text, toml.names, toml.encoding,
                                table.where)
        stored = stored_value(table.type, attribute, value, toml.names, toml.encoding, table.where)
        line = table.key_lines.get(attribute)
        if stored == type_defaults.get(attribute) and not table.full \
                and attribute not in PLACEMENT_ATTRIBUTES:
            if line is not None:
                edits.append(_line_edit(line, line + 1, ""))
        elif line is not None:
            edits.append(_line_edit(line, line + 1, _key_value(attribute, value)))
        else:
            inserted.setdefault(_insertion_line(table, order, attribute), []).append(
                (order.index(attribute), _key_value(attribute, value)))
    # New keys at one line make one edit, in the type's order.
    for line, keys in inserted.items():
        text = "".join(text for _, text in sorted(keys))
        if line < len(table.lines):
            edits.append(_line_edit(line, line, text))
        else:
            # Past the end of a file with no final newline: after its last line.
            end = len(table.lines[-1])
            edits.append({"range": {"start": {"line": len(table.lines) - 1, "character": end},
                                    "end": {"line": len(table.lines) - 1, "character": end}},
                          "newText": "\n" + text[:-1]})
    return edits


def edited_text(text: str, edits: list) -> str:
    """Returns `text` with the TextEdits attribute_edits makes applied, the
    last first: whole lines replaced, and text inserted at a place, as at
    the end of a file's last line. Raises ValueError for another edit."""
    lines = text.split("\n")
    for edit in sorted(edits, key=lambda edit: edit["range"]["start"]["line"], reverse=True):
        start, end = edit["range"]["start"], edit["range"]["end"]
        if start["line"] >= len(lines):
            # An editor takes a place past the end as the end of the last line.
            lines = ("\n".join(lines) + edit["newText"]).split("\n")
            continue
        if start == end and start["character"]:
            line = lines[start["line"]]
            column = start["character"]
            lines[start["line"]] = line[:column] + edit["newText"] + line[column:]
            lines = "\n".join(lines).split("\n")
            continue
        if start["character"] or end["character"]:
            raise ValueError("not an edit of whole lines: %r" % (edit,))
        new = edit["newText"].split("\n")[:-1] if edit["newText"] else []
        lines[start["line"]:end["line"]] = new
    return "\n".join(lines)


def _key_value(attribute: str, value) -> str:
    return tomli_w.dumps({attribute: value})


def _insertion_line(table: ComponentTable, order: list, attribute: str) -> int:
    """Returns the line a new attribute's line goes before: that of the first
    attribute after it in the type's order that the table gives, else the
    line after the table's last attribute, or after its name and type."""
    later = [table.key_lines[other] for other in order[order.index(attribute) + 1:]
             if other in table.key_lines]
    if later:
        return min(later)
    given = [table.key_lines[other] for other in order + ["name", "type"]
             if other in table.key_lines]
    return max(given) + 1 if given else table.object.first_line + 1


def _line_edit(start: int, end: int, text: str) -> dict:
    """Returns a TextEdit replacing whole lines `start` to `end` (not included)."""
    return {"range": {"start": {"line": start, "character": 0},
                      "end": {"line": end, "character": 0}}, "newText": text}
