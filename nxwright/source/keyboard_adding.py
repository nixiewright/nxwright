"""Adding one of nxwright's keyboard pages to a source folder: its page and
code files, laid out for the folder's screen, and its font, drawn for it
unless the folder holds a font of that name. What each keyboard is, its keys
and their layout, is keyboards.py's. The Chinese keyboard's font is drawn in
gb2312 from a typeface file, or is one of the folder's fonts in gb2312
(chinese_keyboard_fonts).
"""
from pathlib import Path

from nxwright import NxwrightError
from nxwright.language.resource_names import check_names
from nxwright.project.font_drawing import draw_font_block, font_warning
from nxwright.project.truetype import TrueTypeFont
from nxwright.project.zi_font import UTF8, decode_font, text_codes
from nxwright.source.device_keys import settings_from_keys
from nxwright.source.keyboards import (CHINESE_INPUT, KEYBOARD_PAGES, UTF8_CHARACTERS,
                                       chinese_font_height, chinese_label_characters,
                                       font_widths, keyboard, keyboard_font, typeface_widths)
from nxwright.source.page_source import page_toml_path
from nxwright.source.source_folder import (FONT_SUFFIX, app_text, drawn_font_name, folder_reader,
                                           noto_sans_lacks, parse_app, parsed_page_toml,
                                           read_bytes, read_text)

# The encoding of the Chinese keyboard's font and candidates.
_GB2312 = "gb2312"


def add_keyboard(source_folder: Path, kind: str, typeface: Path = None, font: str = None) -> tuple:
    """Adds nxwright's keyboard page of `kind`, a name of KEYBOARD_PAGES, to a
    source folder (keyboards.py): its page and code files, laid out for the
    folder's screen at its rotation, and its font, unless the folder has a
    font of that name, which it then uses as it is. The page and a new font
    are listed in app.toml after the folder's others.

    The Chinese keyboard (keyboards.CHINESE_INPUT) takes its font from
    exactly one of `typeface`, a typeface file with Chinese characters, which
    it is drawn from in gb2312, or `font`, the name of a gb2312 font the
    folder holds (_chinese_keyboard).

    Returns (the page's name, the font's name, a warning or None). The
    warning says that the font is in another encoding than the folder's, so
    that a caller's text beyond ascii shows garbled in the keyboard's field;
    or, of a utf-8 font it draws, which characters the font holds, as a
    caller's text in another shows a gap; or, of the Chinese keyboard's font
    drawn from a typeface, which characters the typeface lacks.

    Raises NxwrightError, before writing anything, for a folder without
    screen settings, one that has that keyboard already, as a page of any
    name marked as that system page, one with a page of the keyboard's name
    that is another page, or a file already at the place of one the
    keyboard adds; for the Chinese keyboard in a folder of another encoding
    than gb2312, and for its font as _chinese_keyboard refuses it; and for
    `typeface` or `font` given another keyboard.
    """
    if kind not in KEYBOARD_PAGES:
        raise NxwrightError("%r is not a keyboard; they are %s" % (kind, ", ".join(KEYBOARD_PAGES)))
    chinese = kind == CHINESE_INPUT
    if not chinese and (typeface is not None or font is not None):
        raise NxwrightError("only the Chinese keyboard takes --typeface or --font: the others "
                            "draw their font from Noto Sans")
    source_folder = Path(source_folder)
    app = parse_app(read_text(source_folder / "app.toml"))
    settings = settings_from_keys(app)
    if settings is None:
        raise NxwrightError("app.toml gives no screen settings, so the keyboard's size, "
                            "rotation, and encoding are not known")
    if chinese and settings.encoding != _GB2312:
        raise NxwrightError("the Chinese keyboard only works in a gb2312 folder, and this one "
                            "is in %s. To change it: nxwright device %s --encoding gb2312"
                            % (settings.encoding, source_folder))
    page = KEYBOARD_PAGES[kind]
    present = keyboard_page(folder_reader(source_folder), app["pages"], kind)
    if present:
        raise NxwrightError("the folder has the %s already: page %s" % (kind, present))
    for name in app["pages"]:
        if name.lower() == page.lower():
            raise NxwrightError("the folder has a page named %s that is not the %s"
                                % (name, kind))
    fonts = app["fonts"]
    if chinese:
        made, block, warning = _chinese_keyboard(source_folder, fonts, settings, typeface, font)
    else:
        made = keyboard(kind, *settings.page_size)
        block = (None if made.font_name in fonts
                 else keyboard_font(made, settings.rotation, settings.encoding))
    files = {page_toml_path(page): made.page_toml.encode("utf-8"),
             "pages/%s.nx" % page: made.code.encode("utf-8")}
    if block is not None:
        files["fonts/%s%s" % (made.font_name, FONT_SUFFIX)] = block
        fonts = fonts + [made.font_name]
        check_names(fonts, "fonts")
    for relative in files:
        if (source_folder / relative).exists():
            raise NxwrightError("%s is already there, though app.toml does not list it"
                                % (source_folder / relative))
    for relative, content in files.items():
        (source_folder / relative).parent.mkdir(parents=True, exist_ok=True)
        (source_folder / relative).write_bytes(content)
    (source_folder / "app.toml").write_text(
        app_text(dict(app, pages=app["pages"] + [page], fonts=fonts)), encoding="utf-8",
        newline="\n")
    if not chinese:
        warning = _keyboard_font_warning(source_folder, made, block is not None, settings)
    return page, made.font_name, warning


def _keyboard_font_warning(source_folder: Path, made, drawn: bool, settings):
    """Returns the warning add_keyboard gives of the font of a keyboard drawn
    from Noto Sans, `made`, a keyboards.Keyboard, whose font it `drawn`, or
    which the folder holds; or None."""
    if drawn:
        encoding = settings.encoding
    else:
        font_path = source_folder / "fonts" / (made.font_name + FONT_SUFFIX)
        encoding = decode_font(read_bytes(font_path)).encoding
    if encoding != settings.encoding:
        return ("the keyboard's font, %s, is in %s, not in the folder's %s: a caller's text "
                "in characters beyond ascii shows garbled in the keyboard's field"
                % (made.font_name, encoding, settings.encoding))
    if drawn and encoding == UTF8:
        return ("the keyboard's font, %s, holds the characters U+%04X to U+%04X: a caller's "
                "text in another character shows the font's first character in its place, "
                "a pixel's gap" % (made.font_name, UTF8_CHARACTERS[0], UTF8_CHARACTERS[-1]))
    if drawn:
        return noto_sans_lacks("the keyboard's font, %s," % made.font_name, encoding,
                               "a caller's text")
    return None


def _chinese_keyboard(source_folder: Path, fonts: list, settings, typeface, font) -> tuple:
    """Returns (the Chinese keyboard, a keyboards.Keyboard; its font's block,
    or None for a font the folder holds; a warning or None) for a folder of
    `fonts`, with `settings`, its font given by exactly one of `typeface` and
    `font`:
      - `typeface`, a typeface file, is drawn in gb2312, at the largest
        height its labels fit (keyboards.chinese_font_height), named as
        add_font names a font it draws (drawn_font_name). The warning says
        which characters the typeface lacks (font_drawing.font_warning).
      - `font`, a font the folder holds, is used as it is. The warning says
        that it draws nothing for some of the keys' labels, when it does not.
    Raises NxwrightError for neither or both; for a typeface file with no
    Chinese character, or whose font's name the folder has; and for a font
    the folder lacks, one in another encoding than gb2312, one with no
    Chinese character, or one taller than the keys fit."""
    if typeface is not None and font is not None:
        raise NxwrightError("the Chinese keyboard takes --typeface or --font, not both")
    if typeface is None and font is None:
        raise NxwrightError("the Chinese keyboard needs a font with Chinese characters. Give a "
                            "typeface file with --typeface, or one of the folder's fonts with "
                            "--font")
    width, height = settings.page_size
    if font is not None:
        if font not in fonts:
            raise NxwrightError("the folder has no font %s" % font)
        held = _chinese_keyboard_font(source_folder, font, settings.page_size)
        lacking = [character for character in chinese_label_characters()
                   if not _font_draws(held, character)]
        warning = None if not lacking else (
            "the font %s has nothing to show for some of the keys' labels, such as %r. Those "
            "keys will look empty" % (font, lacking[0]))
        return keyboard(CHINESE_INPUT, width, height, (font, held.height)), None, warning
    typeface = Path(typeface)
    face = TrueTypeFont(read_bytes(typeface))
    if not _typeface_has_chinese(face):
        raise NxwrightError("the typeface file %s has no Chinese characters, so the keyboard "
                            "could not show any. Choose a Chinese typeface, such as SimSun or "
                            "Noto Sans CJK SC" % typeface)
    font_height = chinese_font_height(width, height, typeface_widths(face))
    name = drawn_font_name(face.typeface_name(), typeface, font_height)
    if name in fonts:
        raise NxwrightError("the folder has a font %s already: add the keyboard with that "
                            "font instead" % name)
    block = draw_font_block(name, face, font_height, _GB2312, settings.rotation)
    made = keyboard(CHINESE_INPUT, width, height, (name, font_height))
    return made, block, font_warning(face, _GB2312)


def _chinese_characters() -> list:
    """GB2312's Chinese characters: those of the rows from b0 to f7."""
    found = []
    for first in range(0xb0, 0xf8):
        for second in range(0xa1, 0xff):
            try:
                found.append(bytes([first, second]).decode(_GB2312))
            except UnicodeDecodeError:
                continue
    return found


def _typeface_has_chinese(typeface: TrueTypeFont) -> bool:
    """Whether a typeface file has a glyph for any of GB2312's Chinese
    characters."""
    return any(typeface.glyph_of(character) is not None for character in _chinese_characters())


def chinese_keyboard_fonts(source_folder: Path, app: dict) -> list:
    """Returns the fonts of a folder whose app.toml is `app` that its Chinese
    keyboard takes as they are (add_keyboard's `font`): in gb2312, with
    Chinese characters, and no taller than the keys fit. Returns [] for a
    folder without screen settings, or in another encoding."""
    settings = settings_from_keys(app)
    if settings is None or settings.encoding != _GB2312:
        return []
    taken = []
    for font in app["fonts"]:
        try:
            _chinese_keyboard_font(Path(source_folder), font, settings.page_size)
        except (NxwrightError, OSError):
            # A font the keyboard refuses, or whose file cannot be read.
            continue
        taken.append(font)
    return taken


def _chinese_keyboard_font(source_folder: Path, font: str, page_size: tuple):
    """Returns the folder's font `font` (zi_font.Font), read for the Chinese
    keyboard of a page of `page_size`. Raises NxwrightError for a font in
    another encoding than gb2312, one with no Chinese characters, or one
    taller than the keys fit."""
    held = decode_font(read_bytes(source_folder / "fonts" / (font + FONT_SUFFIX)))
    if held.encoding != _GB2312:
        raise NxwrightError("the font %s is in %s, not gb2312, so it cannot show Chinese "
                            "characters" % (font, held.encoding))
    if not _font_holds_chinese(held):
        raise NxwrightError("the font %s holds no Chinese characters, so the keyboard "
                            "could not show its candidates" % font)
    largest = chinese_font_height(*page_size, font_widths(held, _GB2312), capped=False)
    if held.height > largest:
        raise NxwrightError("the font %s is %d pixels tall, but the keys fit a font of "
                            "%d pixels at most" % (font, held.height, largest))
    return held


def _font_draws(font, character: str) -> bool:
    """Whether a gb2312 font (zi_font.Font) draws `character`: holds it, not
    empty."""
    code = text_codes(character.encode(_GB2312), _GB2312)[0]
    held = font.characters.get(code)
    return held is not None and any(held.coverages())


def _font_holds_chinese(font) -> bool:
    """Whether a gb2312 font (zi_font.Font) draws any of GB2312's Chinese
    characters, a character's first byte from b0, which the font keeps in its
    code's low byte: a font drawn from a typeface without them holds them
    empty."""
    return any(code > 0xff and code & 0xff >= 0xb0 and any(character.coverages())
               for code, character in font.characters.items())


def keyboard_page(read, pages: list, kind: str):
    """Returns the name of the page of `pages` that is the keyboard `kind`, a
    name of SYSTEM_PAGES, by its page file's system_page, the Editor's or
    nxwright's; or None. `read(path)` returns a file of the folder."""
    for name in pages:
        table = parsed_page_toml(read(page_toml_path(name)), name)
        if table.get("page", {}).get("system_page") == kind:
            return name
    return None
