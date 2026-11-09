"""SVG pictures: pictures of a source folder whose file is an SVG file,
pictures/<name>.svg. nxwright draws one with resvg whenever a tool needs the
picture, and the build stores the drawn PNG (docs/source-folder.md).

resvg does not read three things an SVG file can use, so this module puts
them into the SVG text before drawing:
  - a style sheet linked by <?xml-stylesheet href="..."?> before the root.
    Its rules go in a <style> element at the start of the picture.
  - a <use> of an element of another SVG file, as href="../art/parts.svg#frame".
    The element, and what it refers to in its file, such as a gradient, go
    in the picture's <defs>. The <use> then refers to the copy, so it
    places it like any other <use>. The style of the other file does not apply.
  - a file that an <image> shows. It goes in as a data: URL.
Each of these files is named by a path relative to the file that names it,
and must be in the source folder. It can be another picture's file, as when
a page's pressed picture uses the drawing of its normal one. Renaming or
removing a file does not change the paths to it: the checks report a path
that leads nowhere.

Fonts. The computer's fonts are never loaded, so that a picture is drawn
the same on every computer. resvg has nxwright's Noto Sans, which is also
the font of the generic families, such as sans-serif, and of a text that
names none. It also has the font files that @font-face rules of the style
sheets name. resvg leaves out a text whose font it lacks, with no error, so
every font-family list is checked first.

A picture's size is its root's width and height, in whole pixels.

Defines. A picture can take the values of app.toml's defines. It does this
with plain SVG and CSS, so other viewers still draw the file, with the
values the file declares:
  - a style value, through a CSS variable named after the define:
    fill: var(--ACCENT), or var(--ACCENT, #ff8a45) with a fallback. It is
    replaced by the define's value wherever it is: in a style sheet, a
    <style> element, a style attribute, or another attribute. resvg does not
    read CSS variables, so a var() that names no define is refused.
  - a text's text, through <text data-nxwright-text="TITLE">: the define's
    value replaces what the file writes, which other viewers show.
A file can declare a value for other viewers, as in :root { --ACCENT:
#ff8a45; }. Such declarations play no part in the drawing, and are kept
(SvgDrawing.declared) so that the checks can warn when one differs from the
define's default.

The files are read through the caller's functions, so that a caller can
give the folder as a command would leave it, or the unsaved text of open
files. Drawn pictures are kept in memory by a hash of all they depend on
(SvgDrawing.key), and in the picture cache for builds (picture_cache.py).
"""
from collections import OrderedDict
import copy
from dataclasses import dataclass
import functools
import hashlib
from importlib import metadata
import io
import os
from pathlib import Path
import posixpath
import re
import tempfile
import threading
from urllib.parse import unquote
import xml.etree.ElementTree as ElementTree

import freetype
import resvg_py

from nxwright import NxwrightError
from nxwright.project.pictures import data_url
from nxwright.project.truetype import NOTO_SANS

SVG_SUFFIX = ".svg"
_SVG = "http://www.w3.org/2000/svg"
_XLINK = "http://www.w3.org/1999/xlink"
# So that the text given to resvg keeps the usual prefixes.
ElementTree.register_namespace("", _SVG)
ElementTree.register_namespace("xlink", _XLINK)

# The family of nxwright's own font, which serves every text that names no
# font file.
_NOTO_SANS_FAMILY = "Noto Sans"
# CSS's generic families, which resvg draws with Noto Sans.
_GENERIC_FAMILIES = ("serif", "sans-serif", "cursive", "fantasy", "monospace")
# Values of font-family that name no family.
_FONT_KEYWORDS = ("inherit", "initial", "unset", "revert")
# The files an <image> may show, by suffix, with their media type.
_IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}

_STYLESHEET = re.compile(r"<\?xml-stylesheet\s(.*?)\?>", re.S)
_PSEUDO_ATTRIBUTE = re.compile(r"""([A-Za-z-]+)\s*=\s*(["'])(.*?)\2""", re.S)
_ROOT_START = re.compile(r"<(?![?!])")
_FONT_FACE = re.compile(r"@font-face\s*\{([^{}]*)\}", re.I)
_FONT_FAMILY = re.compile(r"(?<![-\w])font-family\s*:\s*([^;{}]+)", re.I)
_FONT_SHORTHAND = re.compile(r"(?<![-\w])font\s*:", re.I)
_URL = re.compile(r"""url\(\s*(["']?)(.*?)\1\s*\)""", re.S)
_REFERENCE = re.compile(r"url\(\s*[\"']?#([^\"')\s]+)")
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_SIZE = re.compile(r"\s*([0-9]+)\s*(?:px)?\s*")
# The largest width or height of a picture, far past any screen's, so that a
# mistyped size never asks resvg for a picture too large to hold.
_MOST_PIXELS = 8192
_IMPORT = re.compile(r"@import\b", re.I)
_VAR = re.compile(r"var\(\s*--([A-Za-z0-9_-]*)")
_DECLARATION = re.compile(r"(?<![-\w])--([A-Za-z0-9_-]+)\s*:\s*([^;{}]+)")
# What a define's value cannot hold where it goes in CSS, since it would end
# or change the CSS around it.
_NOT_IN_CSS = re.compile(r"[;{}\\\r\n]|/\*")
# The attribute that gives a text element a define's value as its text.
_TEXT_FROM_DEFINE = "data-nxwright-text"


# The font files written for resvg whose bytes were checked (_font_file).
_checked_fonts = set()

# Pictures drawn, by SvgDrawing.key, kept up to _KEPT_BYTES of PNG data. A
# simulation draws on two threads, so the lock guards them.
_KEPT_BYTES = 64 << 20
_drawn = OrderedDict()
_drawn_lock = threading.Lock()


class SvgPictureError(NxwrightError):
    """Raised for an SVG picture that cannot be drawn. `files` are the paths
    of the folder's files it read or tried to read, the picture's first, so
    that a view of it can draw it again once one of them changes."""

    def __init__(self, message: str, files: tuple):
        super().__init__(message)
        self.files = files


@dataclass(frozen=True)
class SvgDrawing:
    """What resvg is given to draw an SVG picture: `text`, the SVG with what
    it shares put in; `fonts`, the bytes of the font files its style sheets
    name; its size. `key` is a hash of all of these and of what draws them,
    so that two drawings with the same key give the same picture.
    `files` are the paths of the folder's files read, the picture's first.
    `declared` holds the values the files declare for other viewers, as
    (file, name, value) for each `--name: value` (the module's docstring)."""
    text: str
    fonts: tuple
    width: int
    height: int
    key: str
    files: tuple
    declared: tuple


def svg_picture_size(path: str, text: str) -> tuple:
    """Returns the (width, height) of the SVG picture whose file `path` holds
    `text`, from its root's width and height, without drawing it. Raises
    NxwrightError for a file that is not an SVG file, or a size that is not
    a whole number of pixels."""
    return _size(path, _parsed(path, text))


def prepared_svg_picture(path: str, read_text, read_bytes, defines: dict) -> SvgDrawing:
    """Returns what resvg draws for the SVG picture whose file is `path`, a
    path within the source folder. `read_text(path)` and `read_bytes(path)`
    return the folder's files, and `defines` the values of app.toml's
    defines, {name: int or str}. Raises SvgPictureError, an NxwrightError
    that gives the files tried, for a file that is missing or not what it
    should be, a shared file outside the folder, a font family that no
    given font serves, or a define that the picture uses but `defines`
    lacks, or whose value the picture cannot take. The message names the
    files involved."""
    preparation = _Preparation(path, read_text, read_bytes, defines)
    try:
        return preparation.prepared()
    except NxwrightError as error:
        raise SvgPictureError(str(error), tuple(preparation.files)) from None


def drawn_svg_picture(drawing: SvgDrawing, cache=None) -> bytes:
    """Returns the PNG picture resvg draws for `drawing`, from `cache`
    (picture_cache.PictureCache, or None) or from memory when one was drawn
    for the same key. The picture is kept in memory, and added to `cache`
    when it lacks it. Raises NxwrightError when resvg cannot draw it."""
    kept = cache.get_drawn_svg(drawing.key) if cache is not None else None
    with _drawn_lock:
        kept_here = _drawn.get(drawing.key)
    png = kept or kept_here or _draw(drawing)
    # One drawn earlier in this process, as by the checks, goes in the cache too.
    if cache is not None and kept is None:
        cache.add_drawn_svg(drawing.key, png)
    _keep(drawing.key, png)
    return png


def draw_svg_picture(path: str, read_text, read_bytes, defines: dict, cache=None) -> bytes:
    """Returns the PNG picture of the SVG picture whose file is `path`
    (prepared_svg_picture, drawn_svg_picture)."""
    return drawn_svg_picture(prepared_svg_picture(path, read_text, read_bytes, defines), cache)


def svg_picture_data_url(path: str, read_text, read_bytes, defines: dict) -> tuple:
    """Returns (the PNG data URL of the SVG picture whose file is `path`, the
    key of its drawing), for a webview that shows it."""
    drawing = prepared_svg_picture(path, read_text, read_bytes, defines)
    return data_url(drawn_svg_picture(drawing)), drawing.key


def _keep(key: str, png: bytes):
    """Keeps `png` in memory, as the last used, and forgets those used
    longest ago past _KEPT_BYTES."""
    with _drawn_lock:
        _drawn[key] = png
        _drawn.move_to_end(key)
        total = sum(len(kept) for kept in _drawn.values())
        while total > _KEPT_BYTES and len(_drawn) > 1:
            total -= len(_drawn.popitem(last=False)[1])


def _draw(drawing: SvgDrawing) -> bytes:
    """Draws `drawing` with resvg."""
    fonts = [str(NOTO_SANS)] + [str(_font_file(data)) for data in drawing.fonts]
    try:
        # resvg's log goes to standard output, which carries the language
        # server's and the debugger's messages, so it is never turned on.
        png = resvg_py.svg_to_bytes(
            svg_string=drawing.text, skip_system_fonts=True, font_files=fonts,
            font_family=_NOTO_SANS_FAMILY, serif_family=_NOTO_SANS_FAMILY,
            sans_serif_family=_NOTO_SANS_FAMILY, cursive_family=_NOTO_SANS_FAMILY,
            fantasy_family=_NOTO_SANS_FAMILY, monospace_family=_NOTO_SANS_FAMILY)
    except (ValueError, RuntimeError) as error:
        raise NxwrightError("%s cannot be drawn: %s" % (drawing.files[0], error)) from None
    return bytes(png)


def _font_file(data: bytes) -> Path:
    """Returns a file holding the font `data`, for resvg, which reads fonts
    from files only. Each font is written once, named by its hash, in the
    computer's folder of temporary files. That folder is shared by the
    computer's users, so a file found there is used only once it is seen to
    hold `data`."""
    folder = Path(tempfile.gettempdir()) / "nxwright-svg-fonts"
    path = folder / hashlib.sha256(data).hexdigest()
    if path in _checked_fonts or _file_holds(path, data):
        _checked_fonts.add(path)
        return path
    # Written beside it, then renamed, so that a process or a thread drawing
    # at the same time never reads half a font.
    written = path.with_name("%s.%d.%d" % (path.name, os.getpid(), threading.get_ident()))
    try:
        folder.mkdir(parents=True, exist_ok=True)
        written.write_bytes(data)
        os.replace(written, path)
    except OSError as error:
        if not _file_holds(path, data):
            raise NxwrightError("cannot write a font for drawing SVG pictures to %s: %s"
                                % (folder, error.strerror or error)) from None
        # Written meanwhile by another process or thread.
        written.unlink(missing_ok=True)
    _checked_fonts.add(path)
    return path


class _Preparation:
    """Puts the files an SVG picture shares into its text
    (prepared_svg_picture)."""

    def __init__(self, path: str, read_text, read_bytes, defines: dict):
        self.path, self.read_text, self.read_bytes = path, read_text, read_bytes
        self.defines = defines
        self.files = [path]
        self.declared = []      # [(file, name, value)] (SvgDrawing.declared)
        self.origins = {}       # {element copied from a shared file: that file}
        self.parsed = {}        # {path: the root of a shared SVG file}
        self.imported = {}      # {(path, id): the id of its copy in the picture}
        self.following = []     # [(path, id)] of the copies whose links are being followed
        self.owners = {}        # {id in the picture: the file it comes from}
        self.root = None        # the picture's root element
        self.defs = None        # the <defs> that holds the copies

    def prepared(self) -> SvgDrawing:
        text = self._text(self.path, [])
        root = self.root = _parsed(self.path, text)
        width, height = _size(self.path, root)
        for element in root.iter():
            if element.get("id") is not None:
                self.owners[element.get("id")] = self.path
        css, faces = self._style_sheets(text)
        own_css = []
        for element in root.iter():
            if _local(element) == "style":
                element.text = self._css_with_values(element.text or "", self.path)
                own_css.append(element.text)
                faces += _font_faces(element.text, self.path)
        self._links(list(root.iter()), self.path, [self.path])
        self._attributes_with_values(root)
        if css:
            style = ElementTree.Element(_like(root, "style"))
            style.text = "\n".join(_without_font_faces(sheet) for sheet in css)
            root.insert(0, style)
        fonts, families = self._fonts(faces)
        _check_fonts(self.path, root, css + own_css, families)
        prepared = ElementTree.tostring(root, encoding="unicode")
        return SvgDrawing(prepared, tuple(fonts), width, height, _drawing_key(prepared, fonts),
                          tuple(self.files), tuple(self.declared))

    def _css_with_values(self, css: str, css_path: str) -> str:
        """Returns the style sheet `css`, of the file `css_path`, with each
        define it names in place, once its declarations for other viewers are
        noted."""
        _check_no_import(css, css_path)
        self.declared += [(css_path, name, value.strip())
                          for name, value in _DECLARATION.findall(css)]
        return _with_values(css, self.defines, css_path)

    def _attributes_with_values(self, root):
        """Puts the defines that the attributes of `root` and its elements
        name in place: in a style value, through var(), and as a text's text,
        through data-nxwright-text."""
        for element in root.iter():
            # The file the element comes from: the picture's, or a shared file's.
            origin = self.origins.get(element, self.path)
            style = element.get("style")
            if style is not None:
                self.declared += [(origin, name, value.strip())
                                  for name, value in _DECLARATION.findall(style)]
            for key, value in element.attrib.items():
                if _VAR.search(value):
                    element.set(key, _with_values(value, self.defines, origin))
            name = element.attrib.pop(_TEXT_FROM_DEFINE, None)
            if name is not None:
                _set_text(origin, element, name, self.defines)

    def _fonts(self, faces: list) -> tuple:
        """Returns (the bytes of the font file of each of `faces`, which are
        (family, font file) pairs, and the families the drawing has, in
        lower case). Raises NxwrightError for a file whose family is not the
        one its rule gives."""
        fonts = []
        families = {_NOTO_SANS_FAMILY.lower()} | set(_GENERIC_FAMILIES)
        for family, font_path in faces:
            data = self._bytes(font_path, [self.path])
            _check_font_family(font_path, data, family)
            families.add(family.lower())
            fonts.append(data)
        return fonts, families

    def _style_sheets(self, text: str) -> tuple:
        """Returns (the text of each style sheet the picture links, in order,
        the [(family, font file)] their @font-face rules name)."""
        sheets, faces = [], []
        prolog = text[:_ROOT_START.search(re.sub(r"<\?.*?\?>|<!--.*?-->|<!DOCTYPE[^>]*>",
                                                 lambda found: " " * len(found[0]), text,
                                                 flags=re.S)).start()]
        for found in _STYLESHEET.finditer(prolog):
            attributes = {name.lower(): value
                          for name, _, value in _PSEUDO_ATTRIBUTE.findall(found[1])}
            if attributes.get("type", "text/css").lower() != "text/css":
                raise NxwrightError("%s: a style sheet must be CSS (type=\"text/css\")"
                                    % self.path)
            if "href" not in attributes:
                raise NxwrightError("%s: <?xml-stylesheet?> names no file (href)" % self.path)
            sheet_path = _linked_path(self.path, attributes["href"], "the style sheet")
            sheet = self._css_with_values(self._text(sheet_path, [self.path]), sheet_path)
            sheets.append(sheet)
            faces += _font_faces(sheet, sheet_path)
        return sheets, faces

    def _links(self, elements: list, base: str, chain: list):
        """Follows the links of `elements`, which come from the file `base`,
        reached through the files of `chain`: a <use> of another file's
        element now refers to its copy, and an <image> of a file holds the
        file's data."""
        for element in elements:
            name = _local(element)
            if name not in ("use", "image"):
                continue
            key, href = _href(element)
            if href is None or href.startswith("#") or href.startswith("data:"):
                continue
            if name == "image":
                image_path = _linked_path(base, href, "the image")
                media_type = _IMAGE_TYPES.get(posixpath.splitext(image_path)[1].lower())
                if media_type is None:
                    raise NxwrightError("%s: the image %s is not a PNG, JPEG, GIF, WebP, or SVG "
                                        "file" % (_through(chain), href))
                element.set(key, data_url(self._bytes(image_path, chain), media_type))
            else:
                file, hash_sign, element_id = href.partition("#")
                if not hash_sign or not element_id:
                    raise NxwrightError("%s: <use href=\"%s\"> must name an element of the "
                                        "file, as in parts.svg#frame" % (_through(chain), href))
                shared = _linked_path(base, file, "the shared file")
                element.set(key, "#" + self._imported(shared, unquote(element_id), chain))

    def _imported(self, shared: str, element_id: str, chain: list) -> str:
        """Copies the element `element_id` of the SVG file `shared` into the
        picture's <defs>, with what it refers to in its file, unless done
        already, and returns its id in the picture."""
        if any(_holds(self._shared_root(path, chain), copied_id, element_id)
               for path, copied_id in self.following if path == shared):
            raise NxwrightError("%s: %s#%s uses itself, directly or through other shapes"
                                % (_through(chain + [shared]), shared, element_id))
        if (shared, element_id) in self.imported:
            return self.imported[(shared, element_id)]
        root = self._shared_root(shared, chain)
        by_id = {element.get("id"): element for element in root.iter()
                 if element.get("id") is not None}
        copies = self._copies(shared, root, by_id, self._wanted(shared, element_id, by_id, chain))
        for copied in copies:
            self.following.append((shared, copied.get("id")))
            self._links(list(copied.iter()), shared, chain + [shared])
            self.following.pop()
            self._defs().append(copied)
        return element_id

    def _wanted(self, shared: str, element_id: str, by_id: dict, chain: list) -> list:
        """Returns the ids of the elements of the file `shared` to copy for
        its element `element_id`: it, and what it refers to in its file,
        unless copied already. `by_id` holds the file's elements by id."""
        wanted, done = [element_id], []
        while wanted:
            wanted_id = wanted.pop()
            if wanted_id in done or (shared, wanted_id) in self.imported:
                continue
            if wanted_id not in by_id:
                raise NxwrightError("%s: %s has no element with id %s"
                                    % (_through(chain + [shared]), shared, wanted_id))
            original = by_id[wanted_id]
            done.append(wanted_id)
            # What the element refers to within its file comes too.
            inside = {element.get("id") for element in original.iter()}
            for element in original.iter():
                for value in element.attrib.values():
                    wanted += [found for found in _REFERENCE.findall(value) if found not in inside]
                _, href = _href(element)
                if href is not None and href.startswith("#") and href[1:] not in inside:
                    wanted.append(href[1:])
        return done

    def _copies(self, shared: str, root, by_id: dict, done: list) -> list:
        """Returns copies of the elements `done` of the file `shared`, whose
        root is `root`, leaving out one that another of them holds. Raises
        NxwrightError for an id the picture has from another file."""
        copies = []
        for done_id in done:
            if any(ancestor in done for ancestor in _ancestor_ids(root, by_id[done_id])):
                continue    # copied with an element that holds it
            copied = copy.deepcopy(by_id[done_id])
            for parent in list(copied.iter()):
                for index, child in reversed(list(enumerate(parent))):
                    if _local(child) == "style":
                        # The style of the shared file does not apply in the picture.
                        parent.remove(child)
                    elif (shared, child.get("id")) in self.imported:
                        # A shape copied before, by itself, stays the only
                        # one with its id: this copy uses it.
                        parent[index] = _use_of(parent, child)
            for element in copied.iter():
                own_id = element.get("id")
                if own_id is None:
                    continue
                if own_id in self.owners and self.owners[own_id] != shared:
                    raise NxwrightError("%s and %s both have an element with id %s"
                                        % (self.owners[own_id], shared, own_id))
                self.owners[own_id] = shared
                self.imported[(shared, own_id)] = own_id
            self.origins.update((element, shared) for element in copied.iter())
            copies.append(copied)
        return copies

    def _defs(self):
        """The <defs> element of the picture that holds the copies."""
        if self.defs is None:
            self.defs = ElementTree.Element(_like(self.root, "defs"))
            self.root.append(self.defs)
        return self.defs

    def _shared_root(self, shared: str, chain: list):
        if shared not in self.parsed:
            if not shared.lower().endswith(SVG_SUFFIX):
                raise NxwrightError("%s: %s is not an SVG file" % (_through(chain), shared))
            self.parsed[shared] = _parsed(shared, self._text(shared, chain))
        return self.parsed[shared]

    def _text(self, path: str, chain: list) -> str:
        # Noted before it is read, so that a missing file is among those tried.
        if path not in self.files:
            self.files.append(path)
        try:
            return self.read_text(path)
        except NxwrightError as error:
            raise NxwrightError("%s: %s" % (_through(chain), error) if chain else str(error)) \
                from None

    def _bytes(self, path: str, chain: list) -> bytes:
        if path not in self.files:
            self.files.append(path)
        try:
            data = self.read_bytes(path)
        except FileNotFoundError:
            raise NxwrightError("%s: %s is missing" % (_through(chain), path)) from None
        except OSError as error:
            raise NxwrightError("%s: %s cannot be read (%s)"
                                % (_through(chain), path, error.strerror or error)) from None
        return data


def _with_values(text: str, defines: dict, where: str) -> str:
    """Returns `text`, CSS or an attribute's value from the file `where`,
    with each var(--NAME), with or without a fallback, replaced by the
    value of the define NAME. Raises NxwrightError for a var() that names
    no define, or is not closed, and for a value that would change the CSS
    around it."""
    parts, start = [], 0
    for found in _VAR.finditer(text):
        if found.start() < start:
            continue    # within the fallback of a var() replaced already
        name = found[1]
        if name not in defines:
            raise NxwrightError("%s: var(--%s) does not name a define of app.toml"
                                % (where, name))
        end = _closing(text, found.start() + len("var"))
        if end is None:
            raise NxwrightError("%s: var(--%s has no closing parenthesis" % (where, name))
        value = str(defines[name])
        if _NOT_IN_CSS.search(value):
            raise NxwrightError("%s: the define %s cannot be a style value, because its value %r "
                                "would change the CSS around it" % (where, name, value))
        parts += [text[start:found.start()], value]
        start = end + 1
    return "".join(parts) + text[start:]


def _closing(text: str, opening: int):
    """Returns the place of the parenthesis that closes the one at
    `opening` in `text`, or None."""
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _set_text(path: str, element, name: str, defines: dict):
    """Gives the text element `element` of the file `path` the value of the
    define `name` as its text (data-nxwright-text)."""
    if _local(element) not in ("text", "tspan"):
        raise NxwrightError("%s: %s is on a <%s>. Put it on a <text> or a <tspan>"
                            % (path, _TEXT_FROM_DEFINE, _local(element)))
    if name not in defines:
        raise NxwrightError("%s: %s=\"%s\" does not name a define of app.toml"
                            % (path, _TEXT_FROM_DEFINE, name))
    if len(element):
        raise NxwrightError("%s: the <%s> whose text is the define %s contains other elements, "
                            "which its text would replace" % (path, _local(element), name))
    element.text = str(defines[name])


def _use_of(parent, element):
    """Returns a <use> of `element`, by its id, to stand in its place within
    `parent`."""
    use = ElementTree.Element(_like(parent, "use"), {"href": "#" + element.get("id")})
    use.tail = element.tail
    return use


def _drawing_key(prepared: str, fonts: list) -> str:
    """Returns the hash of all that decides a drawing: the SVG text
    `prepared`, the bytes of its `fonts`, resvg's version, and the code that
    draws, with nxwright's Noto Sans."""
    digest = hashlib.sha256()
    for part in (*_drawing_code(), prepared):
        digest.update(part.encode("utf-8") + b"\0")
    for data in fonts:
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


@functools.cache
def _drawing_code() -> tuple:
    """Returns what changes how a picture is drawn, beside its files: the
    renderer's version, and the hash of this module's code with nxwright's
    Noto Sans. Taken once, at the first drawing, so that the code that runs
    is what it describes, and so that a command without SVG pictures does
    not read these files."""
    code = hashlib.sha256(Path(__file__).read_bytes() + NOTO_SANS.read_bytes()).hexdigest()
    return metadata.version("resvg-py"), code


def _file_holds(path: Path, data: bytes) -> bool:
    """Returns whether the file at `path` holds `data`."""
    try:
        return path.read_bytes() == data
    except OSError:
        return False


def _through(chain: list) -> str:
    """Names a file reached through others: "pictures/home.svg, through
    art/parts.svg"."""
    return chain[0] + "".join(", through %s" % path for path in chain[1:])


def _parsed(path: str, text: str):
    """Returns the root element of the SVG text `text` of the file `path`.
    Raises NxwrightError when it is not an SVG file."""
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as error:
        raise NxwrightError("%s is not an SVG file: %s" % (path, error)) from None
    if _local(root) != "svg":
        raise NxwrightError("%s is not an SVG file: its root is <%s>, not <svg>"
                            % (path, _local(root)))
    return root


def _size(path: str, root) -> tuple:
    """Returns the (width, height) the root element `root` gives, in whole
    pixels."""
    size = []
    for dimension in ("width", "height"):
        value = root.get(dimension)
        found = _SIZE.fullmatch(value) if value is not None else None
        if found is not None and int(found[1]) > _MOST_PIXELS:
            raise NxwrightError("%s: the picture's %s, %s, is more than %d pixels"
                                % (path, dimension, value, _MOST_PIXELS))
        if found is None or int(found[1]) == 0:
            raise NxwrightError("%s: the <svg> element must give the picture's %s in whole "
                                "pixels, as in %s=\"800\"%s"
                                % (path, dimension, dimension,
                                   "" if value is None else ", not %s" % value))
        size.append(int(found[1]))
    return tuple(size)


def _local(element) -> str:
    """Returns an element's name without its namespace."""
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _like(root, name: str) -> str:
    """Returns the tag of a new element `name` in the namespace of `root`."""
    return "{%s}%s" % (_SVG, name) if root.tag.startswith("{%s}" % _SVG) else name


def _href(element) -> tuple:
    """Returns (the attribute's key, its value) of the element's link,
    href or xlink:href, or (None, None)."""
    for key in ("href", "{%s}href" % _XLINK):
        if element.get(key) is not None:
            return key, element.get(key).strip()
    return None, None


def _holds(root, holder_id: str, element_id: str) -> bool:
    """Returns whether the element `holder_id` of the file whose root is
    `root` is, or holds, its element `element_id`."""
    holder = next((element for element in root.iter() if element.get("id") == holder_id), None)
    return holder is not None and any(element.get("id") == element_id
                                      for element in holder.iter())


def _ancestor_ids(root, element) -> list:
    """Returns the ids of the elements of `root` that hold `element`."""
    parents = {child: parent for parent in root.iter() for child in parent}
    found = []
    while element in parents:
        element = parents[element]
        if element.get("id") is not None:
            found.append(element.get("id"))
    return found


def _linked_path(base: str, href: str, what: str) -> str:
    """Returns the path within the source folder of the file `href` names,
    relative to the file `base`. Raises NxwrightError for a path that
    leaves the folder, and a URL."""
    href = unquote(href.strip())
    if _SCHEME.match(href) or href.startswith(("/", "\\")):
        raise NxwrightError("%s: %s %s must be a path relative to %s, within the source folder"
                            % (base, what, href, base))
    path = posixpath.normpath(posixpath.join(posixpath.dirname(base), href.replace("\\", "/")))
    if path == ".." or path.startswith("../"):
        raise NxwrightError("%s: %s %s is outside the source folder" % (base, what, href))
    return path


def _check_no_import(css: str, css_path: str):
    """Raises NxwrightError for an @import in the style sheet `css`, whose
    file is `css_path`: resvg ignores it, so the rules it brings would be
    missing with no error."""
    if _IMPORT.search(css):
        raise NxwrightError("%s: @import is not followed: link each style sheet from the "
                            "picture with <?xml-stylesheet?>" % css_path)


def _font_faces(css: str, css_path: str) -> list:
    """Returns [(family, font file)] of the @font-face rules of the style
    sheet `css`, whose file is `css_path`."""
    faces = []
    for found in _FONT_FACE.finditer(css):
        family = _FONT_FAMILY.search(found[1])
        url = _URL.search(found[1])
        if family is None or url is None:
            raise NxwrightError("%s: an @font-face rule needs a font-family and a src: url(...)"
                                % css_path)
        faces.append((_family_names(family[1])[0],
                      _linked_path(css_path, url[2], "the font file")))
    return faces


def _without_font_faces(css: str) -> str:
    """Returns the style sheet `css` without its @font-face rules, which
    resvg does not read: nxwright gives it their files."""
    return _FONT_FACE.sub("", css)


def _family_names(value: str) -> list:
    """Returns the families of a font-family value, without quotes."""
    return [name.strip().strip("\"'").strip() for name in value.split(",") if name.strip()]


def _check_font_family(font_path: str, data: bytes, family: str):
    """Raises NxwrightError unless the font file `font_path`, whose bytes are
    `data`, is of the family `family`, which an @font-face rule gives it:
    resvg knows a font by the family its file names."""
    try:
        own = freetype.Face(io.BytesIO(data)).family_name
    except freetype.FT_Exception:
        raise NxwrightError("%s is not a font file" % font_path) from None
    own = own.decode("utf-8", "replace") if isinstance(own, bytes) else str(own)
    if own.lower() != family.lower():
        raise NxwrightError("%s is of the family %s, so its @font-face rule must say "
                            "font-family: \"%s\", not \"%s\"" % (font_path, own, own, family))


def _check_fonts(path: str, root, sheets: list, families: set):
    """Raises NxwrightError for a font-family list of the picture whose
    families are none of `families`, those the drawing has (lower case),
    and for the `font` shorthand, which can name a family too."""
    lists = []
    for element in root.iter():
        if element.get("font-family") is not None:
            lists.append(element.get("font-family"))
        style = element.get("style") or ""
        if _FONT_SHORTHAND.search(style):
            _refuse_shorthand(path)
        lists += _FONT_FAMILY.findall(style)
    for sheet in sheets:
        sheet = _without_font_faces(sheet)
        if _FONT_SHORTHAND.search(sheet):
            _refuse_shorthand(path)
        lists += _FONT_FAMILY.findall(sheet)
    for value in lists:
        names = _family_names(value.replace("!important", ""))
        if not names or names[0].lower() in _FONT_KEYWORDS:
            continue
        if not any(name.lower() in families for name in names):
            raise NxwrightError("%s: no font is given for font-family: %s. Use Noto Sans, a "
                                "generic family such as sans-serif, or a font file that an "
                                "@font-face rule of a style sheet names" % (path, value.strip()))


def _refuse_shorthand(path: str):
    raise NxwrightError("%s: give a text's font with font-family, not the font shorthand"
                        % path)
