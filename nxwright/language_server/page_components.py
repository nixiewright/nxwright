"""Adding components to a page from the page preview, deleting them,
clearing their code, copying and pasting them, placing several at once, and
moving them up or down the ID order, for the server's requests (server.py).
Each change is an edit of the folder's files, which the editor applies, so
undo works.

A new component's name is its type's prefix and the lowest number that no
object of the page and no page has, such as t0, or t2 once t0 and t1 are
taken (NAME_PREFIXES). It takes the size its type has in the folder's
defaults.toml, and its table goes at the end of the page file, so last in
the ID order, on top. The table is written as extract writes one: its
name, its type, and its place, every other attribute being its type's
default. The edit is refused when the page built before it and would not
after it, as with a page already holding as many objects as the build
allows.

Deleting a component removes its table, and the code of its events, each
with the comment lines right above it, the code from whichever of the page's
.nx files holds it, since the build refuses code for a component the page
does not have. A delete is refused when some of that code is in a file
that other pages include too, which removing it would take from them. The
places where other code names a deleted component come with the edit, for
the editor to ask about first; deleting leaves that code to the checks.
Deleting changes the ID of each component after it, so that an ID written
as a number then names another (editors/vscode/README.md, Before you edit a
page).

Clearing components' events removes their code as deleting does, and is
refused as deleting is, the components and their tables kept. A table's
`events` list stays: an event it lists without code builds empty.

Copying gives the components' tables as the page file holds them, each
with the comment lines right above it, in ID order, a blank line apart, so
that they paste into a page file opened as text; and apart, the code of
their events, each with the comment lines right above its heading.

Pasting takes such tables, from nxwright or typed by hand, and adds them at
the end of the page file, each as it was copied but for its name, place,
and group:
  - a name the page has, or a page has, takes the lowest free number after
    its stem, the name without its final digits: t0 becomes t2 when t0 and
    t1 are taken, title becomes title0. A name that would pass NAME_LIMIT
    takes its type's prefix instead. Names the Editor refuses are skipped;
  - when the page has a component named as one of them at the place it was
    copied from, as after copying within one page, every pasted component
    moves 10 pixels right and down, so as not to hide it. Pasted here, at a
    point, they move together instead, the box holding those with a place
    taking its top left corner there, but kept inside the page. Pasted in
    place, they do not move;
  - copies of two or more members of one group form a new group of their
    own, as Grouping below makes one, and a member copied without any other
    member of its group joins none. The Editor keeps the pair instead, so
    that its copies join their originals' group; nxwright's small pairs
    would then make a paste into another page join that page's group.
The code that came with them goes at the end of the page's own .nx file,
made when the page has none, its headings following the new names; the
code under them is pasted as it was, as a copy made by hand would be. The
paste is refused when the page built before and its tables would stop it
building; the pasted code need not build, since code copied from another
page may name what this page lacks, and is better pasted and mended than
lost.

Pasting parts, as Paste Special does, takes the table of one component and
its code, and applies the parts asked for (PARTS) to each component named:
  - its size and its position, to a component with a place on the screen;
  - its other attributes, as it holds them, its type's defaults filled in,
    but for its name, type, ID, place, size, lock, and group. Between two
    types, only those that mean the same on both are applied
    (_same_meaning). A value the selected type cannot hold is left out;
  - its code: each of its events replaces the selected component's code
    for that event, or goes at the end of the page's own .nx file. The
    headings take the selected component's name, and so does the copied
    component's own name in the code. An event the selected type lacks is
    left out. Code to replace in a file other pages include too is refused,
    as deleting refuses it.
Each thing left out is said in a note. As with pasting, the page file is
checked, and the code is not.

Placing several components at once, as aligning them does, is one edit, so
that one undo takes it back. A component is refused a size under 2 by 2,
which the Editor refuses as it opens the project.

Locking components, or unlocking them, sets their `lockobj`, 1 or 0, as
one edit. The page preview then shows a locked component with a padlock,
and does not move it.

Grouping components gives them a new group of their own, as one edit: the
smallest `groupid0` no component of the page uses, and `groupid1` 0
(component_groups.py). A component in a group leaves it.
Ungrouping sets their pair back to (0, 0), leaving the other members of
their groups as they are, as the Editor's Delete Group does.

Bringing components forward, or sending them backward, moves each one place
up or down the ID order, past the next component not among them, keeping
their order, each table with its comment lines; the page stays first. When
one of them is already at the end they move toward, nothing moves. Bringing
them to the front, or sending them to the back, moves them past every other
component: to the end of the ID order, or right after the page, keeping
their order. As deleting does, this changes IDs, so that an ID written as a
number then names another.

The edits count columns in Python's characters; the server gives them to
the editor in its own units (server.py).
"""
from collections import Counter
import difflib
import re
import tomllib

import tomli_w

from nxwright import MissingFileError, NxwrightError
from nxwright.project.editor_language import NAMES_THE_EDITOR_REFUSES
from nxwright.project.editor_limits import (LEAST_SIDE, NAME_LIMIT, SERIES_NEW_COMPONENT_VALUES,
                                           least_size_words)
from nxwright.project.object_types import TYPE_NAMES, TYPES_BY_NAME
from nxwright.source.definitions import dotted_names
from nxwright.source.folder_index import line_tokens
from nxwright.language_server.page_editing import value_kind
from nxwright.source.page_edits import attribute_edits, edited_text
from nxwright.source.references import references
from nxwright.project.attribute_descriptions import described_by_type
from nxwright.project.attribute_values import number_from_bytes
from nxwright.project.component_defaults import NAME_PREFIXES
from nxwright.source.component_groups import NO_GROUP, group_of, new_groupid0
from nxwright.source.device_keys import screen_model, settings_from_keys
from nxwright.source.folder_check import check_folder
from nxwright.source.nx_files import EVENT_HEADING, with_code_added
from nxwright.source.page_source import (KEY_LINE, attribute_value, component_properties,
                                         page_nx_path, page_toml_path)
from nxwright.source.source_folder import read_page_toml


def component_types(read, page: str) -> list:
    """Returns the types a component of `page` can have, by name, as the
    folder's defaults.toml lists them: [{"type", "placed"}], "placed" being
    whether it has a place on the screen."""
    defaults = read_page_toml(read, page).defaults
    return [{"type": TYPE_NAMES[object_type],
             "placed": "x" in defaults[object_type].names()}
            for object_type in sorted(defaults, key=lambda number: TYPE_NAMES.get(number, ""))
            if object_type in NAME_PREFIXES]


def add_component(index, read, exists, page: str, type_name: str, x: int = 0,
                  y: int = 0) -> dict:
    """Returns {"edits": {path: [TextEdit]}, "name"}: the edits adding a new
    component of the type `type_name` to `page`, its top left corner at (x,
    y) when it has a place, and its name. It takes the folder's defaults,
    but for the values the Editor gives one on the series of the folder's
    screen (editor_limits.SERIES_NEW_COMPONENT_VALUES), written out. Raises
    NxwrightError for a type no component has, and when the page built
    before the edit and would not after it."""
    object_type = TYPES_BY_NAME.get(type_name)
    if object_type not in NAME_PREFIXES:
        raise NxwrightError("%s is not a type of component" % type_name)
    page_toml = read_page_toml(read, page)
    defaults = page_toml.defaults.get(object_type)
    if defaults is None:
        raise NxwrightError("defaults.toml has no type %s" % type_name)
    name = _free_name(NAME_PREFIXES[object_type], _taken_names(index, page))
    values = {"name": name, "type": type_name}
    stored = dict(defaults.attributes)
    if "x" in stored:
        values.update(x=x, y=y, w=number_from_bytes(stored["w"]),
                      h=number_from_bytes(stored["h"]))
    screen = screen_model(page_toml.app)
    if screen is not None:
        values.update(SERIES_NEW_COMPONENT_VALUES.get(screen.series, {}).get(type_name, {}))
    path = page_toml_path(page)
    text = read(path)
    new_text = _with_table(text, "[[component]]\n" + tomli_w.dumps(values))
    _refuse_breaking(read, exists, page, {path: new_text}, "adding %s" % name)
    return {"edits": {path: line_edits(text, new_text)}, "name": name}


def delete_components(index, read, page: str, names: list) -> dict:
    """Returns {"edits": {path: [TextEdit]}, "namedElsewhere": [{"path",
    "line"}]}: the edits deleting the components `names` of `page`, their
    tables and their code, and the places where code that stays names one
    of them. Raises NxwrightError for the page itself, an object the page
    lacks, a .nx file of the page that cannot be read (_refuse_unread_code),
    and code in a file other pages include too."""
    objects = _components_named(index, page, names, "deleted")
    _refuse_unread_code(index, read, page)
    removed = {}        # {path: set of line numbers}
    for name in names:
        found = objects[name]
        removed.setdefault(found.place.path, set()).update(
            _table_lines(index.lines(found.place.path), found))
        _add_code_lines(index, page, name, removed)
    named = []
    for name in names:
        place = objects[name].place
        for use in references(index, place.path, place.line, place.start,
                              with_declarations=False):
            if use.line not in removed.get(use.path, ()):
                named.append({"path": use.path, "line": use.line})
    return {"edits": _removal_edits(read, removed), "namedElsewhere": named}


def clear_events(index, read, page: str, names: list) -> dict:
    """Returns {path: [TextEdit]}: the edits removing the code of every event
    of the components `names` of `page`, as deleting them removes it, the
    components kept; empty when none of them has code. Raises NxwrightError
    as delete_components does."""
    _components_named(index, page, names, "cleared", "")
    _refuse_unread_code(index, read, page)
    removed = {}        # {path: set of line numbers}
    for name in names:
        _add_code_lines(index, page, name, removed)
    return _removal_edits(read, removed)


def copy_components(index, read, page: str, names: list) -> dict:
    """Returns {"text", "code"}: the tables of the components `names` of
    `page`, as the clipboard holds them, and the code of their events, a
    text per event. Raises NxwrightError for the page itself, an object the
    page lacks, and a .nx file of the page that cannot be read
    (_refuse_unread_code)."""
    _components_named(index, page, names, "copied")
    _refuse_unread_code(index, read, page)
    lines = index.lines(page_toml_path(page))
    tables = []
    for entry in index.page_objects[page][1:]:
        if entry.name in names:
            tables.append("".join(lines[number] + "\n" for number in _table_lines(lines, entry)))
    code = []
    for name in names:
        for path, blocks in index.event_blocks(page, name).items():
            code_lines = index.lines(path)
            code += ["".join(code_lines[number] + "\n" for number in _block_lines(code_lines, block))
                     for block in blocks]
    return {"text": "\n".join(tables), "code": code}


def paste_components(index, read, exists, page: str, text: str, code: list = (),
                     at: tuple = None, in_place: bool = False) -> dict:
    """Returns {"edits": {path: [TextEdit]}, "created": [path], "names"}:
    the edits pasting the tables of `text`, and the code that came with them
    (`code`, a text per event), into `page`; the files they make; and the
    pasted components' new names, in order. They go where the module's
    docstring says, or with `at`, (x, y), the box holding those with a place
    has its top left corner there, or with `in_place`, they are not moved.
    Raises NxwrightError for text that is not components' tables, and when
    the page built before and the tables would stop it building."""
    # A clipboard may hold a text's lines ended as Windows ends them.
    tables = _pasted_tables(text.replace("\r\n", "\n"))
    path = page_toml_path(page)
    page_text = read(path)
    components = _page_tables(path, page_text)
    if at is not None:
        step = _step_to(read_page_toml(read, page).app, [table for table, _ in tables], at)
    else:
        places = {table.get("name"): (table.get("x"), table.get("y")) for table in components}
        moved = not in_place and any(
            "x" in table and places.get(table["name"]) == (table.get("x"), table.get("y"))
            for table, _ in tables)
        step = (_PASTE_STEP, _PASTE_STEP) if moved else (0, 0)
    taken = _taken_names(index, page)
    renamed, names, chunks = {}, [], []
    groups = _regrouped([table for table, _ in tables], components)
    for (table, lines), groupid0 in zip(tables, groups):
        name = _pasted_name(table, taken)
        taken.add(name)
        renamed.setdefault(table["name"], name)
        names.append(name)
        new_values = {"name": name}
        if step != (0, 0):
            new_values.update({key: table[key] + change for key, change in zip(("x", "y"), step)
                               if isinstance(table.get(key), int)})
        # A new group's groupid1 is 0, the default, which a table leaves out.
        dropped = set()
        if groupid0 is not None:
            new_values["groupid0"] = groupid0
            dropped = {"groupid1"}
        elif group_of(table) is not None:
            dropped = {"groupid0", "groupid1"}
        chunks.append("".join(_with_values(line, new_values) + "\n" for line in lines
                              if _key_of(line) not in dropped))
    new_text = _with_table(page_text, "\n".join(chunks))
    _refuse_breaking(read, exists, page, {path: new_text}, "pasting")
    edits, created = {path: line_edits(page_text, new_text)}, []
    if code:
        nx_path = page_nx_path(page)
        nx_text = read(nx_path) if exists(nx_path) else None
        if nx_text is None:
            created.append(nx_path)
        blocks = "\n".join(_with_new_headings(block, renamed) for block in code)
        new_nx_text = with_code_added(nx_text or "", blocks)
        edits[nx_path] = line_edits(nx_text or "", new_nx_text)
    return {"edits": edits, "created": created, "names": names}


def paste_parts(index, read, exists, page: str, names: list, text: str, code: list,
                parts: list) -> dict:
    """Returns {"edits": {path: [TextEdit]}, "created": [path], "notes"}:
    the edits applying `parts` (PARTS) of the one component whose table
    `text` holds, its code being `code`, a text per event, to each of the
    components `names` of `page`, as the module's docstring says; the files
    they make; and what was left out, a sentence each. Raises NxwrightError
    for text that holds no one component's table, a part not of PARTS, a
    type the folder's defaults.toml lacks, the code part while a .nx file
    of the page cannot be read (_refuse_unread_code), code in a file other
    pages include too, and when the page built before and its page file
    would stop it building."""
    unknown = [part for part in parts if part not in PARTS]
    if unknown:
        raise NxwrightError("%s is not a part of a component" % unknown[0])
    tables = _pasted_tables(text.replace("\r\n", "\n"))
    if len(tables) != 1:
        raise NxwrightError("Paste Special works with one copied component. "
                            "Copy just one component first")
    copied = tables[0][0]
    _components_named(index, page, names, "given pasted parts", "")
    if "code" in parts:
        _refuse_unread_code(index, read, page)
    page_toml = read_page_toml(read, page)
    path = page_toml_path(page)
    page_text = read(path)
    types = {table.get("name"): table.get("type") for table in _page_tables(path, page_text)}
    copied_values = _copied_values(copied, page_toml) if "attributes" in parts else []
    # A part the copied table cannot give, such as a size it lacks, changes nothing.
    placed = [part for part, keys in (("size", ("w", "h")), ("position", ("x", "y")))
              if part in parts and all(isinstance(copied.get(key), int) for key in keys)]
    page_edits, notes = [], []
    for name in names:
        values = {}
        has_place = "x" in _type_defaults(page_toml, types[name]).names()
        if placed and not has_place:
            notes.append("%s has no place on the screen, so no %s was pasted onto it"
                         % (name, " or ".join(placed)))
        elif placed:
            if "size" in placed:
                values.update(w=copied["w"], h=copied["h"])
            if "position" in placed:
                values.update(x=copied["x"], y=copied["y"])
        values.update(_attribute_values(name, types[name], copied["type"], copied_values,
                                        page_toml, notes))
        if values:
            page_edits += attribute_edits(index, read, page, name, values)
    new_page_text = edited_text(page_text, page_edits)
    _refuse_breaking(read, exists, page, {path: new_page_text}, "pasting parts")
    edits = {path: page_edits} if page_edits else {}
    created = []
    if "code" in parts and code:
        for nx_path, (old_text, new_text) in _pasted_code(index, read, exists, page, names,
                                                          types, copied["name"], code,
                                                          page_toml, notes).items():
            if old_text is None:
                created.append(nx_path)
            edits[nx_path] = line_edits(old_text or "", new_text)
    return {"edits": edits, "created": created, "notes": notes}


def _type_defaults(page_toml, type_name: str):
    """Returns the TypeDefaults of the type `type_name` in the folder of
    `page_toml`. Raises NxwrightError for a type its defaults.toml lacks."""
    defaults = page_toml.defaults.get(TYPES_BY_NAME.get(type_name))
    if defaults is None:
        raise NxwrightError("defaults.toml has no type %s" % type_name)
    return defaults


def _copied_values(copied: dict, page_toml) -> list:
    """Returns the [Property] of the copied component's table `copied`, its
    type's defaults filled in, as the page `page_toml` would hold it."""
    return component_properties(copied, 1, page_toml.names, page_toml.defaults,
                                page_toml.encoding, "the clipboard's %s" % copied["name"])[2]


def _attribute_values(name: str, selected_type: str, copied_type: str, copied_values: list,
                      page_toml, notes: list) -> dict:
    """Returns {attribute: value} of the other attributes the component
    `name`, of the type `selected_type`, takes of `copied_values`, those of
    a component of the type `copied_type`; adds to `notes` those it left
    out, of another meaning or a value it cannot hold."""
    if not copied_values:
        return {}
    attributes = set(_type_defaults(page_toml, selected_type).names())
    values, differing, refused = {}, [], []
    for entry in copied_values:
        attribute = entry.attribute
        if attribute in _NOT_PASTED or attribute not in attributes:
            continue
        if not _same_meaning(copied_type, selected_type, attribute):
            differing.append(attribute)
            continue
        try:
            attribute_value(selected_type, attribute, str(entry.value), page_toml.names,
                            page_toml.encoding, name)
        except NxwrightError:
            refused.append(attribute)
            continue
        values[attribute] = entry.value
    if differing:
        notes.append("Not pasted onto %s, because they mean something else on %s: %s"
                     % (name, _with_article(selected_type), ", ".join(differing)))
    if refused:
        notes.append("Not pasted onto %s, because %s can't hold the copied values: %s"
                     % (name, _with_article(selected_type), ", ".join(refused)))
    return values


def _same_meaning(copied_type: str, selected_type: str, attribute: str) -> bool:
    """Whether `attribute` means the same on components of the two types:
    always on one type. Across two, when both take its common description;
    or when it is a colour, a picture, or a font on both, or `txt`, the
    text a component shows or holds. Other texts and numbers a type
    describes in its own words mean other things on other types, as `dis`
    and `path` do."""
    if copied_type == selected_type:
        return True
    if not (described_by_type(copied_type, attribute)
            or described_by_type(selected_type, attribute)):
        return True
    kinds = {value_kind(TYPES_BY_NAME[type_name], attribute)
             for type_name in (copied_type, selected_type)}
    return kinds in ({"colour"}, {"picture"}, {"font"}) or (attribute == "txt"
                                                             and kinds == {"text"})


def _pasted_code(index, read, exists, page: str, names: list, types: dict, copied_name: str,
                 code: list, page_toml, notes: list) -> dict:
    """Returns {path: (its text, or None for a file to make, its new text)}
    of the .nx files taking the code of the copied component `copied_name`,
    `code`, for each of the components `names` of `page`, whose types are
    `types`, {name: type}; adds to `notes` the events a type lacks. Raises
    NxwrightError for code to replace in a file other pages include too."""
    events = []     # [(event, its code)]
    for block in code:
        heading = next(filter(None, map(EVENT_HEADING.fullmatch, block.split("\n"))), None)
        if heading and heading[1] == copied_name:
            events.append((heading[2], block))
    replaced, added = {}, []    # replaced: {path: [(its lines, new code)]}
    for name in names:
        type_events = _type_defaults(page_toml, types[name]).events
        own = {block.event: (path, block)
               for path, blocks in index.event_blocks(page, name).items() for block in blocks}
        lacked = []
        for event, block in events:
            if event not in type_events:
                lacked.append(event)
                continue
            new_block = _with_own_name(_with_new_headings(block, {copied_name: name}),
                                       copied_name, name)
            if event not in own:
                added.append(new_block)
                continue
            path, found = own[event]
            _refuse_shared_code(index, page, name, path)
            replaced.setdefault(path, []).append((_block_lines(index.lines(path), found),
                                                  new_block))
        if lacked:
            notes.append("Code not pasted onto %s, because %s has no such events: %s"
                         % (name, _with_article(types[name]), ", ".join(lacked)))
    texts = {}
    for path, blocks in replaced.items():
        text = read(path)
        lines = text.split("\n")
        for own_lines, new_block in sorted(blocks, key=lambda pair: pair[0].start, reverse=True):
            lines[own_lines.start:own_lines.stop] = new_block.rstrip("\n").split("\n")
        texts[path] = (text, "\n".join(lines))
    if added:
        # As Paste adds code: at the end of the page's own file, made when missing.
        nx_path = page_nx_path(page)
        old_text, text = texts.get(nx_path) or ((read(nx_path),) * 2 if exists(nx_path)
                                                else (None, ""))
        blocks = "\n".join(added)
        texts[nx_path] = (old_text, with_code_added(text, blocks))
    return texts


def _with_article(type_name: str) -> str:
    """Returns the type's name after "a", or "an" before a vowel's sound, as
    in "an audio" and "an xfloat"."""
    return ("an " if type_name[0] in "aeiou" or type_name.startswith("x") else "a ") + type_name


def _with_own_name(block: str, old: str, new: str) -> str:
    """Returns an event's code with its component's own name, `old`, as
    `new`, where it stands for the component itself: a whole name, outside
    quoted texts and comments, and not after a page's name or a dot."""
    lines = block.split("\n")
    for number, line in enumerate(lines):
        if EVENT_HEADING.fullmatch(line):
            continue
        tokens = line_tokens(line)
        starts = [start for at, (kind, text, start, _) in enumerate(tokens)
                  if kind == "name" and text == old and dotted_names(tokens, at)[0][:1] == [old]]
        for start in reversed(starts):
            line = line[:start] + new + line[start + len(old):]
        lines[number] = line
    return "\n".join(lines)


# The parts of a component Paste Special applies to others.
PARTS = ("size", "position", "attributes", "code")
# What the other attributes leave out: what makes a component what it is,
# its position and size, and the design view's lock and grouping.
_NOT_PASTED = {"objname", "type", "id", "x", "y", "w", "h", "lockobj", "groupid0", "groupid1"}
# How far pasted components move, right and down, so as not to hide the
# originals they were copied from.
_PASTE_STEP = 10
_TABLE_HEADER = re.compile(r"\s*\[")
_COMPONENT_HEADER = re.compile(r"\s*\[\[component\]\]\s*(#.*)?$")


def _pasted_tables(text: str) -> list:
    """Returns [(table, its lines)] of the `[[component]]` tables of `text`.
    Raises NxwrightError, saying what it holds, for text that holds anything
    else, or a table without a name or a known type."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise NxwrightError("the clipboard holds no components' tables: %s" % error) from None
    if set(data) != {"component"}:
        raise NxwrightError("the clipboard holds no components' tables, but %s"
                            % ", ".join(sorted(set(data) - {"component"})) if data
                            else "the clipboard holds no components' tables")
    if not isinstance(data["component"], list):
        raise NxwrightError("the clipboard holds no components' tables")
    chunks, before = [], []     # before: the lines before the first table
    for line in text.split("\n"):
        if _COMPONENT_HEADER.match(line):
            # The comment lines right above a header are its table's, as
            # page files keep them (_table_lines).
            above = chunks[-1] if chunks else before
            comments = []
            while above and above[-1].lstrip().startswith("#"):
                comments.insert(0, above.pop())
            chunks.append(comments + [line])
        elif _TABLE_HEADER.match(line):
            raise NxwrightError("the clipboard holds a table other than a component's: %s"
                                % line.strip())
        else:
            (chunks[-1] if chunks else before).append(line)
    if len(chunks) != len(data["component"]):
        raise NxwrightError("the clipboard's components are not each under a [[component]] line")
    tables = []
    for table, lines in zip(data["component"], chunks):
        if not isinstance(table.get("name"), str) or not isinstance(table.get("type"), str) \
                or TYPES_BY_NAME.get(table["type"]) not in NAME_PREFIXES:
            raise NxwrightError("a table of the clipboard has no name, or no type of component")
        while lines and not lines[-1].strip():
            lines.pop()
        tables.append((table, lines))
    return tables


def _step_to(app: dict, tables: list, at: tuple) -> tuple:
    """Returns how far, (x, y), the pasted `tables` move for the box holding
    those with a place to have its top left corner at `at`. Where the box
    would pass an edge of the page of the screen `app` names, it moves back
    inside, and where it is larger than the page, to the page's edge."""
    placed = [table for table in tables
              if isinstance(table.get("x"), int) and isinstance(table.get("y"), int)]
    if not placed:
        return (0, 0)
    settings = settings_from_keys(app)
    step = []
    for axis, (start_key, size_key) in enumerate((("x", "w"), ("y", "h"))):
        start = min(table[start_key] for table in placed)
        # A table typed by hand may leave its size to its type's default.
        end = max(table[start_key] + (table[size_key] if isinstance(table.get(size_key), int)
                                      else 0) for table in placed)
        corner = at[axis]
        if settings is not None:
            corner = max(0, min(corner, settings.page_size[axis] - (end - start)))
        step.append(corner - start)
    return tuple(step)


def _regrouped(tables: list, components: list) -> list:
    """Returns the `groupid0` of each pasted table of `tables` in the page
    whose tables are `components`, or None for a table that joins no group:
    a new one for each group two or more of them share."""
    pairs = [group_of(table) for table in tables]
    shared = Counter(pairs)
    new, used = {}, list(components)
    for pair in pairs:
        if pair is not None and shared[pair] > 1 and pair not in new:
            new[pair] = new_groupid0(used)
            used.append({"groupid0": new[pair]})
    return [new.get(pair) for pair in pairs]


def place_components(index, read, page: str, places: dict) -> list:
    """Returns the protocol's TextEdits of the page file placing several
    components of `page` at once, `places` being {name: {"x", "y", "w",
    "h"}}. Raises NxwrightError for a width or height under the Editor's
    least, which the build refuses too, and as setting each attribute would
    (page_edits.attribute_edits)."""
    named = _components_named(index, page, list(places), "placed")
    edits = []
    for name, place in places.items():
        if place["w"] < LEAST_SIDE or place["h"] < LEAST_SIDE:
            raise NxwrightError("%s would be %d by %d; %s"
                                % (name, place["w"], place["h"],
                                   least_size_words(named[name].type, place["w"], place["h"])))
        edits += attribute_edits(index, read, page, name,
                                 {key: place[key] for key in ("x", "y", "w", "h")})
    return edits


def lock_components(index, read, page: str, names: list, locked: bool) -> list:
    """Returns the protocol's TextEdits of the page file locking the
    components `names` of `page`, or unlocking them."""
    _components_named(index, page, names, "locked", " here, but by its page file's `locked`")
    edits = []
    for name in names:
        edits += attribute_edits(index, read, page, name, {"lockobj": 1 if locked else 0})
    return edits


def group_components(index, read, page: str, names: list, grouped: bool) -> list:
    """Returns the protocol's TextEdits of the page file giving the
    components `names` of `page` a new group of their own, or taking them
    out of theirs."""
    _components_named(index, page, names, "grouped", "")
    pair = {"groupid0": NO_GROUP, "groupid1": 0}
    if grouped:
        path = page_toml_path(page)
        pair["groupid0"] = new_groupid0(_page_tables(path, read(path)))
    edits = []
    for name in names:
        edits += attribute_edits(index, read, page, name, pair)
    return edits


def reorder_components(index, read, page: str, names: list, direction: str) -> list:
    """Returns the protocol's TextEdits of the page file moving the
    components `names` of `page` one place "forward", up the ID order, or
    "backward", down it; or past every other component, to the "front", the
    end of the ID order, or to the "back", right after the page; as the
    module's docstring says. None when they move nowhere."""
    if direction not in ("forward", "backward", "front", "back"):
        raise NxwrightError("components move forward, backward, to the front, or to the back, "
                            "not %s" % direction)
    _components_named(index, page, names, "moved")
    tables = index.page_objects[page][1:]
    order = [entry.name for entry in tables]
    if direction in ("front", "back"):
        new_order = _moved_to_an_end(order, set(names), direction == "front")
    else:
        new_order = _moved_one_place(order, set(names), direction == "forward")
    if new_order == order:
        return []
    path = page_toml_path(page)
    text = read(path)
    lines = text.split("\n")
    own = {entry.name: _table_lines(lines, entry) for entry in tables}
    head = lines[:own[order[0]].start]
    tail = lines[own[order[-1]].stop:]
    body = "\n\n".join("\n".join(lines[number] for number in own[name]) for name in new_order)
    return line_edits(text, "\n".join(head + body.split("\n") + tail))


def _moved_to_an_end(order: list, chosen: set, front: bool) -> list:
    """Returns `order` with the names of `chosen` at its end, when `front`,
    else at its start, in the order they had."""
    kept = [name for name in order if name in chosen]
    others = [name for name in order if name not in chosen]
    return others + kept if front else kept + others


def _moved_one_place(order: list, chosen: set, forward: bool) -> list:
    """Returns `order` with each name of `chosen` one place toward its end,
    when `forward`, else toward its start, past the next name not chosen;
    or `order` as it is when a chosen name is at that end already."""
    names = list(reversed(order)) if forward else list(order)
    if names[0] in chosen:
        return order
    for number in range(1, len(names)):
        if names[number] in chosen and names[number - 1] not in chosen:
            names[number - 1], names[number] = names[number], names[number - 1]
    return list(reversed(names)) if forward else names


def _pasted_name(table: dict, taken: set) -> str:
    """Returns the name a pasted table takes on its page, whose objects and
    pages hold the names `taken`: its own when free, else the lowest free
    number after its stem, or after its type's prefix when that would pass
    NAME_LIMIT."""
    name = table["name"]
    if name not in taken:
        return name
    found = _free_name(name.rstrip("0123456789"), taken)
    if len(found.encode("utf-8")) <= NAME_LIMIT:
        return found
    return _free_name(NAME_PREFIXES[TYPES_BY_NAME[table["type"]]], taken)


def _page_tables(path: str, text: str) -> list:
    """Returns the component tables of the page file at `path`, whose text
    is `text`. Raises NxwrightError for a file that does not read."""
    try:
        return tomllib.loads(text).get("component", [])
    except tomllib.TOMLDecodeError as error:
        raise NxwrightError("%s: %s" % (path, error)) from None


def _key_of(line: str):
    """Returns the key a table's `line` gives, or None for another line."""
    match = KEY_LINE.match(line)
    return match[1] if match else None


def _with_values(line: str, values: dict) -> str:
    """Returns a table's `line`, set to `values`' when it gives one of its keys."""
    match = KEY_LINE.match(line)
    if match and match[1] in values:
        # A page file's values are numbers and texts, each on one line.
        return tomli_w.dumps({match[1]: values[match[1]]}).rstrip("\n")
    return line


def _with_new_headings(block: str, renamed: dict) -> str:
    """Returns an event's code, its heading naming its component's new name."""
    lines = block.split("\n")
    for number, line in enumerate(lines):
        heading = EVENT_HEADING.fullmatch(line)
        if heading and heading[1] in renamed:
            lines[number] = "on %s.%s:" % (renamed[heading[1]], heading[2])
    return "\n".join(lines)


def _components_named(index, page: str, names: list, what: str,
                      instead: str = " here, but in app.toml") -> dict:
    """Returns {name: PageObject} of the components `names` of `page`.
    Raises NxwrightError for an object the page lacks, and for the page
    itself, saying it is not `what`, then `instead`, how it is."""
    objects = {entry.name: entry for entry in index.page_objects.get(page, [])}
    for name in names:
        if name not in objects:
            raise NxwrightError("page %s has no object %s" % (page, name))
        if objects[name] is index.page_objects[page][0]:
            raise NxwrightError("a page is not %s%s" % (what, instead))
    return {name: objects[name] for name in names}


def _add_code_lines(index, page: str, name: str, removed: dict):
    """Adds the lines of the code of the component `name`'s events, each
    event with the comment lines right above it, to `removed`, {path: set of
    line numbers}. Raises NxwrightError for code in a file other pages
    include too, which removing it would take from them."""
    for path, blocks in index.event_blocks(page, name).items():
        _refuse_shared_code(index, page, name, path)
        lines = index.lines(path)
        for block in blocks:
            removed.setdefault(path, set()).update(_block_lines(lines, block))


def _refuse_unread_code(index, read, page: str):
    """Raises NxwrightError while a .nx file of `page`'s code cannot be read,
    in the words of `read` (FileTexts.folder_reader): "is missing", or "is
    not UTF-8 text", as the build refuses the folder. The file's code would
    otherwise be left out of what a command copies, removes, or pastes over.
    A page without code lacks a file of its own, which is fine."""
    for path in index.unread_code_files(page):
        try:
            read(path)
        except MissingFileError:
            if path != page_nx_path(page):
                raise


def _refuse_shared_code(index, page: str, name: str, path: str):
    """Raises NxwrightError when the code of the component `name` of `page`
    is in `path`, a .nx file other pages include too: changing it there
    would change those pages."""
    if index.pages_using(path) != [page]:
        raise NxwrightError("the code of %s is in %s, which other pages include too: "
                            "move it to the page's own file first" % (name, path))


def _removal_edits(read, removed: dict) -> dict:
    """Returns {path: [TextEdit]} removing the lines `removed`, {path: set of
    line numbers}, from each file (_without_lines)."""
    edits = {}
    for path, lines in removed.items():
        text = read(path)
        edits[path] = line_edits(text, _without_lines(text, lines))
    return edits


def _taken_names(index, page: str) -> set:
    """Returns the names no new component of `page` may take: those of its
    objects, of the pages, and those the Editor refuses."""
    return ({entry.name for entry in index.page_objects.get(page, [])} | set(index.pages)
            | NAMES_THE_EDITOR_REFUSES)


def _free_name(stem: str, taken: set) -> str:
    """Returns `stem` and the lowest number that makes a name not `taken`."""
    number = 0
    while "%s%d" % (stem, number) in taken:
        number += 1
    return "%s%d" % (stem, number)


def _with_table(text: str, table: str) -> str:
    """Returns a page file's `text` with `table` at its end, after a blank line."""
    body = text.rstrip("\n")
    return body + "\n\n" + table if body else table


def _table_lines(lines: list, table) -> range:
    """Returns the lines of a page file's table that are its own: the comment
    lines right above its header, the header, and its keys, up to its last
    line that is neither blank nor a comment right above the next table's
    header, which is that table's own."""
    start = table.first_line
    while start > 0 and lines[start - 1].lstrip().startswith("#"):
        start -= 1
    end = table.last_line
    if end + 1 < len(lines):
        while end > table.first_line and lines[end].lstrip().startswith("#"):
            end -= 1
    while end > table.first_line and not lines[end].strip():
        end -= 1
    return range(start, end + 1)


def _block_lines(lines: list, block) -> range:
    """Returns the lines of an event that are its own: the comment lines right
    above its heading, the heading, and its code, up to its last code line.
    The blank lines and comments after that lead to the next heading."""
    start = block.place.line
    while start > 0 and lines[start - 1].startswith("//"):
        start -= 1
    end = block.place.line
    for number in range(block.place.line + 1, block.end_line + 1):
        if lines[number][:1] in (" ", "\t"):
            end = number
    return range(start, end + 1)


def _without_lines(text: str, removed: set) -> str:
    """Returns `text` without the lines `removed`. Where a run of them goes,
    the blank line after it goes too when it would follow another blank line
    or start the text, so that the blank lines between tables and between
    events stay single. The rest of the text is left as it is."""
    lines = text.split("\n")
    kept, number = [], 0
    while number < len(lines):
        if number not in removed:
            kept.append(lines[number])
            number += 1
            continue
        while number in removed:
            number += 1
        if number < len(lines) and not lines[number].strip() and not (kept and kept[-1].strip()):
            number += 1
    return "\n".join(kept)


def line_edits(text: str, new_text: str) -> list:
    """Returns the protocol's TextEdits turning `text` into `new_text`, a
    line at a time: one per run of lines that differ."""
    old_lines, new_lines = _lines_with_ends(text), _lines_with_ends(new_text)

    def position(number: int) -> dict:
        # Past the last line of a text without a final newline: its end.
        if number == len(old_lines) and old_lines and not text.endswith("\n"):
            last = old_lines[-1]
            return {"line": number - 1, "character": len(last)}
        return {"line": number, "character": 0}
    return [{"range": {"start": position(old_start), "end": position(old_end)},
             "newText": "".join(new_lines[new_start:new_end])}
            for tag, old_start, old_end, new_start, new_end
            in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes()
            if tag != "equal"]


def _lines_with_ends(text: str) -> list:
    """Returns the lines of `text`, each with its newline but the last when
    the text does not end with one."""
    lines = [line + "\n" for line in text.split("\n")]
    lines[-1] = lines[-1][:-1]
    return lines if lines[-1] else lines[:-1]


def _refuse_breaking(read, exists, page: str, texts: dict, what: str):
    """Raises NxwrightError when `page` built before an edit and would not
    after it, the edited files reading `texts`, {path: new text}."""
    if check_folder(read, exists, [page]).errors():
        return
    errors = check_folder(lambda path: texts[path] if path in texts else read(path),
                          exists, [page]).errors()
    if errors:
        place = "%s line %d" % (errors[0].file, errors[0].line) if errors[0].line \
            else errors[0].file
        raise NxwrightError("the page would not build after %s: %s: %s"
                            % (what, place, errors[0].message))
