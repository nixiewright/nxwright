"""Page files (".page"): one page as the Nextion Editor exports and imports it.

A page file is a page block plus the fonts the page uses:
  - The fonts follow the objects. Their object table entries hold 1 in the
    third field, where objects hold 0 (see page_block.py).
  - They appear in order of first use, scanning the objects' records in order.
  - Each "font" attribute is renumbered to its font's position in that list.
  - Pictures are not embedded; picture attributes keep their project IDs.
  - Header bytes 40 to 55 hold the form the Editor writes into every page
    it writes, with the project's encoding (page_header.py), whatever form
    the page had.
  - The block is stamped like a page block (see stamp.py).
"""
from pathlib import Path
import copy

from nxwright import NxwrightError
from nxwright.project.device_settings import DEFAULT_ENCODING, encoding_code
from nxwright.project.dump_folder import (check_dump_format, dump_device_settings,
                                         numbered_files, page_text_files)
from nxwright.project.page_block import Attribute, PageBlock, encode_page
from nxwright.project.page_header import header_40
from nxwright.project.page_text import page_from_text
from nxwright.project.replacing import is_page_file, written_beside
from nxwright.project.stamp import with_stamp


def build_page_file(page: PageBlock, fonts: dict, encoding: str) -> bytes:
    """Returns the page file for `page`, of a project in the encoding
    `encoding`, a name of ENCODINGS.

    `fonts` maps project font IDs to font blocks. Raises NxwrightError when
    the page uses a font missing from `fonts`.
    """
    page = copy.deepcopy(page)
    used = []
    for font_attribute in _font_attributes(page):
        font_id = font_attribute.value[0]
        if font_id not in fonts:
            raise NxwrightError("page %s uses font %d, which the dump does not have"
                                % (page.name, font_id))
        if font_id not in used:
            used.append(font_id)
        font_attribute.value = bytes([used.index(font_id)])
    page.unknown_40 = header_40(encoding_code(encoding))
    page.stamp = 0
    return with_stamp(encode_page(page, embedded=tuple(fonts[font_id] for font_id in used)))


def _font_attributes(page: PageBlock) -> list:
    """Returns the page's "font" attributes, in stored order. Raises
    NxwrightError when one is not a single byte."""
    found = []
    for page_object in page.objects:
        for item in page_object.items:
            if isinstance(item, Attribute) and item.name == "font":
                if len(item.value) != 1:
                    raise NxwrightError("page %s has a font attribute of %d bytes"
                                        % (page.name, len(item.value)))
                found.append(item)
    return found


def write_page_file(dump_folder: Path, page_id: int, output: Path):
    """Writes the page file for page `page_id` of `dump_folder` to `output`.

    An existing page file at `output` is replaced, but only once the new one
    is written in full (replacing.written_beside). So a write that fails
    leaves it as it was.

    Raises NxwrightError when the output exists and is not a page file, the
    folder is not a dump in the current format, its device settings are not
    ones a project can hold, the page's text does not parse, or the page or
    a font it uses is missing from the dump.
    """
    # Replacing only a page file guards against a mistyped output, such as a
    # file of the dump.
    if output.exists() and not is_page_file(output):
        raise NxwrightError("%s exists and is not a page file; nxwright page replaces only a "
                            "page file" % output)
    check_dump_format(dump_folder)
    pages = page_text_files(dump_folder)
    if page_id not in pages:
        raise NxwrightError("no page file for page %d in %s" % (page_id, dump_folder / "pages"))
    page = page_from_text(pages[page_id].read_text(encoding="utf-8"))
    fonts = {font_id: path.read_bytes()
             for font_id, path in numbered_files(dump_folder / "fonts", ".zi").items()}
    # A dump of a screen model nxwright does not know shows no settings.
    # Its encoding is then taken to be the Editor's default, as extracting does.
    settings = dump_device_settings(dump_folder)
    encoding = settings.encoding if settings is not None else DEFAULT_ENCODING
    page_file = build_page_file(page, fonts, encoding)
    with written_beside(output) as written:
        try:
            written.write_bytes(page_file)
        except OSError as error:
            raise NxwrightError("writing %s failed (%s)" % (output, error)) from None
