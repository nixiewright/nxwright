"""Writing a Nextion Editor project (.HMI) out as a dump folder of text and asset files.

The project file is only read. The output folder must not exist yet, or be
empty. Nothing is ever deleted; clearing an old dump is left to the user. The
folder layout and the page text format are described in docs/dumps.md.
"""
from pathlib import Path
import hashlib
import re

from nxwright import NxwrightError
from nxwright.project.container import HmiContainer, numbered_block
from nxwright.project.dump_folder import (DUMP_FORMAT_LINE, MACROS_BLOCK, MACROS_FILE,
                                          copied_file_name)
from nxwright.project.page_block import encode_page, parse_page
from nxwright.project.page_text import page_from_text, page_to_text
from nxwright.project.resources import (FONTS, MEDIA, CopiedKind, check_manifest_matches_blocks,
                                        parse_image_source, parse_manifest, partner_name)
from nxwright.project.zi_font import parse_font_header

# The block kinds this tool handles: the manifest and the program, which
# every project has, the macros, which a project may have, and numbered
# pages (pa), pictures' files (is), screen copies (i), fonts (zi), animations
# (gmovs and gmov), videos (v), and sounds (wav).
_KNOWN_SINGLE_BLOCKS = ("main.HMI", "Program.s")
_KNOWN_EXTENSIONS = ("pa", "is", "i", "zi", "gmovs", "gmov", "v", "wav")
_SAFE_FILE_NAME = re.compile(r"[A-Za-z0-9_]+")


class ProjectDumper:
    """Writes one project's dump folder."""

    def __init__(self, project_path: Path, output: Path):
        self._project_path = Path(project_path)
        self._output = Path(output)
        self._container = None
        self._manifest = None

    def dump(self):
        """Writes the whole dump.

        Raises NxwrightError when the project holds something not understood,
        when a page's text form does not encode back to its block, or when the
        output folder is not empty.
        """
        if self._output.exists() and any(self._output.iterdir()):
            raise NxwrightError("output folder %s is not empty" % self._output)
        self._container = HmiContainer.from_file(self._project_path)
        self._check_block_kinds()
        self._manifest = parse_manifest(self._container.blocks["main.HMI"])
        check_manifest_matches_blocks(self._manifest, self._container.blocks)
        self._output.mkdir(parents=True, exist_ok=True)
        try:
            self._write_project_summary()
            (self._output / "program.s").write_bytes(self._container.blocks["Program.s"])
            if MACROS_BLOCK in self._container.blocks:
                (self._output / MACROS_FILE).write_bytes(self._container.blocks[MACROS_BLOCK])
            self._write_pages()
            self._write_images()
            self._write_fonts()
            for kind in MEDIA:
                self._write_copied(kind)
        except NxwrightError as error:
            raise NxwrightError("%s (the partly written dump is in %s)"
                                % (error, self._output)) from None

    def _check_block_kinds(self):
        """Stops on a block kind this tool would otherwise silently leave out."""
        for name in _KNOWN_SINGLE_BLOCKS:
            if name not in self._container.blocks:
                raise NxwrightError("project has no %s block" % name)
        for name in self._container.blocks:
            known = name in _KNOWN_SINGLE_BLOCKS or name == MACROS_BLOCK or any(
                numbered_block(name, extension) is not None for extension in _KNOWN_EXTENSIONS)
            if not known:
                raise NxwrightError("block %s is of a kind this tool does not handle" % name)

    def _write_project_summary(self):
        """Writes project.txt: the dump format line, block counts, and the manifest."""
        container = self._container
        manifest = self._manifest
        lines = [
            DUMP_FORMAT_LINE,
            "file               %s" % self._project_path.name,
            "size               %d bytes" % container.file_size,
            "directory entries  %d" % container.entry_count,
            "live blocks        %d" % len(container.blocks),
            "stale entries      %d" % container.stale_count,
            "pages              %d" % len(container.blocks_with_extension("pa")),
            "images             %d" % len(container.blocks_with_extension("is")),
            "fonts              %d" % len(container.blocks_with_extension("zi")),
            "animations         %d" % len(container.blocks_with_extension("gmov")),
            "videos             %d" % len(container.blocks_with_extension("v")),
            "sounds             %d" % len(container.blocks_with_extension("wav")),
            "",
            "manifest",
            "  header_size      %d" % manifest.header_size,
            "  table_offset     %d" % manifest.table_offset,
            "  unknown_header   %s" % manifest.unknown_header.hex(),
            "  resources        %d" % len(manifest.resources),
        ]
        lines.extend("    %-4s %s" % resource for resource in manifest.resources)
        _write_text(self._output / "project.txt", lines)

    def _write_pages(self):
        folder = self._output / "pages"
        folder.mkdir()
        for page_id, block_name in enumerate(self._manifest.block_names("pa")):
            block = self._container.blocks[block_name]
            page = parse_page(block)
            # The page name becomes part of a file name, so it must not hold path characters.
            if not _SAFE_FILE_NAME.fullmatch(page.name):
                raise NxwrightError("page %d name %r cannot be used in a file name"
                                    % (page_id, page.name))
            text = page_to_text(page)
            _check_page_text(text, block, block_name)
            (folder / ("%02d-%s.txt" % (page_id, page.name))).write_text(
                text, encoding="utf-8", newline="\n")

    def _write_images(self):
        folder = self._output / "images"
        folder.mkdir()
        index = ["image  block  size       screen copy sha256"]
        for picture_id, block_name in enumerate(self._manifest.block_names("i")):
            screen_copy = self._container.blocks[block_name]
            # The file the Editor shows lives in the ".is" block of the same
            # number, which names its suffix.
            source = parse_image_source(self._container.blocks[block_name + "s"])
            (folder / ("%04d%s" % (picture_id, source.suffix))).write_bytes(source.data)
            (folder / ("%04d.i" % picture_id)).write_bytes(screen_copy)
            index.append("%04d   %-6s %-9s  %s" % (
                picture_id, block_name[:-2], "%dx%d" % (source.width, source.height),
                hashlib.sha256(screen_copy).hexdigest()))
        _write_text(folder / "index.txt", index)

    def _write_fonts(self):
        folder = self._output / "fonts"
        folder.mkdir()
        index = ["font  block  bytes   height  characters"]
        for font_id, block_name in enumerate(self._manifest.block_names("zi")):
            block = self._container.blocks[block_name]
            (folder / copied_file_name(font_id, FONTS.suffixes[0])).write_bytes(block)
            header = parse_font_header(block)
            index.append("%02d    %-6s %-6d  %-6d  0x%02x-0x%02x (%d)" % (
                font_id, block_name[:-3], len(block), header.height, header.first_character,
                header.last_character, header.character_count))
        _write_text(folder / "index.txt", index)

    def _write_copied(self, kind: CopiedKind):
        """Writes each animation, video, or sound (`kind`) as a file per
        block, bytes unchanged, with an index of their blocks."""
        folder = self._output / kind.folder
        folder.mkdir()
        index = ["%-9s  block      bytes" % kind.noun]
        for resource_id, listed in enumerate(self._manifest.block_names(kind.listed)):
            for extension, suffix in kind.blocks:
                block_name = partner_name(listed, extension)
                block = self._container.blocks[block_name]
                (folder / copied_file_name(resource_id, suffix)).write_bytes(block)
                index.append("%-9s  %-9s  %d" % ("%02d" % resource_id, block_name, len(block)))
        _write_text(folder / "index.txt", index)


def _check_page_text(text: str, block: bytes, block_name: str):
    """Proves the text is lossless: parses it back, encodes it, and compares it
    with the original block. The stamp (bytes 0 to 3) is not compared, because
    the text does not hold it."""
    rebuilt = encode_page(page_from_text(text))
    if rebuilt[4:] != block[4:]:
        first = next((i for i in range(4, min(len(rebuilt), len(block)))
                      if rebuilt[i] != block[i]), min(len(rebuilt), len(block)))
        raise NxwrightError("page %s does not survive its text form; first difference "
                            "at byte %d" % (block_name, first))


def _write_text(path: Path, lines: list):
    # Fixed encoding: manifest names can hold non-ASCII bytes, and the locale
    # default would differ between machines or fail to encode them.
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

