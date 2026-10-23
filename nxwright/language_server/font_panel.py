"""The language server's answers for nxwright's Fonts panel in VS Code
(editors/vscode/src/fontPanel.ts): a source folder's fonts, each with a
sample of a text drawn in it (drawing/font_samples.py); the typefaces
installed on the computer that nxwright can draw a font from in the folder's
encoding; samples of a font about to be added, drawn from a typeface file or
ready-made, with what adding it would do; and adding it (add_font and
add_font_file in source/resource_adding.py). And, for the font viewer
(editors/vscode/src/fontViewer.ts), one font file's details and sample
(font_file_details).

A sample is a PNG picture, as a data: URL, under "sample". Where none can be
drawn, "noSample" says why. A font about to be added has under "refusal" why
adding it would be refused, or None.
"""
from dataclasses import replace
from functools import cache
from pathlib import Path

from nxwright import NxwrightError
from nxwright.project.device_settings import TextCodec
from nxwright.project.font_drawing import check_drawable, code_point_ranges, code_points_of
from nxwright.project.installed_typefaces import installed_typefaces
from nxwright.project.pictures import data_url
from nxwright.project.truetype import TrueTypeFont
from nxwright.project.zi_font import (FONT_ENCODINGS, GRID_ENCODINGS, UTF8, decode_font,
                                      font_facts)
from nxwright.drawing.font_samples import font_sample, sample_font, sample_note
from nxwright.source.source_folder import drawn_font_name
from nxwright.source.resource_adding import (add_font, add_font_file, check_drawn_font,
                                             folder_fonts, font_settings, ready_made_font,
                                             ready_made_font_name)


class FontPanelAnswers:
    """The answers for the Fonts panel. It keeps the typefaces found for each
    encoding, since looking for them takes about half a second: the
    typefaces request looks again, and the fonts request uses what was found
    last."""

    def __init__(self):
        self._typefaces = {}     # {encoding: [Typeface]}

    def fonts(self, root: Path, text: str, colour: tuple) -> dict:
        """Returns {"encoding", "drawable", "fonts"}: the folder's encoding,
        whether nxwright draws fonts in it, and its fonts in ID order, each
        {"name", "height", "encoding", "rotation", "smoothed", "characters"},
        with a sample of `text` in `colour`, and "like", the installed
        typeface a font drawn from it would be named after, or None. A font
        in an encoding nxwright draws gives "ranges" too, its code points as
        a utf-8 folder's Characters field takes them (code_point_ranges)."""
        names, settings = folder_fonts(root)
        encoding = font_settings(settings).encoding
        typefaces = self._found(encoding)
        fonts = []
        for name in names:
            entry = {"name": name}
            try:
                block = (root / "fonts" / (name + ".zi")).read_bytes()
                facts = font_facts(block)
            except (OSError, NxwrightError) as error:
                entry["noSample"] = str(error)
                fonts.append(entry)
                continue
            # Decoded once, as a font in utf-8 takes some 20 ms to.
            decoded = cache(lambda: decode_font(block))
            entry.update(_details(facts, decoded, text, encoding, colour))
            # Its code points, which a font like it is drawn of in a utf-8
            # folder, as the form's Characters field takes them: of a font
            # in an encoding nxwright draws, but a two-byte one, which holds
            # every position of its grid rather than chosen characters.
            if facts.encoding in FONT_ENCODINGS and facts.encoding not in GRID_ENCODINGS:
                try:
                    entry["ranges"] = code_point_ranges(_code_points(decoded(), facts.encoding))
                except NxwrightError:
                    pass        # its sample says why it cannot be read
            like = next((typeface for typeface in typefaces
                         if drawn_font_name(typeface.name, typeface.path, facts.height) == name),
                        None)
            entry["like"] = like and {"name": like.name, "path": str(like.path)}
            fonts.append(entry)
        return {"encoding": encoding, "drawable": encoding in FONT_ENCODINGS,
                "fonts": fonts}

    def typefaces(self, root: Path) -> dict:
        """Returns {"typefaces": [{"name", "path"}]}, the installed typefaces
        nxwright can draw a font from in the folder's encoding, looked for
        anew; none in an encoding nxwright does not draw fonts in."""
        encoding = _encoding(root)
        self._typefaces.pop(encoding, None)
        return {"typefaces": [{"name": typeface.name, "path": str(typeface.path)}
                              for typeface in self._found(encoding)]}

    def _found(self, encoding: str) -> list:
        if encoding not in FONT_ENCODINGS:
            return []
        if encoding not in self._typefaces:
            self._typefaces[encoding] = installed_typefaces(encoding)
        return self._typefaces[encoding]


def typeface_sample(root: Path, typeface_file: Path, height, smoothed: bool, name: str,
                    text: str, colour: tuple, characters: str = None,
                    full_table: bool = False) -> dict:
    """Returns {"name", "refusal"}, and a sample of `text` in `colour`, of the
    font add_font would draw from a typeface file, `height` pixels tall,
    smoothed or not, in a utf-8 folder of the code points `characters`
    gives, a `full_table` or not: its name, `name` or else the one add_font
    gives, and why add_font would refuse it; and {"warning"}, when the
    typeface lacks some of the characters, which the font would leave out
    (font_drawing.font_warning). The sample draws a character the font would
    not hold as the screen would, and its note says so."""
    encoding = _encoding(root)
    try:
        height = _whole_height(height)
    except NxwrightError as error:
        return {"name": name, "refusal": str(error), "noSample": str(error)}
    try:
        typeface = TrueTypeFont(Path(typeface_file).read_bytes())
    except (OSError, NxwrightError) as error:
        return {"name": name, "refusal": str(error), "noSample": str(error)}
    name = name or drawn_font_name(typeface.typeface_name(), typeface_file, height)
    # The characters first: the sample is of them, whatever else is refused.
    try:
        code_points = None if characters is None else code_points_of(characters)
    except NxwrightError as error:
        return {"name": name, "refusal": str(error), "noSample": str(error)}
    reply = {"name": name, "refusal": None}
    try:
        check_drawn_font(root, name)
        warning = check_drawable(typeface, height, encoding, code_points, full_table)
        if warning:
            reply["warning"] = warning
    except NxwrightError as error:
        reply["refusal"] = str(error)
    reply.update(_sample(lambda: sample_font(typeface, height, encoding, smoothed, text,
                                             code_points, full_table),
                         text, encoding, colour, name))
    return reply


def font_file_sample(root: Path, font_file: Path, name: str, text: str, colour: tuple) -> dict:
    """Returns {"name", "refusal", "turned", "warning"}, and a sample of
    `text` in `colour`, of a ready-made font file as add_font_file would add
    it: its name, `name` or else the one add_font_file gives; why it would be
    refused; whether it would be turned to the folder's rotation; and the
    warning it would come with."""
    encoding = _encoding(root)
    try:
        block = Path(font_file).read_bytes()
    except OSError as error:
        return {"name": name, "refusal": str(error), "noSample": str(error)}
    reply = {"name": name or ready_made_font_name(block, font_file), "refusal": None,
             "turned": False, "warning": None}
    try:
        font = ready_made_font(root, font_file, reply["name"])
        reply.update(turned=font.turned, warning=font.warning)
    except NxwrightError as error:
        reply["refusal"] = str(error)
    reply.update(_sample(lambda: decode_font(block), text, encoding, colour))
    return reply


def font_file_details(font_file: Path, text: str, colour: tuple) -> dict:
    """Returns, for the font viewer, {"name", "folder"} of a font file, its
    name being the file's, and "folder" the source folder whose font it is,
    or None: the folder above its fonts/ folder, when that folder's app.toml
    lists it. With them, as the Fonts panel lists a font: {"height",
    "encoding", "rotation", "smoothed", "characters"} and a sample of `text`
    in `colour`, drawn in the folder's encoding, or the font's own outside a
    folder or in one whose app.toml gives no screen settings; or
    {"noSample"}, why the file cannot be read."""
    font_file = Path(font_file)
    reply = {"name": font_file.stem, "folder": None}
    # The folder's encoding, when the folder lists the font and its app.toml
    # gives screen settings; else the font's own.
    encoding = None
    try:
        names, settings = folder_fonts(font_file.parent.parent)
        if font_file.parent.name == "fonts" and font_file.stem in names:
            reply["folder"] = str(font_file.parent.parent)
            encoding = font_settings(settings).encoding
    except (OSError, NxwrightError):
        pass
    try:
        block = font_file.read_bytes()
        facts = font_facts(block)
    except (OSError, NxwrightError) as error:
        return dict(reply, noSample=str(error))
    return dict(reply, **_details(facts, cache(lambda: decode_font(block)),
                                  text, encoding or facts.encoding, colour))


def add(root: Path, params: dict) -> dict:
    """Adds a font to the folder, as the panel's request asks: drawn from the
    typeface file "typeface", "height" pixels tall, "smoothed" or not, in a
    utf-8 folder of the "characters" given; or the ready-made font file
    "file". Its name is "name", or else the one the adding gives. A utf-8
    font is a full table when "fullTable" is true. Returns {"name",
    "warning"}."""
    name = params.get("name") or None
    if "typeface" in params:
        name, warning = add_font(root, Path(params["typeface"]),
                                 _whole_height(params["height"]), name,
                                 bool(params.get("smoothed", True)), params.get("characters"),
                                 bool(params.get("fullTable", False)))
        return {"name": name, "warning": warning}
    name, warning = add_font_file(root, requested_font_file(params), name)
    return {"name": name, "warning": warning}


def requested_font_file(params: dict) -> Path:
    """Returns the ready-made font file a request names, "file". Raises
    NxwrightError for a request that names neither it nor a typeface file,
    "typeface"."""
    if "file" not in params:
        raise NxwrightError('the request names neither a typeface file ("typeface") nor a '
                            'font file ("file")')
    return Path(params["file"])


def _encoding(root: Path) -> str:
    """Returns the folder's encoding. Raises NxwrightError for a folder whose
    app.toml gives no screen settings."""
    return font_settings(folder_fonts(root)[1]).encoding


def _whole_height(height) -> int:
    """Returns a font's height as the panel gives it, as a whole number.
    Raises NxwrightError when it is none."""
    try:
        return int(height)
    except (TypeError, ValueError):
        raise NxwrightError("the height is not a whole number") from None


def _code_points(font, encoding: str) -> list:
    """Returns the code points of a decoded font's characters, in order: in
    utf-8, its codes; in a one-byte encoding, the characters its bytes stand
    for there, a byte that stands for none left out."""
    if encoding == UTF8:
        return sorted(font.characters)
    points = set()
    codec = TextCodec(encoding).codec_name
    for code in font.characters:
        try:
            points.add(ord(bytes([code]).decode(codec)))
        except UnicodeDecodeError:
            continue
    return sorted(points)


def _details(facts, font_of, text: str, encoding: str, colour: tuple) -> dict:
    """Returns what the Fonts panel and the font viewer show of a font, from
    its `facts` (zi_font.font_facts): {"height", "encoding", "rotation",
    "smoothed", "characters"}, and a sample of `text` in the font
    `font_of()` gives, in `encoding` and `colour` (_sample)."""
    return dict(height=facts.height, encoding=facts.encoding, rotation=facts.rotation,
                smoothed=facts.smoothed, characters=facts.character_count,
                **_sample(font_of, text, encoding, colour))


def _sample(font_of, text: str, encoding: str, colour: tuple, name: str = None) -> dict:
    """Returns {"sample"}, a sample of `text` in the font `font_of()` gives,
    with {"sampleNote"} when the font lacks some of its characters
    (font_samples.sample_note), which names the font `name` when given; or
    {"noSample"}, why there is none."""
    try:
        font = font_of()
        reply = {"sample": data_url(font_sample(font, text, encoding, colour))}
        note = sample_note(replace(font, name=name) if name else font, text, encoding)
    except NxwrightError as error:
        return {"noSample": str(error)}
    if note:
        reply["sampleNote"] = note
    return reply
