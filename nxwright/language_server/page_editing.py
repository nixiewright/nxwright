"""Editing a page from the page preview: what the properties panel lists, the
key a component may be bound to, and where a component's events are, for
the server's requests (server.py). The edits its changes and the mouse make
are source/page_edits.py's.

A component's events are those its type lists in defaults.toml, in that
order. Its default event, which double-clicking it opens, is the first of
them that has code, or the first of them when none has. An event without
code has its heading added at the end of the page's own .nx file when it is
opened, and the cursor goes under it. A type that lists no events, such as
a variable, has none.

Their places count columns in Python's characters; the server gives them
to the editor in its own units (server.py).
"""
from nxwright import NxwrightError
from nxwright.language.resource_names import FONT, NOUNS
from nxwright.language_server.attributes import attribute_tooltip
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.project.page_header import SYSTEM_PAGES
from nxwright.project.page_text import is_string_attribute
from nxwright.project.attribute_descriptions import SHOWN, describe
from nxwright.source.keyboards import CHINESE_INPUT, KEYBOARD_PAGES
from nxwright.source.keyboard_adding import chinese_keyboard_fonts, keyboard_page
from nxwright.source.nx_files import with_code_added
from nxwright.source.page_edits import ComponentTable
from nxwright.source.page_source import (COLOUR_ATTRIBUTES, attribute_value, page_nx_path,
                                         reference_kind)


def properties(index, read, page: str, name: str) -> dict:
    """Returns what the properties panel shows of the object `name` of
    `page`: its "name", "type", whether its table is marked defaults = false
    ("defaultsFalse"), its table's "firstLine" and "lastLine", the place of
    its name ("nameLine", "nameCharacter"), and its "attributes", each with
    its "name", "value", "default", whether the table gives it ("given"),
    its "kind" (text, colour, picture, font, animation, video, sound, or
    number), the "choices" of a resource's name, "none" first but for a
    font, the "labels" of a number's choices, [{"value", "label"}], in
    order, the "line" of the table that gives it, or the table's first
    line, its "description", as plain text for the name's tooltip and the
    panel's footer, and its "treatment" in the panel: shown with a field,
    value-only, hidden, or never-shown (attribute_descriptions.py). Raises
    NxwrightError as the build would."""
    table = ComponentTable(index, read, page, name)
    object_type = TYPES_BY_NAME.get(table.type)
    names = table.page_toml.names
    attributes = []
    for entry in table.properties:
        kind = value_kind(object_type, entry.attribute)
        resource = reference_kind(object_type, entry.attribute)
        choices = [] if resource is None else (
            names.names(resource) if resource == FONT else ["none"] + names.names(resource))
        described = describe(table.type, entry.attribute)
        labels = [{"value": number, "label": label}
                  for number, label in sorted(described.choices.items())] if described else []
        attributes.append({"name": entry.attribute, "value": entry.value,
                           "default": entry.default, "given": entry.given, "kind": kind,
                           "choices": choices, "labels": labels,
                           "line": table.key_lines.get(entry.attribute,
                                                       table.object.first_line),
                           "description": attribute_tooltip(table.type, entry.attribute),
                           "treatment": described.properties if described else SHOWN})
    place = table.object.place
    return {"name": name, "type": table.type, "defaultsFalse": table.full,
            "firstLine": table.object.first_line, "lastLine": table.object.last_line,
            "nameLine": place.line, "nameCharacter": place.start, "attributes": attributes}


def key_binding(index, read, page: str, name: str, typed) -> dict:
    """Returns what setting the `key` of the object `name` to `typed`, its
    value as typed, means, for the properties panel: "keyboard", the keyboard
    it opens that nxwright has a page of (KEYBOARD_PAGES), or None, as for
    Chinese input in a folder of another encoding than gb2312; "present",
    whether the folder has that keyboard, nxwright's or the Editor's;
    "local", whether the key opens a keyboard and the object is of local
    scope, which a keyboard does not take; "chinese", whether it opens
    Chinese input, whose keyboard nxwright adds to a gb2312 folder alone;
    and "fonts", the folder's fonts that the Chinese keyboard takes
    (keyboard_adding.chinese_keyboard_fonts), or [] for another keyboard.
    Raises NxwrightError for an object without `key`, and for a value `key`
    cannot hold."""
    table = ComponentTable(index, read, page, name)
    table.property("key")
    toml = table.page_toml
    key = attribute_value(table.type, "key", str(typed), toml.names, toml.encoding, table.where)
    kind = {number: kind for kind, number in SYSTEM_PAGES.items()}.get(key)
    chinese = kind == CHINESE_INPUT
    # The Chinese keyboard types gb2312 text (keyboard_adding.add_keyboard).
    keyboard = kind if kind in KEYBOARD_PAGES and (not chinese or toml.encoding == "gb2312") \
        else None
    present = keyboard is not None and keyboard_page(
        read, table.page_toml.app["pages"], keyboard) is not None
    fonts = chinese_keyboard_fonts(index.root, toml.app) if keyboard == CHINESE_INPUT else []
    return {"keyboard": keyboard, "present": present,
            "local": kind is not None and table.property("vscope").value != 1,
            "chinese": chinese, "fonts": fonts}


def value_kind(object_type: int, attribute: str) -> str:
    """Returns the kind of value the properties panel shows for an attribute
    of the type `object_type`: text, colour, picture, font, animation,
    video, sound, or number."""
    if object_type is not None and is_string_attribute(object_type, attribute):
        return "text"
    if attribute in COLOUR_ATTRIBUTES:
        return "colour"
    return NOUNS.get(reference_kind(object_type, attribute), "number")


def component_events(index, read, page: str, name: str) -> list:
    """Returns the events of the object `name` of `page`, in its type's
    order, each {"event", "path"}: the file of the page that holds its code,
    or None when it has none. Empty for a type without events."""
    blocks = _blocks_by_event(index, page, name)
    return [{"event": event, "path": blocks[event][0] if event in blocks else None}
            for event in _type_events(ComponentTable(index, read, page, name))]


def default_event(index, read, page: str, name: str, event: str = None) -> dict | None:
    """Returns where an event of the object `name` of `page` is: `event`,
    else its default event, the first its type lists that has code, or the
    first it lists when none has. {"path", "line", "character"} of its first
    line of code, in whichever file of the page defines it, and "edit",
    None, or when it has no code, the TextEdit adding its heading at the end
    of the page's own .nx file, after one blank line (with_code_added), the
    place then being the line under it.
    Returns None when its type has no events. Raises NxwrightError for an
    event its type lacks."""
    table = ComponentTable(index, read, page, name)
    events = _type_events(table)
    if not events:
        return None
    if event is not None and event not in events:
        raise NxwrightError("%s: type %s has no event %s" % (table.where, table.type, event))
    blocks = _blocks_by_event(index, page, name)
    if event is None:
        event = next((listed for listed in events if listed in blocks), events[0])
    if event in blocks:
        path, block = blocks[event]
        names = index.nx_file(path)
        line = block.place.line + 1 if block.end_line > block.place.line else block.place.line
        code = names.lines[line]
        return {"path": path, "line": line, "character": len(code) - len(code.lstrip()),
                "edit": None}
    path = page_nx_path(page)
    text = "\n".join(index.lines(path) or [""])
    new_text = with_code_added(text, "on %s.%s:\n" % (name, event))
    return {"path": path, "line": new_text.count("\n"), "character": 0,
            "edit": _code_added_edit(text, new_text)}


def _code_added_edit(text: str, new_text: str) -> dict:
    """Returns the TextEdit turning the .nx file `text` into `new_text`, the
    same file with code added at its end (with_code_added). The edit keeps
    the file's code lines. It replaces the blank lines the file ends with,
    or adds after the last line of a file that does not end with a newline.
    A file without code is replaced whole."""
    kept = text.rstrip("\n")
    if not text.strip():
        start, end, added = {"line": 0, "character": 0}, _end_of(text), new_text
    elif kept == text:
        start = end = _end_of(text)
        added = new_text[len(text):]
    else:
        start = {"line": kept.count("\n") + 1, "character": 0}
        end = {"line": text.count("\n"), "character": 0}
        added = new_text[len(kept) + 1:]
    return {"range": {"start": start, "end": end}, "newText": added}


def _end_of(text: str) -> dict:
    """Returns the LSP position of the end of `text`."""
    return {"line": text.count("\n"), "character": len(text) - text.rfind("\n") - 1}


def _type_events(table: ComponentTable) -> list:
    """Returns the events the type of `table` lists in defaults.toml."""
    type_defaults = table.page_toml.defaults.get(TYPES_BY_NAME.get(table.type))
    return type_defaults.events if type_defaults else []


def _blocks_by_event(index, page: str, name: str) -> dict:
    """Returns {event: (path, block)} for each event of the object `name`
    that has code in a file of `page`, the first file holding it when two
    do."""
    blocks = {}
    for path, found in index.event_blocks(page, name).items():
        for block in found:
            blocks.setdefault(block.event, (path, block))
    return blocks
