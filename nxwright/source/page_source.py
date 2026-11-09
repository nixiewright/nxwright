"""A page as source files: "<page>.page.toml" (the page and its components) and
"<page>.nx" (their event code).

<page>.page.toml holds a [page] table for the page itself, then one [[component]]
table per component, in ID order. Each table has:
  name     the object's name
  type     its type as a readable name (or the type number, if unknown)
  events   the events it has, with or without code; left out when they are
           its type's default events
then its attributes by their names in the Editor. Attributes equal to the
type's default are left out, except x, y, w, and h (see component_defaults.py).
An object whose attributes differ from its type's defaults in name or order,
or whose type has no section in the folder's defaults.toml, lists every
attribute in stored order and is marked "defaults = false". The [page]
table of one of the Editor's system pages also says which it is:
system_page = "keyboard", "keypad", "speed-dial", or "chinese-input". That of a locked page says
locked = true, and gives its lock's password, if any, as app.toml gives the
project's: lock_password_hash = "<8 hexadecimal digits>" (page_header.py).
The rest of the page header is not written: the build derives it.

Attributes that can be derived are left out and recomputed: "id" (the ID),
"objname" (the name), and "endx" and "endy" (x + w - 1 and y + h - 1). One
whose stored value differs from the derived value is written. Colours are
written as "#rrggbb"; text values as strings, in the project's character
encoding, as is the code (device_settings.TextCodec). Picture and font
attributes hold the picture's or font's name, or a number when no picture or
font has that ID (65535 means none). So does a `vid`, naming the animation,
video, or sound its component plays (reference_kind).

<page>.nx holds each event that has code under a heading, in ID order:

  on zero.up:
    if(syncing==0)
    {
    }

Code lines are indented by two spaces. The build turns them into Editor syntax
with code_preprocessor.py, which also drops blank lines.

This module also builds a page back from its source files (page_from_source),
compiling its events first when the folder uses nxlang. The screen's colours
are in screen_colours.py.
"""
from dataclasses import dataclass, replace
import re
import tomllib

import tomli_w

from nxwright import NxwrightError
from nxwright.language.code_checks import ObjectNames
from nxwright.language.code_preprocessor import Owner, preprocess, preprocess_with_places
from nxwright.project.object_types import TYPE_NAMES, TYPES_BY_NAME
from nxwright.project.page_file_names import page_file_stem
from nxwright.project.screen_colours import COLOUR_TEXT, hex_to_rgb565, rgb565_to_hex
from nxwright.project.screen_models import ScreenModel
from nxwright.project.component_defaults import DERIVED_ATTRIBUTES, PLACEMENT_ATTRIBUTES
from nxwright.project.device_settings import (DEFAULT_ENCODING, TextCodec, encoding_code,
                                              is_password_hash_text)
from nxwright.project.editor_limits import (LEAST_SIDE, bounded_attributes, check_component_count,
                                             check_page_limits, least_size_words)
from nxwright.project.page_block import HEADER_SIZE, Attribute, Event, Marker, PageBlock, PageObject
from nxwright.project.page_header import (HEADER_21, NO_LOCK_PASSWORD, SYSTEM_PAGES, PageHeader,
                                         header_16, header_40, page_header_of)
from nxwright.source.defines import filled
from nxwright.source.content_sorts import CANNOT_BE_KEPT, KEPT, MAY_BE_LOST, WRITTEN_OTHERWISE
from nxwright.source.nx_files import (CODE_INDENT, EVENT_COMMENT_MARKER, EventBlock, PageFiles,
                                      blank_lines_dropped, event_blocks, event_heading,
                                      event_label, read_page_files)
from nxwright.project.page_text import expected_width, is_string_attribute, text_form_number
from nxwright.project.attribute_values import number_from_bytes
from nxwright.project.attribute_descriptions import allowed_number_bytes
from nxwright.language.resource_names import (ANIMATION, FONT, PICTURE, SOUND, VIDEO,
                                              ResourceNames)
from nxwright.language.nxlang import HOTSPOT, HOTSPOT_SIZE, TEXT, ProgramNames, compile_page

# Attributes holding a colour, stored as RGB565 (5 bits of red, 6 of green, 5
# of blue) and written as "#rrggbb".
COLOUR_ATTRIBUTES = frozenset({"bco", "bco1", "bco2", "pco", "pco1", "pco2", "borderc"})
# The ending of a page's file: an editor tells it from other TOML files by it.
PAGE_FILE_SUFFIX = ".page.toml"
# A TOML line `key = value`, of a page file or of app.toml: its key, then
# its value.
KEY_LINE = re.compile(r"\s*([A-Za-z0-9_]+)\s*=(.*)")
# Attributes that hold a picture or font ID, written by name in <page>.page.toml.
_REFERENCE_KINDS = {name: PICTURE for name in ("pic", "pic1", "pic2", "picc", "picc1", "picc2",
                                               "bpic", "ppic")}
_REFERENCE_KINDS["font"] = FONT
# A `vid` holds the ID of what its component plays, written by name too.
_PLAYED_KINDS = {TYPES_BY_NAME["gmov"]: ANIMATION, TYPES_BY_NAME["video"]: VIDEO,
                 TYPES_BY_NAME["audio"]: SOUND}
# Keys of a <page>.page.toml table that are not attributes.
_TABLE_KEYS = ("name", "type", "defaults", "events", "kept_events", "kept_attributes",
               "system_page", "locked",
               "lock_password_hash", "header_21")
# The keys of the [page] table that give the page header (page_header.py).
_HEADER_KEYS = ("system_page", "locked", "lock_password_hash", "header_21")
# Attributes the build derives (see _derived_values). A table gives one only
# when its stored value differs from the derived one.
_DERIVED = ("id", "objname", "endx", "endy")
# disup is an attribute of the Nextion Editors 1.60.1 and 1.63.3, which they
# read right after drag. The Nextion Editor 1.68.2, whose sample gives the
# defaults, has none. So a table may give it on a type that has drag, and
# the build puts it after drag.
_DISUP, _DRAG = "disup", "drag"
# Names are decoded as Latin-1. Latin-1 decodes any byte, so every name
# reaches the checks below, and the build writes it back byte for byte.
_NAME_ENCODING = "latin-1"
# The names a source folder can keep: any name that is not empty and has no
# double quote or control character. An event's heading puts a name in
# quotes when the name is not plain. A quoted name has no escapes, and must
# fit on one line (nx_files.event_heading). The Nextion Editor does not allow
# an empty name, a double quote, or a control character either.
_KEPT_NAME = re.compile(r'[^"\x00-\x1f]+')


def reference_kind(object_type, attribute: str):
    """Returns the kind of resource (resource_names.py) whose ID `attribute`
    holds in a component of type `object_type`, a number, or None when it
    holds none."""
    if attribute == "vid":
        return _PLAYED_KINDS.get(object_type)
    return _REFERENCE_KINDS.get(attribute)


@dataclass
class PageSource:
    """The text of a page's two source files, and the warnings of what
    page_to_source dropped making them."""
    toml: str
    events: str
    warnings: tuple = ()


def page_to_source(page: PageBlock, names: ResourceNames, defaults: dict,
                   encoding: str = DEFAULT_ENCODING,
                   keep_locks_without_password: bool = True) -> PageSource:
    """Returns the source files of `page`. `defaults` ({type number:
    TypeDefaults}) gives what can be left out. Its texts and code are in
    `encoding`, the project's character encoding. Its warnings name each
    event whose blank lines were dropped (_event_to_text).

    If `keep_locks_without_password` is false, a page locked with no password
    is written unlocked. The build adds that lock to every page anyway, so
    keeping it would only stop the page from being edited in VS Code.

    Raises NxwrightError when the page holds something the source files
    cannot represent, naming the page and object.
    """
    if page.header_size != HEADER_SIZE:
        raise NxwrightError("page %s: header size %d is not %d" % (page.name, page.header_size,
                                                                  HEADER_SIZE))
    if not page.objects:
        raise NxwrightError("page %s has no page object" % page.name)
    header = page_header_of(page)
    if not keep_locks_without_password and header.locked is True \
            and header.lock_password_hash == NO_LOCK_PASSWORD:
        header = replace(header, locked=False)
    codec = TextCodec(encoding)
    tables, headings, warnings = [], [], []
    for index, page_object in enumerate(page.objects):
        where = "page %s, object %d" % (page.name, index)
        # The page object takes its page's name, because the build writes
        # that name for it.
        content = _ObjectContent.read(page_object, index, where,
                                      page.name if index == 0 else None)
        table = {"name": content.name, "type": TYPE_NAMES.get(content.type, content.type)}
        if index == 0:
            table.update(_header_keys(header))
        type_defaults = defaults.get(content.type)
        stored = [item.name for item in page_object.items
                  if isinstance(item, Attribute) and item.name not in DERIVED_ATTRIBUTES]
        # Only a component with exactly its type's attributes can be shortened.
        # A disup after its drag is allowed too, and is then written.
        with_disup = None if type_defaults is None else _with_disup(type_defaults.attributes, b"")
        # The table of a component with an attribute kept as its stored bytes
        # lists every attribute. The raw value then keeps its place among them.
        shortened = type_defaults is not None and not any(
            _is_raw(item, content.type) or item.name in _TABLE_KEYS
            for item in content.attributes) and (
            stored == type_defaults.names()
            or with_disup is not None and stored == [name for name, _ in with_disup])
        default_values = dict(type_defaults.attributes) if shortened else {}
        event_names = [event.name for event in content.events]
        if not shortened:
            table["defaults"] = False
        if not shortened or event_names != type_defaults.events:
            table["events"] = event_names
        for attribute in content.attributes:
            if attribute.name in _TABLE_KEYS:
                # The attribute goes under kept_attributes, because the page
                # file would read the attribute's name as one of its own keys.
                # If two of these attributes have others between them, the
                # build writes them back next to each other, at the place of
                # the first.
                table.setdefault("kept_attributes", {})[attribute.name] = {
                    RAW_KEY: attribute.value.hex()}
            elif (attribute.name in _DERIVED or attribute.name in PLACEMENT_ATTRIBUTES
                    or default_values.get(attribute.name) != attribute.value):
                table[attribute.name] = _attribute_to_value(attribute, content.type, where, names,
                                                            codec)
        for event in content.events:
            if kept_as_lines(event, codec):
                table.setdefault("kept_events", {})[event.name] = {
                    "lines": [line.hex() for line in event.lines]}
        tables.append(table)
        for event in content.events:
            if kept_as_lines(event, codec):
                continue
            text, dropped = _event_to_text(content.name, event, where, codec)
            if text is not None:
                headings.append(text)
            if dropped:
                warnings.append(blank_lines_dropped(
                    "page %s, event %s.%s" % (page.name, content.name, event.name), dropped))
    return PageSource(page_file_text(tables), "\n".join(headings), tuple(warnings))


def page_from_source(source: PageSource, page_name: str, names: ResourceNames,
                     defaults: dict, nxlang_program: ProgramNames = None, page_id: int = 0,
                     globals_used: list = None, read=None, page_objects: dict = None,
                     encoding: str = DEFAULT_ENCODING, chain: list = None,
                     program_variables: frozenset = None, macros: frozenset = None,
                     absent_attributes: dict = None, screen: ScreenModel = None,
                     page_size: tuple = None, text_limits: dict = None,
                     cut_texts: list = None, defines: dict = None,
                     page_globals: dict = None) -> PageBlock:
    """Returns the page `page_name` built from its source files. Its stamp, a
    checksum of the page block, is left 0. Its texts, its code, and its header
    are in `encoding`, the project's character encoding (the Editor's
    default unless given).

    With `nxlang_program` (what program.nx declares), the events are in
    nxlang: they are compiled, the generated variables are added after the
    page's own components, and the program.s globals the page uses are added
    to `globals_used`, named after `page_id`. `read(path)` returns the text of
    a file the page includes.

    With `page_objects`, {page name: {object name: type}} of its page object
    and components, for every page of the app, every reference in the code
    must name a component of this page or, after its page's name, of
    another; and no line may assign to an attribute code cannot change. A
    page whose objects are None is not checked: they are unknown. With
    `absent_attributes` too, {page name: {name: {attribute: why}}}, no
    line may name an attribute a component lacks by its page file's
    values, such as a variable's `val` while it holds a text (ObjectNames).
    With `page_globals` too, {page name: the names of its components of
    global scope}, code can use another page's component only if it is of
    global scope (ObjectNames.reachable).

    In the Editor's own language, with `program_variables`, program.nx's int
    variables, the code may name sys0, sys1, and sys2 only when they are
    among them. The Editor refuses it otherwise. nxlang's compiler checks
    every name itself. With `macros`, the folder's macros' names, a `call`
    must name one of them (macros_source.py). With `screen`, the folder's
    screen model, in either language, no line may use a command or a
    system variable its series lacks (code_checks.series_lacks). With
    `page_size`, the screen's size at its rotation, the page gets the
    screen's place and size, whatever its page file says
    (page_table_at_screen).

    In nxlang, each text that a generated variable may cut is added to
    `cut_texts`, when given, as (file, line, message). This needs
    `text_limits`, the most bytes of the pages' texts, keyed as the code
    writes them (code_text_limits). The page's
    longest chain of calls and clicks is added to `chain`, when given: the
    event first, as "home.load", then each function or event that runs during
    the one before it.

    Raises NxwrightError naming the file and the problem. Its `file` is the
    file at fault, the page's .page.toml file unless the code is; for a table of
    the .toml file, `table` says which.
    """
    try:
        return _page_from_source(source, page_name, names, defaults, nxlang_program, page_id,
                                 globals_used, read, page_objects, encoding, chain,
                                 program_variables, macros, absent_attributes, screen,
                                 page_size, text_limits, cut_texts, defines, page_globals)
    except NxwrightError as error:
        error.file = error.file or page_toml_path(page_name)
        raise


# The keys that identify a page file's table. They cannot be placeholders,
# because the language server's index and the code checks read them as
# written.
_FIXED_KEYS = ("name", "type")


def page_data(text: str, page_name: str, defines: dict) -> dict:
    """Parses the page file `text` of the page `page_name`, and returns it
    with each placeholder filled in from app.toml's `defines`
    (defines.filled). Every reader of a page file's values reads it through
    this function. Raises tomllib.TOMLDecodeError if `text` is not TOML, so
    that each caller can word its own message. Raises NxwrightError for a
    placeholder that cannot be filled in. The error names the table, and its
    `table` is the table's index, 0 for [page]."""
    data = tomllib.loads(text)
    if not defines:
        return data
    path = page_toml_path(page_name)

    def table_filled(table, index: int):
        if not isinstance(table, dict):
            return table
        try:
            return filled(table, defines, _FIXED_KEYS,
                          "%s, %s" % (path, table.get("name", "table %d" % index)))
        except NxwrightError as error:
            error.table = index
            raise

    if "page" in data:
        data["page"] = table_filled(data["page"], 0)
    if isinstance(data.get("component"), list):
        data["component"] = [table_filled(table, index)
                             for index, table in enumerate(data["component"], 1)]
    return data


def _page_from_source(source: PageSource, page_name: str, names: ResourceNames, defaults: dict,
                      nxlang_program: ProgramNames, page_id: int, globals_used: list, read,
                      page_objects: dict, encoding: str, chain: list,
                      program_variables: frozenset, macros: frozenset,
                      absent_attributes: dict, screen: ScreenModel,
                      page_size: tuple, text_limits: dict, cut_texts: list,
                      defines: dict, page_globals: dict) -> PageBlock:
    """Does the work of page_from_source."""
    try:
        data = page_data(source.toml, page_name, defines)
    except tomllib.TOMLDecodeError as error:
        raise NxwrightError("%s.page.toml: %s" % (page_file_stem(page_name), error)) from None
    page_table, components = data.get("page"), data.get("component", [])
    if not isinstance(page_table, dict):
        raise NxwrightError("%s.page.toml has no [page] table" % page_file_stem(page_name))
    if set(data) - {"page", "component"} or not isinstance(components, list):
        raise NxwrightError("%s.page.toml can contain only [page] and [[component]] tables"
                            % page_file_stem(page_name))
    if page_table.get("name") != page_name:
        raise NxwrightError("%s.page.toml gives the page the name %r"
                            % (page_file_stem(page_name), page_table.get("name")))
    page_table = page_table_at_screen(page_table, page_size, defaults)
    header = _page_header(page_table, components, page_name)
    codec = TextCodec(encoding)
    tables = [page_table] + components
    page_file_tables = len(tables)
    # The code is compiled against the tables' names, so a name that is no
    # name, as a table being typed may hold, is refused first, as below.
    for index, table in enumerate(tables):
        if isinstance(table, dict) and not isinstance(table.get("name"), (str, type(None))):
            try:
                _table_header(table, "%s.page.toml, object %d"
                              % (page_file_stem(page_name), index))
            except NxwrightError as error:
                error.table = index
                raise
    if nxlang_program is None:
        objects = None
        if page_objects is not None:
            objects = ObjectNames(frozenset(table.get("name") for table in tables), page_objects,
                                  page_name, page_globals, absent_attributes)
        code = _parse_events(source.events, page_name, names, codec,
                             [table.get("name") for table in tables], objects,
                             program_variables, macros, screen)
    else:
        code, generated, used, deepest, cuts = _compile_nxlang_events(
            source.events, page_name, names, [table.get("name") for table in tables],
            nxlang_program, page_id, read, codec, events_of_page_tables(tables, defaults),
            page_objects, {**(page_objects or {}), page_name: table_types(tables)},
            absent_attributes, screen, text_limits, page_globals)
        if cut_texts is not None:
            cut_texts.extend(cuts)
        if globals_used is not None:
            globals_used.extend(used)
        if chain is not None:
            chain.extend(deepest)
        tables += [generated_table(variable) for variable in generated]
    object_names = [table.get("name") for table in tables]
    # Checked before the objects are made, because making an object past ID
    # 255 fails.
    check_component_count(object_names, len(tables) - page_file_tables,
                          "%s.page.toml" % page_file_stem(page_name))
    if len(set(object_names)) != len(object_names):
        raise NxwrightError("%s.page.toml: two objects are named %s"
                            % (page_file_stem(page_name),
                               next(name for name in object_names if object_names.count(name) > 1)))
    objects = []
    for index, table in enumerate(tables):
        try:
            objects.append(_object_from_table(table, index, code, names, defaults, codec,
                                              "%s.page.toml, object %d"
                                              % (page_file_stem(page_name), index)))
        except NxwrightError as error:
            error.table = index
            raise
    if code:
        name, event = next(iter(code))
        if nxlang_program is not None and (name, event) == (page_name, "load"):
            # The build puts the functions' tsw lines there.
            raise NxwrightError("%s.page.toml: functions need the page's load event, but the "
                                "page's events do not include it" % page_file_stem(page_name))
        raise NxwrightError("%s.nx: %s.%s is not an event listed in the page's .page.toml file"
                            % (page_file_stem(page_name), name, event))
    page = PageBlock(name=page_name, header_size=HEADER_SIZE,
                     unknown_16=header_16(header),
                     unknown_40=header_40(encoding_code(encoding)), objects=objects)
    check_page_limits(page, "%s.page.toml" % page_file_stem(page_name))
    _check_fonts(page, names, page_name)
    return page


def _check_fonts(page: PageBlock, names: ResourceNames, page_name: str):
    """Raises NxwrightError for a component whose font, given or its type's
    default, is none of the project's fonts, which the Editor's compile
    refuses ("Invalid Font ID"). Seen on texts in a project with no fonts, and
    taken to hold for every type with a font."""
    for index, page_object in enumerate(page.objects):
        stored = page_object.attribute("font")
        font = None if stored is None else int.from_bytes(stored, "little")
        if font is None or font < len(names.fonts):
            continue
        error = NxwrightError(
            "%s.page.toml: component %s: its font is number %d, and the project has %s; the "
            "Nextion Editor refuses it, saying \"Invalid Font ID\". `nxwright font` adds one" % (
                page_file_stem(page_name),
                (page_object.attribute("objname") or b"").decode("latin-1"), font,
                "%d fonts" % len(names.fonts) if names.fonts else "no fonts"))
        error.table = index
        raise error


@dataclass
class _ObjectContent:
    """One object of a page, checked against the shape the source files assume:
    a marker giving the number of attributes, such as "att-39", then the
    attributes, then the events."""
    name: str
    type: int
    attributes: list     # in stored order, without type and those equal to their derived value
    events: list

    @classmethod
    def read(cls, page_object: PageObject, index: int, where: str,
             page_name: str = None) -> "_ObjectContent":
        """Returns the content of `page_object`, the object at `index` on its
        page, in the form the source files keep it. Records out of their
        usual order are read anyway. If an attribute or an event appears
        twice, the last one is kept. Records of other kinds are left out.
        object_irregularities reports each of these cases. If `page_name` is
        given, the page object takes the page's name.

        Raises NxwrightError, starting with `where`, for an object without its
        type, ID, or name, which nxwright cannot read as an object.
        """
        items = page_object.items
        # A TOML table can contain each key only once, and a .nx file has one
        # heading for each event. For an attribute or an event given twice,
        # the last one is kept, in the place of the first.
        attributes = {}
        for item in items:
            if isinstance(item, Attribute):
                attributes[item.name] = item
        event_by_name = {}
        for item in items:
            if isinstance(item, Event):
                event_by_name[item.name] = item
        events = list(event_by_name.values())
        if any(name not in attributes for name in ("type", "id", "objname")) \
                or len(attributes["type"].value) != 1:
            raise NxwrightError("%s: the object has no type, id, or objname, so nxwright cannot "
                                "read it" % where)
        if page_name is not None:
            attributes["objname"] = Attribute("objname", page_name.encode(_NAME_ENCODING))
        attributes = ([attributes[name] for name in ("type", "id", "objname")]
                      + [attribute for name, attribute in attributes.items()
                         if name not in ("type", "id", "objname")])
        objname = attributes[2].value.decode(_NAME_ENCODING)
        if not objname:
            raise NxwrightError("%s: name '' is empty" % where)
        if not _KEPT_NAME.fullmatch(objname):
            raise NxwrightError("%s: name %r has a double quote or a control character, which "
                                "a source folder cannot keep" % (where, objname))
        values = {attribute.name: attribute.value for attribute in attributes}
        derived = _derived_values(index, objname, values)
        kept = [attribute for attribute in attributes[1:]
                if derived.get(attribute.name) != attribute.value]
        return cls(objname, attributes[0].value[0], kept, events)


def _derived_values(index: int, name: str, values: dict) -> dict:
    """Returns the derivable attributes' values as stored bytes, given the
    object's other attribute values (bytes, by name)."""
    derived = {"objname": name.encode(_NAME_ENCODING)}
    # IDs are stored in one byte; a larger index cannot be derived and is kept as stored.
    if index < 256:
        derived["id"] = bytes([index])
    if "h" in values:
        for end, start, size in (("endx", "x", "w"), ("endy", "y", "h")):
            number = int.from_bytes(values[start], "little") + int.from_bytes(values[size], "little") - 1
            derived[end] = (number & 0xFFFF).to_bytes(2, "little")
    return derived


# The key of an attribute's raw form in a page file, such as { bytes = "01" }.
# The raw form gives the attribute's stored bytes in hexadecimal. It keeps an
# attribute that nxwright does not know, or one stored at a width other than
# nxwright's tables give. A newer Nextion Editor may write either. The build
# writes the bytes back as they are.
RAW_KEY = "bytes"


def _is_raw(attribute: Attribute, object_type: int) -> bool:
    """Returns whether `attribute`, on an object of type `object_type`, is a
    number attribute kept in its raw form. That is the case if nxwright's
    tables give it no width, or a width other than the one it is stored at.
    unknown_content.py makes the same test."""
    return (not is_string_attribute(object_type, attribute.name)
            and len(attribute.value) != expected_width(object_type, attribute.name))


def _attribute_to_value(attribute: Attribute, object_type: int, where: str, names: ResourceNames,
                        codec: TextCodec):
    """Returns an attribute's value as <page>.page.toml writes it: a string, a
    resource's name, a "#rrggbb" colour, or a number."""
    if is_string_attribute(object_type, attribute.name):
        # A text whose bytes are not valid in the project's encoding is kept
        # as its stored bytes.
        if not codec.keeps(attribute.value):
            return {RAW_KEY: attribute.value.hex()}
        return codec.decode(attribute.value, "%s: %s" % (where, attribute.name))
    if _is_raw(attribute, object_type):
        return {RAW_KEY: attribute.value.hex()}
    number = number_from_bytes(attribute.value)
    kind = reference_kind(object_type, attribute.name)
    if kind and names.name_of(kind, number) is not None:
        return names.name_of(kind, number)
    if attribute.name in COLOUR_ATTRIBUTES:
        return rgb565_to_hex(number)
    return number


def _event_to_text(name: str, event: Event, where: str, codec: TextCodec) -> tuple:
    """Returns (one event as the .nx file holds it: its comment, its heading,
    then its code, indented; how many blank lines it dropped). The text is
    None for an event with no code. The build drops blank lines, so the .nx
    file could not give them back, and they compile to nothing."""
    texts, dropped = [], 0
    for line in event.lines:
        text = codec.decode(line, "%s: event %s" % (where, event.name))
        if not text.strip():
            dropped += 1
            continue
        if any(ord(char) < 0x20 and char != "\t" or ord(char) == 0x7f for char in text):
            raise NxwrightError("%s: event %s has a control character in its code" % (where, event.name))
        texts.append(text)
    if not texts:
        return None, dropped
    # The marked lines the event starts with are its comment, above its heading.
    start = 0
    while start < len(texts) and texts[start].startswith(EVENT_COMMENT_MARKER):
        start += 1
    lines = (["//" + text[len(EVENT_COMMENT_MARKER):] for text in texts[:start]]
             + [event_heading(name, event.name)] + [CODE_INDENT + text for text in texts[start:]])
    return "\n".join(lines) + "\n", dropped


def kept_as_lines(event: Event, codec: TextCodec) -> bool:
    """Returns whether `event` is kept in its page file as its stored lines,
    rather than in a .nx file. That is the case if a line of its code is not
    valid text in the project's encoding, `codec`, or has a control
    character other than a tab, such as DEL, which a .nx file cannot contain. The finder
    of unknown content uses this function too (object_irregularities)."""
    for line in event.lines:
        if not codec.keeps(line):
            return True
        text = codec.decode(line, "")
        if any(ord(char) < 0x20 and char != "\t" or ord(char) == 0x7f for char in text):
            return True
    return False


def object_irregularities(page_object: PageObject, index: int, page_name: str,
                          codec: TextCodec = None) -> list:
    """Returns the parts of the object `page_object`, at `index` on the page
    `page_name`, that the page files do not keep as they are. Each part is a
    tuple (sort, what, where in the object, bytes), with one of the sorts in
    content_sorts.py. `codec` is the codec of the project's encoding. If
    `codec` is None, the object's texts and events are not checked.
    _ObjectContent.read and page_to_source handle each part as its sort
    describes, so the finder of unknown content and the conversion agree."""
    items = page_object.items
    attributes = [item for item in items if isinstance(item, Attribute)]
    events = [item for item in items if isinstance(item, Event)]
    names = [attribute.name for attribute in attributes]
    if not all(name in names for name in ("type", "id", "objname")) or len(
            [attribute for attribute in attributes if attribute.name == "type"][-1].value) != 1:
        return [(CANNOT_BE_KEPT, "an object without its type, ID, or name", "records", b"")]
    found = [(MAY_BE_LOST, "a record of a kind the page files do not keep", "records", b"")
             for item in items[1:] if not isinstance(item, (Attribute, Event))][:1]
    if items[0] != Marker(b"att-%d" % len(attributes)) or not _in_usual_order(items):
        found.append((WRITTEN_OTHERWISE, "an object's records out of their usual order",
                      "records", b""))
    for kind, given in (("attribute", names), ("event", [event.name for event in events])):
        found += [(MAY_BE_LOST, "an %s given twice, of which the source folder keeps the last"
                   % kind, "%s %s" % (kind, name), b"")
                  for name in sorted({name for name in given if given.count(name) > 1})]
    object_type = [attribute for attribute in attributes if attribute.name == "type"][-1].value[0]
    for attribute in attributes:
        # The table's own type key stands for the type attribute.
        if attribute.name in _TABLE_KEYS and attribute.name != "type":
            found.append((KEPT, "an attribute named like a key of the page file",
                          "attribute " + attribute.name, attribute.value))
        elif codec is not None and is_string_attribute(object_type, attribute.name) \
                and not codec.keeps(attribute.value):
            found.append((KEPT, "a text not valid in the project's encoding",
                          "attribute " + attribute.name, attribute.value))
    if codec is not None:
        # If an event appears twice, the conversion keeps the last one, and
        # so does this check.
        kept_events = {event.name: event for event in events}.values()
        found += [(KEPT, "an event whose code a .nx file cannot contain, kept as its lines",
                   "event " + event.name, b"") for event in kept_events
                  if kept_as_lines(event, codec)]
    objname = [attribute for attribute in attributes if attribute.name == "objname"][-1].value
    if index == 0 and objname != page_name.encode(_NAME_ENCODING):
        found.append((WRITTEN_OTHERWISE, "a page object not named after its page", "objname",
                      objname))
    return found


def _in_usual_order(items: list) -> bool:
    """Returns whether an object's records `items` are in the order the
    build writes them. That order is a marker, then the attributes, then the
    events. The attributes start with type, id, and objname, and endx and
    endy come right after h."""
    attributes = [item for item in items if isinstance(item, Attribute)]
    events = [item for item in items if isinstance(item, Event)]
    names = [attribute.name for attribute in attributes]
    after_h = names[names.index("h") + 1:names.index("h") + 3] if "h" in names else []
    return (isinstance(items[0], Marker) and items[1:] == attributes + events
            and names[:3] == ["type", "id", "objname"]
            and (("h" in names) == ("endx" in names)) and ("h" not in names
                                                          or after_h == ["endx", "endy"]))


def _kept_attributes(value, where: str) -> dict:
    """Returns {attribute: stored bytes} from a table's kept_attributes.
    These are the attributes named like a key of the page file, each in its
    raw form."""
    if not isinstance(value, dict) or not all(isinstance(raw, dict) for raw in value.values()):
        raise NxwrightError("%s: kept_attributes must give each attribute's stored bytes, as "
                            "{ events = { %s = \"05\" } }" % (where, RAW_KEY))
    return {key: _raw_bytes(key, raw, where) for key, raw in value.items()}


def _kept_events(value, events: list, code: dict, name: str, where: str) -> dict:
    """Returns {event: the stored bytes of its lines} from a table's
    kept_events, the events kept as their lines (kept_as_lines). Each event
    must be one of the object's events, and must not also have a heading in
    a .nx file."""
    if not isinstance(value, dict) or not all(
            isinstance(kept, dict) and set(kept) == {"lines"} and isinstance(kept["lines"], list)
            and all(isinstance(line, str) for line in kept["lines"]) for kept in value.values()):
        raise NxwrightError("%s: kept_events must give each event's lines in hexadecimal, as "
                            "{ load = { lines = [\"7072696e7420310d\"] } }" % where)
    kept = {}
    for event, given in value.items():
        if event not in (events or []):
            raise NxwrightError("%s: kept_events gives code for %s, which is not in events"
                                % (where, event))
        if (name, event) in code:
            raise NxwrightError("%s: event %s is kept in the page file, and has a heading in a "
                                ".nx file too; remove one" % (where, event))
        try:
            kept[event] = [bytes.fromhex(line) for line in given["lines"]]
        except ValueError:
            raise NxwrightError("%s: kept_events' lines of %s must be hexadecimal digits"
                                % (where, event)) from None
    return kept


def page_file_text(tables: list) -> str:
    """Returns the text of <page>.page.toml from its tables, dicts of their
    values: the first as [page], the others as [[component]], each after a
    blank line. The headers are written here, as tomli-w writes a list of
    tables as an array of inline ones."""
    return "\n".join(("[page]" if index == 0 else "[[component]]") + "\n" + _table_text(table)
                     for index, table in enumerate(tables))


def _table_text(table: dict) -> str:
    """Returns one table's keys as tomli-w writes them, except for a value
    in its raw form. That value is written in its place as an inline table,
    such as newattr = { bytes = "01" }. tomli-w would write it after the
    other keys, as a table of its own."""
    if not any(isinstance(value, dict) for value in table.values()):
        return tomli_w.dumps(table)
    return "".join("%s = %s\n" % (_toml_key(key), _inline(value))
                   if isinstance(value, dict) else tomli_w.dumps({key: value})
                   for key, value in table.items())


def _toml_key(key: str) -> str:
    """Returns `key` as TOML writes it: bare, or in quotes if needed."""
    return tomli_w.dumps({key: 0})[:-len(" = 0\n")]


def _inline(value) -> str:
    """Returns `value`, a table, a list, a text, or a number, as an inline
    TOML value, on one line, such as { bytes = "01" }."""
    if isinstance(value, dict):
        return "{ %s }" % ", ".join("%s = %s" % (_toml_key(key), _inline(item))
                                    for key, item in value.items())
    if isinstance(value, list):
        return "[%s]" % ", ".join(_inline(item) for item in value)
    return tomli_w.dumps({"v": value})[len("v = "):-1]


def editor_code_of_block(block: EventBlock, page_name: str, names: ResourceNames, owner: Owner,
                         objects: ObjectNames = None, variables: frozenset = None,
                         macros: frozenset = None, screen: ScreenModel = None,
                         codec: TextCodec = None) -> list:
    """Returns the block's code in Editor syntax, one string per line, its
    comment first. `owner` is the object whose event it is, None when the
    page has none of that name. With `objects`, its references are checked,
    with `variables`, its names of program.nx's variables, with `macros`,
    its calls, with `screen`, what its series lacks, and with `codec`, its
    lines' lengths (preprocess)."""
    try:
        return block.marked_comment() + preprocess(block.code_lines(), names, objects, variables,
                                                   macros, screen, owner, codec=codec,
                                                   suggest_nxlang=True)
    except NxwrightError as error:
        raise error.in_file(page_nx_path(page_name),
                            shown="%s.nx" % page_file_stem(page_name)) from None


def table_types(tables: list) -> dict:
    """Returns the types of a page's objects, {name: type}, from its page
    file's tables: the page's, then its components'. A table whose name is
    not text, as one being typed may hold, is left out, for its own check to
    report (_table_header)."""
    return {table.get("name"): table.get("type") for table in tables
            if isinstance(table, dict) and isinstance(table.get("name"), (str, type(None)))}


def page_nx_path(page_name: str) -> str:
    """Returns the source folder path of a page's own .nx file. The page's
    name in the path is encoded by page_file_names.page_file_stem."""
    return "pages/%s.nx" % page_file_stem(page_name)


def page_toml_path(page_name: str) -> str:
    """Returns the source folder path of a page's file, `<page>.page.toml`.
    The page's name in the path is encoded by page_file_names.page_file_stem."""
    return "pages/%s%s" % (page_file_stem(page_name), PAGE_FILE_SUFFIX)


def _no_includes(path: str) -> str:
    """Raises NxwrightError for any include: the `read` used when there is no
    source folder."""
    raise NxwrightError("%s: no source folder to read included files from" % path)


def events_of_page_tables(tables: list, defaults: dict) -> frozenset:
    """Returns the events that the objects of a page's `tables` have, as
    {(object name, event)}: those a table's `events` lists, or for a table
    without `events`, its type's events in `defaults`, the folder's
    defaults.toml. A table marked defaults = false has only those it lists.
    A table the build rejects is left out, as the build reports it."""
    found = set()
    for table in tables:
        if not isinstance(table, dict):
            continue
        try:
            name, object_type, events, full = _table_header(table, "")
        except NxwrightError:
            continue
        if events is None and not full and object_type in defaults:
            events = defaults[object_type].events
        found.update((name, event) for event in events or [])
    return frozenset(found)


def _compile_nxlang_events(text: str, page_name: str, names: ResourceNames, component_names: list,
                           program: ProgramNames, page_id: int, read, codec: TextCodec,
                           page_events: frozenset, page_objects: dict = None,
                           object_types: dict = None, absent_attributes: dict = None,
                           screen: ScreenModel = None, text_limits: dict = None,
                           page_globals: dict = None) -> tuple:
    """Returns ({(object name, event): [code line bytes]}, [Generated] for the
    generated variables, [the program.s globals used], the longest chain of
    calls and clicks, [(file, line, message)] of the texts a generated
    variable may cut) for a page's .nx file in nxlang. `page_events` gives
    the events the page has (events_of_page_tables), as compile_page_files
    takes them. `text_limits` gives
    the most bytes of the pages' texts, keyed as the code writes them
    (code_text_limits), which those warnings need. With
    `page_objects`, references, calls, and assignments are checked as
    page_from_source describes (ObjectNames). The checks use
    `absent_attributes` for the attributes components lack, `page_globals`
    for each page's components of global scope, and `screen` for what its
    series lacks.
    `object_types` gives the types of the pages' objects nxlang compiles
    with, {page: {name: type}} (nxlang.compile_page)."""
    page_files = read_page_files(page_nx_path(page_name), text, read or _no_includes)
    compiled = compile_page_files(page_files, page_name, component_names, program, page_id,
                                  object_types, codec=codec, text_limits=text_limits,
                                  page_events=page_events)
    code = {}
    objects = None
    if page_objects is not None:
        own = frozenset(component_names) | {variable.name for variable in compiled.generated}
        objects = ObjectNames(own, page_objects, page_name, page_globals, absent_attributes)
    for key, lines in preprocess_compiled(compiled, page_name, names, objects=objects,
                                          screen=screen, codec=codec).items():
        where = "%s: %s.%s" % (compiled.sources.get(key, page_nx_path(page_name)), *key)
        code[key] = [codec.encode(line, where) for line in lines]
    return code, compiled.generated, compiled.globals, compiled.deepest_chain, compiled.cut_texts


def editor_code_of_file(path: str, page_name: str, events_text: str, names: ResourceNames,
                        component_names: list, program: ProgramNames, page_id: int, read,
                        object_types: dict = None, codec: TextCodec = None, *,
                        page_events: frozenset) -> list:
    """Returns [(title, [(line, Editor code line)])] of the events and the
    functions that the .nx file `path` defines, as page `page_name` compiles
    them, its own .nx file's text being `events_text`. A title is as
    "on save.up" or "function show"; `line` is the line of `path` that the
    Editor line comes from, counted from 1, or 0 for a line the compiler
    adds. With `program`, what program.nx declares, the code is nxlang, and
    only the functions the page calls are compiled; without it, the code is
    in the Editor's own language. `read(path)` returns an included file.
    `object_types` gives the types of the pages' objects nxlang compiles
    with, {page: {name: type}}, and `codec` the project's encoding
    (nxlang.compile_page). `page_events` gives the events the page has,
    as compile_page_files takes them.

    Raises NxwrightError as the build does."""
    if program is None:
        text = events_text if path == page_nx_path(page_name) else read(path)
        sections = []
        for key, block in event_blocks(text, path).items():
            comment = [(number, marked) for (number, _), marked
                       in zip(block.comment, block.marked_comment())]
            sections.append((event_label(*key),
                             preprocess_with_places(comment + block.code_lines(), names,
                                                    owner=Owner.among(key[0],
                                                                      component_names))))
        return sections
    compiled = compile_nxlang_page(events_text, page_name, component_names, program, page_id,
                                   read, object_types, codec=codec, page_events=page_events)
    sections = [(event_label(*key), preprocess_with_places(lines, names))
                for key, lines in compiled.events.items() if compiled.sources.get(key) == path]
    sections += [("function " + name, preprocess_with_places(compiled.bodies[name], names))
                 for name, function in compiled.functions.items() if function.file == path]
    return sections


def compile_nxlang_page(text: str, page_name: str, component_names: list, program: ProgramNames,
                        page_id: int = 0, read=None, object_types: dict = None,
                        own_attributes: bool = True, codec: TextCodec = None,
                        text_limits: dict = None, *, page_events: frozenset):
    """Returns the CompiledPage of a page's .nx text and the files it
    includes, as compile_page_files compiles them."""
    page_files = read_page_files(page_nx_path(page_name), text, read or _no_includes)
    return compile_page_files(page_files, page_name, component_names, program, page_id,
                              object_types, own_attributes, codec, text_limits,
                              page_events=page_events)


def compile_page_files(page_files: PageFiles, page_name: str, component_names: list,
                       program: ProgramNames, page_id: int = 0, object_types: dict = None,
                       own_attributes: bool = True, codec: TextCodec = None,
                       text_limits: dict = None, *, page_events: frozenset):
    """Returns the CompiledPage of a page's .nx files. The compiler sees only
    code lines, so each event's comment is put back at its start, marked as
    the build writes it.

    `page_events` gives the events the page has, {(object name, event)}
    (events_of_page_tables). The events of included files whose objects are
    not among `component_names` are left out before compiling, so that
    their code, and the functions only they call, are not part of the page
    (PageFiles.without_events). An event of an included file whose object
    is on the page, but does not have that event, is refused. None keeps
    every event, for a page without a page file.

    `object_types` gives the types of the pages'
    objects nxlang compiles with, {page: {name: type}}
    (nxlang.compile_page). An event of an object among `component_names`,
    the page's objects in ID order, the unnamed included, may name its
    attributes as '&name&'; with `own_attributes` False, none may, as code
    that runs in no object's event. `codec` is the project's encoding, and
    `text_limits` the most bytes of the pages' texts, as nxlang.compile_page
    takes them."""
    if page_events is not None:
        _refuse_included_events_the_page_lacks(page_files, page_name, component_names,
                                               page_events)
        page_files = page_files.without_events(frozenset(component_names))
    events, functions, comments = {}, {}, {}
    for nx_file in page_files.files:
        for key, block in nx_file.blocks.items():
            if key[0] is None:
                functions[key[1]] = (nx_file.path, block.number, block.heading, block.code_lines())
            else:
                events[key] = (nx_file.path, block.code_lines())
                if block.comment:
                    comments[key] = [(number, marked) for (number, _), marked
                                     in zip(block.comment, block.marked_comment())]
    owners = ({key: Owner.among(key[0], component_names) for key in events}
              if own_attributes else {})
    compiled = compile_page(page_name, [name for name in component_names if name], program,
                            page_files.preambles(), events, functions, page_id, object_types,
                            owners, codec, text_limits)
    for key, comment in comments.items():
        compiled.events[key] = comment + compiled.events.get(key, [])
    return compiled


def _refuse_included_events_the_page_lacks(page_files: PageFiles, page_name: str,
                                           component_names: list, page_events: frozenset):
    """Raises NxwrightError, at its heading, for an event of an included file
    whose object is on the page but does not have that event, and for one
    whose object is not on the page when a line including the file says
    `strict`. The page's own file, the last of `files`, is checked later,
    against the page file's tables (_page_from_source)."""
    on_page = frozenset(component_names)
    own = page_files.files[-1]
    for nx_file in page_files.files[:-1]:
        strict = [(including.path, number) for including in [own] + page_files.files[:-1]
                  for number, included in including.includes
                  if included == nx_file.path and included in including.strict]
        for key, block in nx_file.blocks.items():
            # A function's key has no object; an unnamed table's name is None.
            if key[0] is None:
                continue
            if key[0] in on_page and key not in page_events:
                raise NxwrightError("%s includes this file, but %s.%s is not an event listed in %s"
                                    % (page_name, key[0], key[1], page_toml_path(page_name)),
                                    file=nx_file.path, line=block.number)
            if key[0] not in on_page and strict:
                raise NxwrightError("%s has no %s, and line %d of %s includes this file with "
                                    "strict" % (page_name, key[0], strict[0][1], strict[0][0]),
                                    file=nx_file.path, line=block.number)


def preprocess_compiled(compiled, page_name: str, names: ResourceNames,
                        objects: ObjectNames = None,
                        screen: ScreenModel = None, codec: TextCodec = None) -> dict:
    """Returns {key: Editor code} of a compiled page's events. With
    `objects`, references are checked, with `screen`,
    what its series lacks, and with `codec`, the lines' lengths. Errors
    name the .nx file holding the code at fault."""
    out = {}
    for key, lines in compiled.events.items():
        try:
            out[key] = preprocess(lines, names, objects, screen=screen, codec=codec)
        except NxwrightError as error:
            # in_file keeps the type, which tells an unknown name apart from other problems.
            raise error.in_file(file_at_fault(compiled, key, page_name, names, objects,
                                              screen, codec)) from None
    return out


def file_at_fault(compiled, key, page_name: str, names: ResourceNames,
                  objects: ObjectNames = None, screen: ScreenModel = None,
                  codec: TextCodec = None) -> str:
    """Returns the .nx file holding the code of `key` that does not preprocess.
    A hotspot's event holds several functions: the one at fault is found by
    preprocessing each body alone."""
    if key in compiled.sources:
        return compiled.sources[key]
    for name, function in compiled.functions.items():
        if function.hotspot == key[0]:
            try:
                preprocess(compiled.bodies[name], names, objects, screen=screen, codec=codec)
            except NxwrightError:
                return function.file
    return page_nx_path(page_name)


def table_limits(toml_tables: list, defaults: dict) -> dict:
    """Returns {"name.attribute": the most bytes it keeps} of a page file's
    `toml_tables` that have a name: a `txt`'s `txt_maxl`, and each `X`'s
    `X_m`, as a `path`'s `path_m` (editor_limits.bounded_attributes). Each
    limit is the table's own, or else its type's, from `defaults`. A table
    whose type is not a string, as in a malformed page file, gives no limits.
    The page's build refuses it."""
    limits = {}
    for table in toml_tables:
        if "name" not in table or not isinstance(table.get("type"), str):
            continue
        object_type = TYPES_BY_NAME.get(table.get("type"))
        type_defaults = defaults.get(object_type)
        stored = dict(type_defaults.attributes) if type_defaults is not None else {}
        for attribute, bound in bounded_attributes(object_type, {*table, *stored}):
            limit = table.get(bound)
            if limit is None and bound in stored:
                limit = int.from_bytes(stored[bound], "little")
            if isinstance(limit, int):
                limits["%s.%s" % (table["name"], attribute)] = limit
    return limits


def code_text_limits(limits: dict, page: str) -> dict:
    """Returns {text as the code of `page` writes it: its most bytes}, from
    `limits`, which is {page: {"name.attribute": its most bytes}}
    (table_limits). The page's own texts are written alone, as `t0.txt`, and
    another page's after that page's name, as `second.t0.txt`. A page whose
    limits are None, such as a page whose file cannot be read, adds nothing."""
    found = {}
    for name, own in limits.items():
        prefix = "" if name == page else name + "."
        found.update((prefix + text, most) for text, most in (own or {}).items())
    return found


def generated_table(variable) -> dict:
    """Returns the <page>.page.toml table of a generated variable: a hotspot for a
    function, otherwise a variable, which holds text when its kind is TEXT."""
    if variable.kind == HOTSPOT:
        return {"name": variable.name, "type": "hotspot", "x": 0, "y": 0, "w": HOTSPOT_SIZE,
                "h": HOTSPOT_SIZE}
    table = {"name": variable.name, "type": "variable"}
    if variable.kind == TEXT:
        table.update(sta=1, txt="", txt_maxl=variable.room)
    return table


def _parse_events(text: str, page_name: str, names: ResourceNames, codec: TextCodec,
                  object_names: list, objects: ObjectNames = None, variables: frozenset = None,
                  macros: frozenset = None, screen: ScreenModel = None) -> dict:
    """Returns {(object name, event): [code line bytes]} from a page's .nx file,
    in Editor syntax, checked as editor_code_of_block says. `object_names` are the
    page's, in ID order, the page's first."""
    code = {}
    for key, block in event_blocks(text, page_nx_path(page_name)).items():
        where = "%s.nx: %s.%s" % (page_file_stem(page_name), *key)
        code[key] = [codec.encode(line, where)
                     for line in editor_code_of_block(block, page_name, names,
                                                      Owner.among(key[0], object_names), objects,
                                                      variables, macros, screen, codec)]
    return code


def _object_from_table(table: dict, index: int, code: dict, names: ResourceNames,
                       defaults: dict, codec: TextCodec, where: str,
                       whole_checks: bool = True) -> PageObject:
    """Rebuilds one object, taking its event code out of `code`. With
    `whole_checks`, it also refuses the object as a whole, as the build
    does: a keyboard bound to a component of local scope, and a component
    narrower or lower than LEAST_SIDE.

    A table marked "defaults = false" lists every attribute, in stored order.
    Any other table leaves out what equals its type's defaults; those are
    filled in, in the defaults' order.
    """
    name, object_type, events, full = _table_header(table, where)
    given = {}
    for key, value in table.items():
        if key == "kept_attributes":
            given.update(_kept_attributes(value, where))
        elif key not in _TABLE_KEYS:
            given[key] = _value_to_bytes(key, value, object_type, names, codec, where)
    if full:
        attributes = [Attribute(key, value) for key, value in given.items()]
    else:
        type_defaults = defaults.get(object_type)
        if type_defaults is None:
            raise NxwrightError("%s: type %s has no defaults in defaults.toml; add its section "
                                "there, as nxwright defaults writes it from a sample project"
                                % (where, TYPE_NAMES.get(object_type, object_type)))
        defaults_order = type_defaults.attributes
        if _DISUP in given:
            defaults_order = _with_disup(defaults_order, given[_DISUP]) or defaults_order
        known = [key for key, _ in defaults_order]
        unknown = [key for key in given if key not in known and key not in _DERIVED]
        if unknown:
            raise NxwrightError("%s: type %s has no attribute %s"
                                % (where, TYPE_NAMES.get(object_type, object_type), unknown[0]))
        # A type's defaults hold a sample position, which says nothing of where
        # this component goes.
        missing = [key for key in PLACEMENT_ATTRIBUTES if key in known and key not in given]
        if missing:
            raise NxwrightError("%s: component %s needs its place on the screen; %s missing"
                                % (where, name, ", ".join(missing)))
        attributes = [Attribute(key, given.get(key, value)) for key, value in defaults_order]
        if events is None:
            events = type_defaults.events
    if whole_checks:
        _check_keyboard_scope(attributes, name, where)
        _check_least_size(attributes, TYPE_NAMES.get(object_type), name, where)
    if ("endx" in given or "endy" in given) and "h" not in given:
        raise NxwrightError("%s: endx and endy need h" % where)
    derived = _derived_values(index, name, given)
    ordered = [Attribute("type", bytes([object_type]))]
    for key in ("id", "objname"):
        if key not in given and key not in derived:
            raise NxwrightError("%s: id must be given for an object past ID 255" % where)
        ordered.append(Attribute(key, given.get(key, derived.get(key))))
    for attribute in attributes:
        if attribute.name in _DERIVED:
            continue
        ordered.append(attribute)
        if attribute.name == "h":
            ordered += [Attribute(key, given.get(key, derived[key])) for key in ("endx", "endy")]
    items = [Marker(b"att-%d" % len(ordered))] + ordered
    # By this point, a table that leaves out its events has its type's
    # events.
    kept_events = _kept_events(table.get("kept_events", {}), events, code, name, where)
    items += [Event(event, kept_events[event] if event in kept_events
                    else code.pop((name, event), [])) for event in events or []]
    return PageObject(items)


@dataclass
class Component:
    """A page's object as a page file describes it, its values as the screen
    stores them: colours as RGB565 numbers, pictures and fonts by ID (65535
    for none), texts as strings."""
    name: str
    type: str           # a name of TYPE_NAMES, or the type's number as text
    values: dict        # {attribute: number or string}


def page_table_at_screen(table: dict, page_size: tuple, defaults: dict) -> dict:
    """Returns the page's `table` with the place and size the Nextion Editor
    compiles every page at: x and y 0, and w and h `page_size`, the
    screen's size at its rotation. It resets them as it opens the project,
    whatever the page file says. Only the attributes the page has are set:
    those its table gives and, unless the table lists every attribute
    ("defaults = false"), those of the page type in `defaults`, the
    folder's component defaults. endx and endy are set when the table gives
    them. Without `page_size`, as when app.toml gives no screen, the table
    is returned as it is."""
    if page_size is None or not isinstance(table, dict):
        return table
    width, height = page_size
    place = {"x": 0, "y": 0, "w": width, "h": height}
    has = set(table)
    type_defaults = defaults.get(TYPES_BY_NAME["page"])
    if table.get("defaults") is not False and type_defaults is not None:
        has |= set(type_defaults.names())
    values = {key: value for key, value in place.items() if key in has}
    values.update({key: value for key, value in (("endx", width - 1), ("endy", height - 1))
                   if key in table})
    return dict(table, **values)


def page_components(text: str, page_name: str, names: ResourceNames, defaults: dict,
                    encoding: str, page_size: tuple = None, defines: dict = None) -> list:
    """Returns the Components of the page file `text`, the page first, in ID
    order, each table completed by its type's defaults as the build does.
    With `page_size`, the page has the screen's place and size, as the build
    gives it (page_table_at_screen). Placeholders take the values of
    app.toml's `defines` (page_data). Raises NxwrightError, naming the
    table, as the build does."""
    try:
        data = page_data(text, page_name, defines)
    except tomllib.TOMLDecodeError as error:
        raise NxwrightError("%s: %s" % (page_toml_path(page_name), error)) from None
    tables = ([page_table_at_screen(data.get("page", {}), page_size, defaults)]
              + list(data.get("component", [])))
    codec = TextCodec(encoding)
    components = []
    for index, table in enumerate(tables):
        where = "%s, %s" % (page_toml_path(page_name), table.get("name", "table %d" % index))
        page_object = _object_from_table(table, index, {}, names, defaults, codec, where)
        object_type = page_object.attribute("type")[0]
        values = {}
        for item in page_object.items:
            if isinstance(item, Attribute) and item.name not in ("type", "objname"):
                values[item.name] = (codec.decode(item.value, where)
                                     if is_string_attribute(object_type, item.name)
                                     else int.from_bytes(item.value, "little"))
        components.append(Component(table["name"], TYPE_NAMES.get(object_type, str(object_type)),
                                    values))
    return components


@dataclass
class Property:
    """One attribute of a component, as a properties panel shows it: its
    value as the page file writes it (a string, a picture or font name, a
    "#rrggbb" colour, or a number), its type's default written the same way,
    or None for a type without defaults, and whether its table gives it."""
    attribute: str
    value: object
    default: object
    given: bool


def component_properties(table: dict, index: int, names: ResourceNames, defaults: dict,
                         encoding: str, where: str) -> tuple:
    """Returns (type name, whether the table is marked defaults = false,
    [Property]) of a page file's table, in stored order, as the build
    completes it. The table's index is its object's ID. Raises NxwrightError
    as the build does for a value. A component the build refuses as a whole,
    for its keyboard's scope or its size, still gives its properties, so
    that they can be shown and changed."""
    codec = TextCodec(encoding)
    page_object = _object_from_table(table, index, {}, names, defaults, codec, where,
                                     whole_checks=False)
    object_type = page_object.attribute("type")[0]
    full = _table_header(table, where)[3]
    type_defaults = dict(defaults[object_type].attributes) if object_type in defaults else {}
    properties = []
    for item in page_object.items:
        if not isinstance(item, Attribute) or item.name in ("type",) + _DERIVED:
            continue
        default = type_defaults.get(item.name)
        properties.append(Property(
            item.name, _attribute_to_value(item, object_type, where, names, codec),
            None if default is None else _attribute_to_value(Attribute(item.name, default),
                                                             object_type, where, names, codec),
            item.name in table))
    return TYPE_NAMES.get(object_type, str(object_type)), full, properties


def attribute_value(type_name: str, attribute: str, text: str, names: ResourceNames,
                    encoding: str, where: str):
    """Returns the page file's value for an attribute typed as `text`: the
    text itself for a text attribute, a colour, a resource's name, and
    otherwise a number. "none" for a resource is 65535. Raises NxwrightError,
    as the build would, for a value the attribute cannot hold."""
    object_type = TYPES_BY_NAME.get(type_name)
    if object_type is None:
        raise NxwrightError("%s: unknown type %s" % (where, type_name))
    text = text if is_string_attribute(object_type, attribute) else text.strip()
    kind = reference_kind(object_type, attribute)
    if is_string_attribute(object_type, attribute) or attribute in COLOUR_ATTRIBUTES:
        value = text
    elif kind and (_is_resource_name(names, kind, text) or not text.lstrip("-").isdigit()):
        # A name before an ID: a picture may be called "2".
        value = 65535 if text == "none" else text
    else:
        try:
            value = int(text, 16) if text.lower().startswith("0x") else int(text)
        except ValueError:
            raise NxwrightError("%s: %s must be a number" % (where, attribute)) from None
        # A resource given by its ID is written by its name, as extract writes it.
        if kind:
            value = names.name_of(kind, value) or value
    # The build's own check of the value.
    stored_value(type_name, attribute, value, names, encoding, where)
    return value


def _is_resource_name(names: ResourceNames, kind: str, text: str) -> bool:
    """True when `text` names a resource of `kind`."""
    try:
        names.id_of(kind, text)
    except NxwrightError:
        return False
    return True


def stored_value(type_name: str, attribute: str, value, names: ResourceNames, encoding: str,
                 where: str) -> bytes:
    """Returns the bytes the build stores for an attribute's value in a page
    file. Raises NxwrightError as the build does."""
    return _value_to_bytes(attribute, value, TYPES_BY_NAME[type_name], names,
                           TextCodec(encoding), where)


def _with_disup(attributes: list, value: bytes):
    """Returns `attributes`, a type's (name, stored bytes) in stored order,
    with disup at `value` right after drag. Returns None when they have no
    drag, as a timer's do. Defaults written from a project that the Nextion
    Editor 1.60.1 saved may list a disup already. That disup keeps its
    place, and takes `value`."""
    names = [name for name, _ in attributes]
    if _DRAG not in names:
        return None
    if _DISUP in names:
        return [(name, value if name == _DISUP else stored) for name, stored in attributes]
    at = names.index(_DRAG) + 1
    return attributes[:at] + [(_DISUP, value)] + attributes[at:]


def _table_header(table: dict, where: str) -> tuple:
    """Returns (name, type number, events or None, whether the table is marked
    defaults = false) of a <page>.page.toml table, after checking them."""
    name = table.get("name")
    if not isinstance(name, str):
        raise NxwrightError("%s: name must be a text" % where)
    # The Nextion Editor refuses an empty name. A name is stored in Latin-1
    # (_NAME_ENCODING), so its characters must be Latin-1 ones.
    if not name:
        raise NxwrightError("%s: name '' is empty" % where)
    if any(ord(character) > 0xff for character in name):
        raise NxwrightError("%s: name %r has a character Latin-1 lacks" % (where, name))
    if not _KEPT_NAME.fullmatch(name):
        raise NxwrightError("%s: name %r has a double quote or a control character, which an "
                            "event's heading cannot contain" % (where, name))
    type_value = table.get("type")
    object_type = TYPES_BY_NAME.get(type_value, type_value) if isinstance(type_value, str) \
        else type_value
    if not isinstance(object_type, int) or isinstance(object_type, bool) or not 0 <= object_type < 256:
        raise NxwrightError("%s: unknown type %r" % (where, type_value))
    events = table.get("events")
    if events is not None and (not isinstance(events, list) or not all(
            isinstance(event, str) and event.isalpha() and event.islower() for event in events)):
        raise NxwrightError("%s: events must be a list of event names" % where)
    # Not "in (True, False)": 0 and 1 equal False and True in Python.
    if not isinstance(table.get("defaults", True), bool):
        raise NxwrightError("%s: defaults must be true or false" % where)
    return name, object_type, events, table.get("defaults", True) is False


def _raw_bytes(key: str, value: dict, where: str) -> bytes:
    """Returns the stored bytes in an attribute's raw form `value`, such as
    { bytes = "01" }. Raises NxwrightError for any other table, and for
    bytes that are not hexadecimal digits."""
    text = value.get(RAW_KEY)
    if set(value) != {RAW_KEY} or not isinstance(text, str):
        raise NxwrightError("%s: %s must be a value, or its stored bytes as { %s = \"01\" }"
                            % (where, key, RAW_KEY))
    try:
        return bytes.fromhex(text)
    except ValueError:
        raise NxwrightError("%s: %s's bytes must be hexadecimal digits, two for each byte, such as "
                            "\"01\": %s" % (where, key, text)) from None


def _value_to_bytes(key: str, value, object_type: int, names: ResourceNames, codec: TextCodec,
                    where: str) -> bytes:
    """Returns an attribute's stored bytes from its value in <page>.page.toml: the
    reverse of _attribute_to_value."""
    if isinstance(value, dict):
        return _raw_bytes(key, value, where)
    if is_string_attribute(object_type, key):
        if not isinstance(value, str):
            raise NxwrightError("%s: %s must be a string" % (where, key))
        return codec.encode(value, "%s: %s" % (where, key))
    kind = reference_kind(object_type, key)
    if kind and isinstance(value, str):
        try:
            value = names.id_of(kind, value)
        except NxwrightError as error:
            raise NxwrightError("%s: %s: %s" % (where, key, error)) from None
    if key in COLOUR_ATTRIBUTES and isinstance(value, str):
        if not COLOUR_TEXT.fullmatch(value):
            raise NxwrightError("%s: %s must be a colour such as \"#ff8000\"" % (where, key))
        value = hex_to_rgb565(value)
    width = expected_width(object_type, key)
    if width is None:
        raise NxwrightError("%s: unknown attribute %s" % (where, key))
    if isinstance(value, str):
        number = text_form_number(object_type, key, value,
                                  lambda text: codec.encode(text, "%s: %s" % (where, key)))
        value = value if number is None else number
    if not isinstance(value, int) or isinstance(value, bool):
        raise NxwrightError("%s: %s must be a number" % (where, key))
    return allowed_number_bytes(object_type, key, value, width, "%s: %s" % (where, key))


def _check_least_size(attributes: list, type_name: str, name: str, where: str):
    """Raises NxwrightError for a component of the type `type_name`
    narrower or lower than LEAST_SIDE, from its `attributes`, which the
    Editor would not open as it is (editor_limits.least_size_words)."""
    sides = {attribute.name: number_from_bytes(attribute.value) for attribute in attributes
             if attribute.name in ("w", "h")}
    if len(sides) == 2 and min(sides.values()) < LEAST_SIDE:
        raise NxwrightError("%s: component %s is %d by %d; %s"
                            % (where, name, sides["w"], sides["h"],
                               least_size_words(type_name, sides["w"], sides["h"])),
                            fix={"kind": "least-size", "component": name})


def _check_keyboard_scope(attributes: list, name: str, where: str):
    """Raises NxwrightError for a component bound to one of the Editor's
    keyboards, its `key` the keyboard's system page mark, whose scope is
    local. The keyboard page writes the typed text back into it from another
    page, which can use only a component of global scope. So the Editor
    binds a keyboard only to one, and refuses to make a bound one local."""
    values = {attribute.name: int.from_bytes(attribute.value, "little")
              for attribute in attributes if attribute.name in ("key", "vscope")}
    key = values.get("key")
    if key in SYSTEM_PAGES.values() and values.get("vscope") != 1:
        raise NxwrightError("%s: a keyboard is bound (key %d), so vscope must be 1, global, as "
                            "the Nextion Editor requires" % (where, key),
                            fix={"kind": "global", "component": name})


def _header_keys(header: PageHeader) -> dict:
    """Returns the keys of a [page] table that give `header`: none for an
    ordinary page, unlocked. A value that nxwright has not seen still has a
    key. A system page mark or a lock has its number as its value. Bytes 21
    and 22 are given as their stored bytes, under header_21."""
    keys = {}
    if header.system_page is not None:
        keys["system_page"] = header.system_page
    if header.locked:
        keys["locked"] = header.locked
    if header.lock_password_hash != NO_LOCK_PASSWORD:
        keys["lock_password_hash"] = header.lock_password_hash.hex()
    if header.header_21 != HEADER_21:
        keys["header_21"] = {RAW_KEY: header.header_21.hex()}
    return keys


def page_header_of_text(text: str, page_name: str, defines: dict = None) -> PageHeader:
    """Returns the page header that the [page] table of the page file `text`
    gives, after making the same checks as the build. Raises NxwrightError,
    naming the page's file, if `text` is not TOML, has no [page] table, or
    has an invalid value. Placeholders take the values of app.toml's
    `defines` (page_data)."""
    try:
        data = page_data(text, page_name, defines)
    except tomllib.TOMLDecodeError as error:
        raise NxwrightError("%s.page.toml: %s" % (page_file_stem(page_name), error)) from None
    page_table, components = data.get("page"), data.get("component", [])
    if not isinstance(page_table, dict):
        raise NxwrightError("%s.page.toml has no [page] table" % page_file_stem(page_name))
    return _page_header(page_table, components if isinstance(components, list) else [],
                        page_name)


def _page_header(page_table: dict, components: list, page_name: str) -> PageHeader:
    """Returns the page header the [page] table gives, after checking the
    tables."""
    shown = page_file_stem(page_name)
    for key in ("header_16", "header_40"):
        if key in page_table:
            raise NxwrightError("%s.page.toml: [page] holds %s, which page files no longer keep; "
                                "remove it" % (shown, key))
    for key in _HEADER_KEYS:
        if any(isinstance(table, dict) and key in table for table in components):
            raise NxwrightError("%s.page.toml: only the [page] table can give %s"
                                % (shown, key))
    # Extract writes a system page mark or a lock that nxwright has not seen
    # as its number (_header_keys), so the build accepts that number.
    system_page = page_table.get("system_page")
    unknown_mark = _is_byte(system_page) and system_page not in (0, *SYSTEM_PAGES.values())
    if system_page is not None and system_page not in SYSTEM_PAGES and not unknown_mark:
        names = ['"%s"' % name for name in SYSTEM_PAGES]
        raise NxwrightError("%s.page.toml: system_page must be %s, or the number of a mark "
                            "nxwright does not know" % (shown, ", ".join(names)))
    locked = page_table.get("locked", False)
    if not isinstance(locked, bool) and not (_is_byte(locked) and locked >= 2):
        raise NxwrightError("%s.page.toml: locked must be true, false, or a number from 2 to 255"
                            % shown)
    password = page_table.get("lock_password_hash", NO_LOCK_PASSWORD.hex())
    if not is_password_hash_text(password):
        raise NxwrightError("%s.page.toml: lock_password_hash must be 8 lower-case "
                            "hexadecimal digits" % shown)
    stored_21 = page_table.get("header_21", {RAW_KEY: HEADER_21.hex()})
    header_21 = (_raw_bytes("header_21", stored_21, "%s.page.toml" % shown)
                 if isinstance(stored_21, dict) else None)
    if header_21 is None or len(header_21) != 2:
        raise NxwrightError("%s.page.toml: header_21 must be 2 bytes, such as "
                            "{ %s = \"4f21\" }" % (shown, RAW_KEY))
    return PageHeader(system_page, locked, bytes.fromhex(password), header_21)


def _is_byte(value) -> bool:
    """Returns whether `value` is a whole number from 0 to 255. True and
    false do not count, although Python treats them as numbers."""
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 255
