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
compiling its events first when the folder uses nxlang. Which events keep
their source text when a project is extracted into an existing folder is
editor_code_merge.py's, and the screen's colours are screen_colours.py's.
"""
from dataclasses import dataclass
import re
import tomllib

import tomli_w

from nxwright import NxwrightError
from nxwright.language.code_checks import ObjectNames
from nxwright.language.code_preprocessor import Owner, preprocess, preprocess_with_places
from nxwright.project.object_types import TYPE_NAMES, TYPES_BY_NAME
from nxwright.project.screen_colours import COLOUR_TEXT, hex_to_rgb565, rgb565_to_hex
from nxwright.project.screen_models import ScreenModel
from nxwright.project.component_defaults import DERIVED_ATTRIBUTES, PLACEMENT_ATTRIBUTES
from nxwright.project.device_settings import (DEFAULT_ENCODING, TextCodec, encoding_code,
                                              is_password_hash_text)
from nxwright.project.editor_limits import LEAST_SIDE, check_page_limits, least_size_words
from nxwright.project.page_block import HEADER_SIZE, Attribute, Event, Marker, PageBlock, PageObject
from nxwright.project.page_header import (NO_LOCK_PASSWORD, SYSTEM_PAGES, PageHeader, header_16,
                                         header_40, page_header_of)
from nxwright.source.nx_files import (CODE_INDENT, EVENT_COMMENT_MARKER, EventBlock, PageFiles,
                                      blank_lines_dropped, event_blocks, read_page_files)
from nxwright.project.page_text import expected_width, is_string_attribute, text_form_number
from nxwright.project.attribute_values import number_from_bytes, number_to_bytes
from nxwright.language.resource_names import (ANIMATION, FONT, PICTURE, SOUND, VIDEO,
                                              ResourceNames, UnknownNameError)
from nxwright.language.nxlang import (GENERATED_NAME, GENERATED_PREFIX, HOTSPOT, HOTSPOT_PREFIX,
                                      HOTSPOT_SIZE, TEXT, TEXT_TEMPORARY_SIZE, ProgramNames,
                                      compile_page)

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
_TABLE_KEYS = ("name", "type", "defaults", "events", "system_page", "locked",
               "lock_password_hash")
# The keys of the [page] table that give the page header (page_header.py).
_HEADER_KEYS = ("system_page", "locked", "lock_password_hash")
# Attributes the build derives (see _derived_values). A table gives one only
# when its stored value differs from the derived one.
_DERIVED = ("id", "objname", "endx", "endy")
# Names are plain ASCII, checked once decoded: Latin-1 decodes any byte, so a
# name that is not reaches that check rather than a decoding error.
_NAME_ENCODING = "latin-1"
_NAME = re.compile(r"[A-Za-z0-9_]+")
# The values the Editor allows for an attribute, by (type, attribute), where
# they are fewer than the attribute's bytes can hold. The Editor refuses a
# text of style 4 ("styles.text4.style Out of range"): style 4, 3D auto, is
# a button's. It refuses a select of style 2, sunken, on every series that
# has a select. It refuses a gauge whose val is past 360 degrees ("page0.g14.val
# Out of range"), and a scrolling text's `tim` of 79 or 65535 alike. It
# refuses a gauge whose `left` is past 1024, whatever the gauge's size. Of
# the attributes its panel never shows, it refuses a button's `val` past 1,
# a file browser's `xcen` past 2, a combo box's `drastate` past 1, a
# gauge's `wid` outside 1 to 20, whatever its size, and a hotspot's `drag`
# and `effect` past 1 and 8. It refuses an xfloat's `vvs1` past 8, the
# digits after its point, and `vvs0` past 10, the digits before it, and a
# waveform's `dir` past 2.
_RANGES = {(TYPES_BY_NAME["text"], "style"): range(0, 4),
           (TYPES_BY_NAME["select"], "style"): range(0, 2),
           (TYPES_BY_NAME["gauge"], "val"): range(0, 361),
           (TYPES_BY_NAME["gauge"], "left"): range(0, 1025),
           (TYPES_BY_NAME["scrolling-text"], "tim"): range(80, 65535),
           (TYPES_BY_NAME["button"], "val"): range(0, 2),
           (TYPES_BY_NAME["file-browser"], "xcen"): range(0, 3),
           (TYPES_BY_NAME["combo-box"], "drastate"): range(0, 2),
           (TYPES_BY_NAME["gauge"], "wid"): range(1, 21),
           (TYPES_BY_NAME["hotspot"], "drag"): range(0, 2),
           (TYPES_BY_NAME["hotspot"], "effect"): range(0, 9),
           (TYPES_BY_NAME["xfloat"], "vvs1"): range(0, 9),
           (TYPES_BY_NAME["xfloat"], "vvs0"): range(0, 11),
           (TYPES_BY_NAME["waveform"], "dir"): range(0, 3)}
# The `aph` the Editor allows, on every type that has one: it refused 128 on
# a text, a button, a number, a picture, a hotspot, and a page alike, the
# page's on every series (memory_costs.toml, `refused_values`).
_APH_RANGE = range(0, 128)
_VARIABLE = TYPES_BY_NAME["variable"]
_HOTSPOT = TYPES_BY_NAME["hotspot"]
# Object IDs are one byte.
MOST_OBJECTS = 256


def reference_kind(object_type, attribute: str):
    """Returns the kind of resource (resource_names.py) whose ID `attribute`
    holds in a component of type `object_type`, a number, or None when it
    holds none."""
    if attribute == "vid":
        return _PLAYED_KINDS.get(object_type)
    return _REFERENCE_KINDS.get(attribute)


def attribute_range(object_type: int, attribute: str):
    """Returns the range of values the build takes for `attribute` of a
    component of type `object_type`, a number, where the Editor allows fewer
    than the attribute's bytes hold (_RANGES, _APH_RANGE); None elsewhere."""
    if attribute == "aph":
        return _APH_RANGE
    return _RANGES.get((object_type, attribute))


@dataclass
class PageSource:
    """The text of a page's two source files, and the warnings of what
    page_to_source dropped making them."""
    toml: str
    events: str
    warnings: tuple = ()


def page_to_source(page: PageBlock, names: ResourceNames, defaults: dict,
                   encoding: str = DEFAULT_ENCODING) -> PageSource:
    """Returns the source files of `page`. `defaults` ({type number:
    TypeDefaults}) gives what can be left out. Its texts and code are in
    `encoding`, the project's character encoding. Its warnings name each
    event whose blank lines were dropped (_event_to_text).

    Raises NxwrightError when the page holds something the source files
    cannot represent, naming the page and object.
    """
    if page.header_size != HEADER_SIZE:
        raise NxwrightError("page %s: header size %d is not %d" % (page.name, page.header_size,
                                                                  HEADER_SIZE))
    if not page.objects or page.objects[0].attribute("objname") != page.name.encode(_NAME_ENCODING):
        raise NxwrightError("page %s: the page object is not named after the page" % page.name)
    header = page_header_of(page)
    codec = TextCodec(encoding)
    tables, headings, warnings = [], [], []
    for index, page_object in enumerate(page.objects):
        where = "page %s, object %d" % (page.name, index)
        content = _ObjectContent.read(page_object, index, where)
        table = {"name": content.name, "type": TYPE_NAMES.get(content.type, content.type)}
        if index == 0:
            table.update(_header_keys(header))
        type_defaults = defaults.get(content.type)
        stored = [item.name for item in page_object.items
                  if isinstance(item, Attribute) and item.name not in DERIVED_ATTRIBUTES]
        # Only a component with exactly its type's attributes can be shortened.
        shortened = type_defaults is not None and stored == type_defaults.names()
        default_values = dict(type_defaults.attributes) if shortened else {}
        event_names = [event.name for event in content.events]
        if not shortened:
            table["defaults"] = False
        if not shortened or event_names != type_defaults.events:
            table["events"] = event_names
        for attribute in content.attributes:
            if (attribute.name in _DERIVED or attribute.name in PLACEMENT_ATTRIBUTES
                    or default_values.get(attribute.name) != attribute.value):
                table[attribute.name] = _attribute_to_value(attribute, content.type, where, names,
                                                            codec)
        tables.append(table)
        for event in content.events:
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
                     absent_attributes: dict = None, screen: ScreenModel = None) -> PageBlock:
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

    In the Editor's own language, with `program_variables`, program.nx's int
    variables, the code may name sys0, sys1, and sys2 only when they are
    among them. The Editor refuses it otherwise. nxlang's compiler checks
    every name itself. With `macros`, the folder's macros' names, a `call`
    must name one of them (macros_source.py). With `screen`, the folder's
    screen model, in either language, no line may use a command or a
    system variable its series lacks (code_checks.series_lacks).

    In nxlang, the page's longest chain of calls and clicks is added to
    `chain`, when given: the event first, as "home.load", then each function
    or event that runs during the one before it.

    Raises NxwrightError naming the file and the problem. Its `file` is the
    file at fault, the page's .page.toml file unless the code is; for a table of
    the .toml file, `table` says which.
    """
    try:
        return _page_from_source(source, page_name, names, defaults, nxlang_program, page_id,
                                 globals_used, read, page_objects, encoding, chain,
                                 program_variables, macros, absent_attributes, screen)
    except NxwrightError as error:
        error.file = error.file or page_toml_path(page_name)
        raise


def _page_from_source(source: PageSource, page_name: str, names: ResourceNames, defaults: dict,
                      nxlang_program: ProgramNames, page_id: int, globals_used: list, read,
                      page_objects: dict, encoding: str, chain: list,
                      program_variables: frozenset, macros: frozenset,
                      absent_attributes: dict, screen: ScreenModel) -> PageBlock:
    """Does the work of page_from_source."""
    try:
        data = tomllib.loads(source.toml)
    except tomllib.TOMLDecodeError as error:
        raise NxwrightError("%s.page.toml: %s" % (page_name, error)) from None
    page_table, components = data.get("page"), data.get("component", [])
    if not isinstance(page_table, dict):
        raise NxwrightError("%s.page.toml has no [page] table" % page_name)
    if set(data) - {"page", "component"} or not isinstance(components, list):
        raise NxwrightError("%s.page.toml holds only [page] and [[component]] tables" % page_name)
    if page_table.get("name") != page_name:
        raise NxwrightError("%s.page.toml names the page %r" % (page_name, page_table.get("name")))
    header = _page_header(page_table, components, page_name)
    codec = TextCodec(encoding)
    tables = [page_table] + components
    # The code is compiled against the tables' names, so a name that is no
    # name, as a table being typed may hold, is refused first, as below.
    for index, table in enumerate(tables):
        if isinstance(table, dict) and not isinstance(table.get("name"), (str, type(None))):
            try:
                _table_header(table, "%s.page.toml, object %d" % (page_name, index))
            except NxwrightError as error:
                error.table = index
                raise
    if nxlang_program is None:
        objects = None
        if page_objects is not None:
            objects = ObjectNames(frozenset(table.get("name") for table in tables), page_objects,
                                  page_name, absent_attributes=absent_attributes)
        code = _parse_events(source.events, page_name, names, codec,
                             [table.get("name") for table in tables], objects,
                             program_variables, macros, screen)
    else:
        code, generated, used, deepest = _compile_nxlang_events(
            source.events, page_name, names, [table.get("name") for table in tables],
            nxlang_program, page_id, read, codec, page_objects,
            {**(page_objects or {}), page_name: table_types(tables)}, absent_attributes, screen)
        if globals_used is not None:
            globals_used.extend(used)
        if chain is not None:
            chain.extend(deepest)
        tables += [generated_table(variable) for variable in generated]
        if len(tables) > MOST_OBJECTS:
            raise NxwrightError("%s: with the variables nxlang adds, the page has "
                                "%d objects; at most %d fit" % (page_name, len(tables), MOST_OBJECTS))
    object_names = [table.get("name") for table in tables]
    if len(set(object_names)) != len(object_names):
        raise NxwrightError("%s.page.toml: two objects are named %s"
                            % (page_name, next(name for name in object_names if object_names.count(name) > 1)))
    objects = []
    for index, table in enumerate(tables):
        try:
            objects.append(_object_from_table(table, index, code, names, defaults, codec,
                                              "%s.page.toml, object %d" % (page_name, index)))
        except NxwrightError as error:
            error.table = index
            raise
    if code:
        name, event = next(iter(code))
        if nxlang_program is not None and (name, event) == (page_name, "load"):
            # The build puts the functions' tsw lines there.
            raise NxwrightError("%s.page.toml: functions need the page's load event, which its "
                                "events do not list" % page_name)
        raise NxwrightError("%s.nx: %s.%s is not an event listed in the page's .page.toml file"
                            % (page_name, name, event))
    page = PageBlock(name=page_name, header_size=HEADER_SIZE,
                     unknown_16=header_16(header),
                     unknown_40=header_40(encoding_code(encoding)), objects=objects)
    check_page_limits(page, "%s.page.toml" % page_name)
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
                page_name, (page_object.attribute("objname") or b"").decode("latin-1"), font,
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
    def read(cls, page_object: PageObject, index: int, where: str) -> "_ObjectContent":
        """Returns the content of `page_object`, the object at `index` on its page.

        Raises NxwrightError, starting with `where`, when the object does not
        have the shape the source files assume.
        """
        items = page_object.items
        attributes = [item for item in items if isinstance(item, Attribute)]
        events = [item for item in items if isinstance(item, Event)]
        if (not items or items[0] != Marker(b"att-%d" % len(attributes))
                or items[1:] != attributes + events):
            raise NxwrightError("%s: records are not a class marker, attributes, then events" % where)
        names = [attribute.name for attribute in attributes]
        event_names = [event.name for event in events]
        # A TOML table holds each key once, and a heading names each event once.
        if len(set(names)) != len(names) or len(set(event_names)) != len(event_names):
            raise NxwrightError("%s: an attribute or event appears twice" % where)
        if not all(re.fullmatch(r"[a-z]+", name) for name in event_names):
            raise NxwrightError("%s: an event name is not lowercase letters" % where)
        if names[:3] != ["type", "id", "objname"] or len(attributes[0].value) != 1:
            raise NxwrightError("%s: attributes do not start with type, id, objname" % where)
        if ("h" in names) != ("endx" in names) or (
                "h" in names and names[names.index("h") + 1:names.index("h") + 3] != ["endx", "endy"]):
            raise NxwrightError("%s: endx and endy do not follow h" % where)
        objname = attributes[2].value.decode(_NAME_ENCODING)
        if not _NAME.fullmatch(objname):
            raise NxwrightError("%s: name %r is not a plain name" % (where, objname))
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


def _attribute_to_value(attribute: Attribute, object_type: int, where: str, names: ResourceNames,
                        codec: TextCodec):
    """Returns an attribute's value as <page>.page.toml writes it: a string, a
    resource's name, a "#rrggbb" colour, or a number."""
    if attribute.name in _TABLE_KEYS:
        raise NxwrightError("%s: attribute %s clashes with a key of the page's .page.toml file" % (where, attribute.name))
    if is_string_attribute(object_type, attribute.name):
        return codec.decode(attribute.value, "%s: %s" % (where, attribute.name))
    if len(attribute.value) != expected_width(object_type, attribute.name):
        raise NxwrightError("%s: attribute %s has an unexpected size" % (where, attribute.name))
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
             + ["on %s.%s:" % (name, event.name)] + [CODE_INDENT + text for text in texts[start:]])
    return "\n".join(lines) + "\n", dropped


def page_file_text(tables: list) -> str:
    """Returns the text of <page>.page.toml from its tables, dicts of their
    values: the first as [page], the others as [[component]], each after a
    blank line. The headers are written here, as tomli-w writes a list of
    tables as an array of inline ones."""
    return "\n".join(("[page]" if index == 0 else "[[component]]") + "\n" + tomli_w.dumps(table)
                     for index, table in enumerate(tables))


def editor_code_of_block(block: EventBlock, page_name: str, names: ResourceNames, owner: Owner,
                         objects: ObjectNames = None, variables: frozenset = None,
                         macros: frozenset = None, screen: ScreenModel = None) -> list:
    """Returns the block's code in Editor syntax, one string per line, its
    comment first. `owner` is the object whose event it is, None when the
    page has none of that name. With `objects`, its references are checked,
    with `variables`, its names of program.nx's variables, with `macros`,
    its calls, and with `screen`, what its series lacks (preprocess)."""
    try:
        return block.marked_comment() + preprocess(block.code_lines(), names, objects, variables,
                                                   macros, screen, owner)
    except NxwrightError as error:
        raise error.in_file(page_nx_path(page_name), shown="%s.nx" % page_name) from None


def table_types(tables: list) -> dict:
    """Returns the types of a page's objects, {name: type}, from its page
    file's tables: the page's, then its components'. A table whose name is
    not text, as one being typed may hold, is left out, for its own check to
    report (_table_header)."""
    return {table.get("name"): table.get("type") for table in tables
            if isinstance(table, dict) and isinstance(table.get("name"), (str, type(None)))}


def page_nx_path(page_name: str) -> str:
    """Returns the source folder path of a page's own .nx file."""
    return "pages/%s.nx" % page_name


def page_toml_path(page_name: str) -> str:
    """Returns the source folder path of a page's file, `<page>.page.toml`."""
    return "pages/%s%s" % (page_name, PAGE_FILE_SUFFIX)


def _no_includes(path: str) -> str:
    """Raises NxwrightError for any include: the `read` used when there is no
    source folder."""
    raise NxwrightError("%s: no source folder to read included files from" % path)


def _compile_nxlang_events(text: str, page_name: str, names: ResourceNames, component_names: list,
                           program: ProgramNames, page_id: int, read, codec: TextCodec,
                           page_objects: dict = None, object_types: dict = None,
                           absent_attributes: dict = None, screen: ScreenModel = None) -> tuple:
    """Returns ({(object name, event): [code line bytes]}, [Generated] for the
    generated variables, [the program.s globals used], the longest chain of
    calls and clicks) for a page's .nx file in nxlang. With
    `page_objects`, references, calls, and assignments are checked, as
    page_from_source says (ObjectNames), with `absent_attributes` the
    attributes components lack, and with `screen` what its series lacks.
    `object_types` gives the types of the pages' objects nxlang compiles
    with, {page: {name: type}} (nxlang.compile_page)."""
    page_files = read_page_files(page_nx_path(page_name), text, read or _no_includes)
    compiled = compile_page_files(page_files, page_name, component_names, program, page_id,
                                  object_types)
    code = {}
    objects = None
    if page_objects is not None:
        own = frozenset(component_names) | {variable.name for variable in compiled.generated}
        objects = ObjectNames(own, page_objects, page_name, absent_attributes=absent_attributes)
    for key, lines in preprocess_compiled(compiled, page_name, names, objects=objects,
                                          screen=screen).items():
        where = "%s: %s.%s" % (compiled.sources.get(key, page_nx_path(page_name)), *key)
        code[key] = [codec.encode(line, where) for line in lines]
    return code, compiled.generated, compiled.globals, compiled.deepest_chain


def editor_code_of_file(path: str, page_name: str, events_text: str, names: ResourceNames,
                        component_names: list, program: ProgramNames, page_id: int, read,
                        object_types: dict = None) -> list:
    """Returns [(title, [(line, Editor code line)])] of the events and the
    functions that the .nx file `path` defines, as page `page_name` compiles
    them, its own .nx file's text being `events_text`. A title is as
    "on save.up" or "function show"; `line` is the line of `path` that the
    Editor line comes from, counted from 1, or 0 for a line the compiler
    adds. With `program`, what program.nx declares, the code is nxlang, and
    only the functions the page calls are compiled; without it, the code is
    in the Editor's own language. `read(path)` returns an included file.
    `object_types` gives the types of the pages' objects nxlang compiles
    with, {page: {name: type}} (nxlang.compile_page).

    Raises NxwrightError as the build does."""
    if program is None:
        text = events_text if path == page_nx_path(page_name) else read(path)
        sections = []
        for key, block in event_blocks(text, path).items():
            comment = [(number, marked) for (number, _), marked
                       in zip(block.comment, block.marked_comment())]
            sections.append(("on %s.%s" % key,
                             preprocess_with_places(comment + block.code_lines(), names,
                                                    owner=Owner.among(key[0],
                                                                      component_names))))
        return sections
    compiled = compile_nxlang_page(events_text, page_name, component_names, program, page_id,
                                   read, object_types)
    sections = [("on %s.%s" % key, preprocess_with_places(lines, names))
                for key, lines in compiled.events.items() if compiled.sources.get(key) == path]
    sections += [("function " + name, preprocess_with_places(compiled.bodies[name], names))
                 for name, function in compiled.functions.items() if function.file == path]
    return sections


def compile_nxlang_page(text: str, page_name: str, component_names: list, program: ProgramNames,
                        page_id: int = 0, read=None, object_types: dict = None,
                        own_attributes: bool = True):
    """Returns the CompiledPage of a page's .nx text and the files it
    includes, as compile_page_files compiles them."""
    page_files = read_page_files(page_nx_path(page_name), text, read or _no_includes)
    return compile_page_files(page_files, page_name, component_names, program, page_id,
                              object_types, own_attributes)


def compile_page_files(page_files: PageFiles, page_name: str, component_names: list,
                       program: ProgramNames, page_id: int = 0, object_types: dict = None,
                       own_attributes: bool = True):
    """Returns the CompiledPage of a page's .nx files. The compiler sees only
    code lines, so each event's comment is put back at its start, marked as
    the build writes it. `object_types` gives the types of the pages'
    objects nxlang compiles with, {page: {name: type}}
    (nxlang.compile_page). An event of an object among `component_names`,
    the page's objects in ID order, the unnamed included, may name its
    attributes as '&name&'; with `own_attributes` False, none may, as code
    that runs in no object's event."""
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
                            owners)
    for key, comment in comments.items():
        compiled.events[key] = comment + compiled.events.get(key, [])
    return compiled


def preprocess_compiled(compiled, page_name: str, names: ResourceNames,
                        unknown_as_none: bool = False, objects: ObjectNames = None,
                        screen: ScreenModel = None) -> dict:
    """Returns {key: Editor code} of a compiled page's events. With
    `unknown_as_none`, an event naming a picture or font the app does not
    list gets None. With `objects`, references are checked, and with
    `screen`, what its series lacks. Errors name the .nx file holding the
    code at fault."""
    out = {}
    for key, lines in compiled.events.items():
        try:
            out[key] = preprocess(lines, names, objects, screen=screen)
        except NxwrightError as error:
            if unknown_as_none and isinstance(error, UnknownNameError):
                out[key] = None
                continue
            # in_file keeps the type, which tells an unknown name apart from other problems.
            raise error.in_file(file_at_fault(compiled, key, page_name, names, objects,
                                              screen)) from None
    return out


def file_at_fault(compiled, key, page_name: str, names: ResourceNames,
                  objects: ObjectNames = None, screen: ScreenModel = None) -> str:
    """Returns the .nx file holding the code of `key` that does not preprocess.
    A hotspot's event holds several functions: the one at fault is found by
    preprocessing each body alone."""
    if key in compiled.sources:
        return compiled.sources[key]
    for name, function in compiled.functions.items():
        if function.hotspot == key[0]:
            try:
                preprocess(compiled.bodies[name], names, objects, screen=screen)
            except NxwrightError:
                return function.file
    return page_nx_path(page_name)


def generated_table(variable) -> dict:
    """Returns the <page>.page.toml table of a generated variable: a hotspot for a
    function, otherwise a variable, which holds text when its kind is TEXT."""
    if variable.kind == HOTSPOT:
        return {"name": variable.name, "type": "hotspot", "x": 0, "y": 0, "w": HOTSPOT_SIZE,
                "h": HOTSPOT_SIZE}
    table = {"name": variable.name, "type": "variable"}
    if variable.kind == TEXT:
        table.update(sta=1, txt="", txt_maxl=TEXT_TEMPORARY_SIZE)
    return table


def strip_generated(page: PageBlock, encoding: str = DEFAULT_ENCODING) -> tuple:
    """Returns (`page` without its generated variables,
    {(component, event): [code lines]} of their events: the functions' bodies).

    The build adds them after the page's own components, but a component
    added later in the Editor comes after them. So they are removed wherever
    they are, and the IDs of the objects after them move down: the IDs the
    next build gives.

    Raises NxwrightError for any other object whose name starts with the
    prefix generated names use.
    """
    objects = [page.objects[0]] + [page_object for page_object in page.objects[1:]
                                   if not _is_generated(page_object)]
    codec = TextCodec(encoding)
    removed = {}
    for page_object in page.objects[1:]:
        if _is_generated(page_object):
            name = page_object.attribute("objname").decode(_NAME_ENCODING)
            for item in page_object.items:
                if isinstance(item, Event) and item.lines:
                    where = "page %s, %s.%s" % (page.name, name, item.name)
                    removed[(name, item.name)] = [codec.decode(line, where) for line in item.lines]
    for page_object in objects:
        name = (page_object.attribute("objname") or b"").decode(_NAME_ENCODING)
        if name.startswith(GENERATED_PREFIX):
            raise NxwrightError("page %s: component %s starts with %r, which the nxlang "
                                "language keeps for its generated variables"
                                % (page.name, name, GENERATED_PREFIX))
    if len(objects) < len(page.objects):
        objects = [_with_id(page_object, index) for index, page_object in enumerate(objects)]
    return PageBlock(name=page.name, header_size=page.header_size, unknown_16=page.unknown_16,
                     unknown_40=page.unknown_40, objects=objects, stamp=page.stamp), removed


def _with_id(page_object: PageObject, index: int) -> PageObject:
    """Returns `page_object` with its id set to `index`, or unchanged when
    `index` does not fit in the one byte an ID has."""
    if index >= MOST_OBJECTS:
        return page_object
    return PageObject([Attribute("id", bytes([index]))
                       if isinstance(item, Attribute) and item.name == "id" else item
                       for item in page_object.items])


def _is_generated(page_object: PageObject) -> bool:
    name = (page_object.attribute("objname") or b"").decode(_NAME_ENCODING)
    if GENERATED_NAME.fullmatch(name) is None:
        return False
    # Functions are hotspots; everything else the compiler adds is a variable.
    kind = _HOTSPOT if name.startswith(HOTSPOT_PREFIX) else _VARIABLE
    return page_object.attribute("type") == bytes([kind])


def _parse_events(text: str, page_name: str, names: ResourceNames, codec: TextCodec,
                  object_names: list, objects: ObjectNames = None, variables: frozenset = None,
                  macros: frozenset = None, screen: ScreenModel = None) -> dict:
    """Returns {(object name, event): [code line bytes]} from a page's .nx file,
    in Editor syntax, checked as editor_code_of_block says. `object_names` are the
    page's, in ID order, the page's first."""
    code = {}
    for key, block in event_blocks(text, page_nx_path(page_name)).items():
        where = "%s.nx: %s.%s" % (page_name, *key)
        code[key] = [codec.encode(line, where)
                     for line in editor_code_of_block(block, page_name, names,
                                                      Owner.among(key[0], object_names), objects,
                                                      variables, macros, screen)]
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
    given = {key: _value_to_bytes(key, value, object_type, names, codec, where)
             for key, value in table.items() if key not in _TABLE_KEYS}
    if full:
        attributes = [Attribute(key, value) for key, value in given.items()]
    else:
        type_defaults = defaults.get(object_type)
        if type_defaults is None:
            raise NxwrightError("%s: type %s has no defaults in defaults.toml; add its section "
                                "there, as nxwright defaults writes it from a sample project"
                                % (where, TYPE_NAMES.get(object_type, object_type)))
        known = type_defaults.names()
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
        attributes = [Attribute(key, given.get(key, value)) for key, value in type_defaults.attributes]
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
    items += [Event(event, code.pop((name, event), [])) for event in events or []]
    return PageObject(items)


@dataclass
class Component:
    """A page's object as a page file describes it, its values as the screen
    stores them: colours as RGB565 numbers, pictures and fonts by ID (65535
    for none), texts as strings."""
    name: str
    type: str           # a name of TYPE_NAMES, or the type's number as text
    values: dict        # {attribute: number or string}


def page_components(text: str, page_name: str, names: ResourceNames, defaults: dict,
                    encoding: str) -> list:
    """Returns the Components of the page file `text`, the page first, in ID
    order, each table completed by its type's defaults as the build does.
    Raises NxwrightError, naming the table, as the build does."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise NxwrightError("%s: %s" % (page_toml_path(page_name), error)) from None
    tables = [data.get("page", {})] + list(data.get("component", []))
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


def _table_header(table: dict, where: str) -> tuple:
    """Returns (name, type number, events or None, whether the table is marked
    defaults = false) of a <page>.page.toml table, after checking them."""
    name = table.get("name")
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise NxwrightError("%s: name must be a plain name" % where)
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


def _value_to_bytes(key: str, value, object_type: int, names: ResourceNames, codec: TextCodec,
                    where: str) -> bytes:
    """Returns an attribute's stored bytes from its value in <page>.page.toml: the
    reverse of _attribute_to_value."""
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
    allowed = attribute_range(object_type, key)
    if allowed is not None and value not in allowed:
        raise NxwrightError("%s: %s must be from %d to %d" % (where, key, allowed.start,
                                                             allowed.stop - 1))
    try:
        return number_to_bytes(value, width)
    except OverflowError:
        raise NxwrightError("%s: %s does not fit in %d bytes" % (where, key, width)) from None


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
    page, which reaches only a component of global scope. So the Editor
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
    ordinary page, unlocked."""
    keys = {}
    if header.system_page is not None:
        keys["system_page"] = header.system_page
    if header.locked:
        keys["locked"] = True
    if header.lock_password_hash != NO_LOCK_PASSWORD:
        keys["lock_password_hash"] = header.lock_password_hash.hex()
    return keys


def _page_header(page_table: dict, components: list, page_name: str) -> PageHeader:
    """Returns the page header the [page] table gives, after checking the
    tables."""
    for key in ("header_16", "header_40"):
        if key in page_table:
            raise NxwrightError("%s.page.toml: [page] holds %s, which page files no longer keep; "
                                "extract the project into the folder again" % (page_name, key))
    for key in _HEADER_KEYS:
        if any(isinstance(table, dict) and key in table for table in components):
            raise NxwrightError("%s.page.toml: only the [page] table can give %s"
                                % (page_name, key))
    system_page = page_table.get("system_page")
    if system_page is not None and system_page not in SYSTEM_PAGES:
        names = ['"%s"' % name for name in SYSTEM_PAGES]
        raise NxwrightError("%s.page.toml: system_page must be %s, or %s"
                            % (page_name, ", ".join(names[:-1]), names[-1]))
    locked = page_table.get("locked", False)
    if not isinstance(locked, bool):
        raise NxwrightError("%s.page.toml: locked must be true or false" % page_name)
    password = page_table.get("lock_password_hash", NO_LOCK_PASSWORD.hex())
    if not is_password_hash_text(password):
        raise NxwrightError("%s.page.toml: lock_password_hash must be 8 lower-case "
                            "hexadecimal digits" % page_name)
    return PageHeader(system_page, locked, bytes.fromhex(password))
