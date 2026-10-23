"""Writing a whole project file from a dump, with no existing project.

The file is laid out the same for every screen model:
  0x000000   the directory and its checksum (container.py)
  0x080000   a copy of both (DIRECTORY_COPY_OFFSET)
  0x380000   four 0xff bytes
  0x6ffff8   the text "ver21234"
  0x700000   the blocks, back to back: Program.s, the pages, the pictures
             (each one's file, then its screen copy), the fonts, the
             animations (each one's GmovMaker file, then the screen's form),
             the videos, the sounds, and last the manifest
Every other byte before 0x700000 is zero. The manifest lists the pictures,
the fonts, the animations, the videos, the sounds, then the pages. Its header
comes from the device settings (device_settings.py), and its stamp from the
screen model's stamp number (screen_models.py). Screen copies are generated
in the format of the model's series, in the pixel order of the rotation, or
taken from the picture cache (picture_cache.py) when an earlier build made
them.
"""
from pathlib import Path

from nxwright import NxwrightError
from nxwright.project.container import (DIRECTORY_COPY_OFFSET, ENTRY_SIZE, DirectoryEntry,
                                        HmiContainer, encode_directory, name_field)
from nxwright.project.device_settings import DeviceSettings, encoding_code, manifest_header
from nxwright.project.dump_folder import (MACROS_BLOCK, MACROS_FILE, check_dump_format,
                                          check_ids_without_gaps, copied_contents, dump_pictures,
                                          page_text_files)
from nxwright.project.page_block import encode_page, parse_page
from nxwright.project.page_header import header_40
from nxwright.project.page_text import page_from_text
from nxwright.project.picture_cache import make_screen_copy, opened_cache
from nxwright.project.resources import (COPIED_KINDS, CopiedKind, ImageSource,
                                        encode_image_source, encode_manifest, parse_manifest)
from nxwright.project.stamp import with_model_manifest_stamp, with_stamp

BLOCKS_START = 0x700000
_MARKER = (0x380000, b"\xff\xff\xff\xff")
_VERSION = (0x6ffff8, b"ver21234")
# The directory flags the Editor gives Program.s; it gives other new blocks 0.
_PROGRAM_FLAGS = 0x200
_PROGRAM_BLOCK = "Program.s"
_MANIFEST_BLOCK = "main.HMI"


def write_new_project(dump_folder: Path, settings: DeviceSettings, output: Path):
    """Writes the project file `output` from the dump in `dump_folder` and the
    device settings `settings`.

    Raises NxwrightError when `output` exists, the dump is not one this
    version reads or has no program.s, its pages, pictures, fonts,
    animations, videos, or sounds are not numbered from 0 without gaps, an
    animation lacks one of its two files, or a picture cannot be stored on
    the screen model (such as a 1-by-1 picture on a compressed screen).
    """
    dump_folder, output = Path(dump_folder), Path(output)
    if output.exists():
        raise NxwrightError("%s already exists" % output)
    check_dump_format(dump_folder)
    if not (dump_folder / "program.s").is_file():
        raise NxwrightError("%s has no program.s" % dump_folder)
    pages = _page_blocks(dump_folder, settings)
    pictures = _picture_blocks(dump_folder, settings)
    copied = {kind: copied_contents(dump_folder, kind) for kind in COPIED_KINDS}
    # Each picture's blocks come in pairs, its file then its screen copy.
    # COPIED_KINDS runs in the Editor's order too.
    resources = ([("i", name) for name, _ in pictures[1::2]]
                 + [(kind.listed, "%d.%s" % (resource_id, kind.listed))
                    for kind in COPIED_KINDS for resource_id in range(len(copied[kind]))]
                 + [("pa", name) for name, _ in pages])
    manifest = with_model_manifest_stamp(encode_manifest(manifest_header(settings), resources),
                                         settings.model.stamp_number)
    # The macros, if any, follow the program. The Editor's new project has
    # none, so where it would put them is not known.
    macros = dump_folder / MACROS_FILE
    blocks = ([(_PROGRAM_BLOCK, (dump_folder / "program.s").read_bytes())]
              + ([(MACROS_BLOCK, macros.read_bytes())] if macros.is_file() else [])
              + pages + pictures
              + [block for kind in COPIED_KINDS for block in _copied_blocks(kind, copied[kind])]
              + [(_MANIFEST_BLOCK, manifest)])
    data = _container(blocks)
    _check_written(data, blocks, settings)
    # Exclusive create: fails instead of overwriting a file that appeared meanwhile.
    out = open(output, "xb")
    try:
        with out:
            out.write(data)
    except OSError as error:
        # The file is the one just created, so removing it loses nothing.
        output.unlink(missing_ok=True)
        raise NxwrightError("writing %s failed (%s)" % (output, error)) from None


def _page_blocks(dump_folder: Path, settings: DeviceSettings) -> list:
    """Returns [(block name, stamped page block)] for the dump's pages, in ID
    order, each carrying the encoding of `settings` (page_header.py)."""
    files = page_text_files(dump_folder)
    check_ids_without_gaps(files, "page")
    blocks = []
    for page_id in range(len(files)):
        page = page_from_text(files[page_id].read_text(encoding="utf-8"))
        # Only the start of the field carries the encoding. The rest, zero on
        # every page seen, is kept as the dump has it.
        page.unknown_40 = header_40(encoding_code(settings.encoding))[:4] + page.unknown_40[4:]
        blocks.append(("%d.pa" % page_id, with_stamp(encode_page(page))))
    return blocks


def _picture_blocks(dump_folder: Path, settings: DeviceSettings) -> list:
    """Returns [(block name, block)] for the dump's pictures in ID order: each
    one's file (".is"), then its screen copy (".i")."""
    files = dump_pictures(dump_folder)
    kind, rotation = settings.screen_copy_layout
    blocks = []
    if not files:
        return blocks
    with opened_cache() as cache:
        for picture_id, (file_name, data, suffix) in enumerate(files):
            try:
                made = make_screen_copy(data, kind, rotation, cache)
            except NxwrightError as error:
                # The dump's file is kept apart from the words too, so that a
                # build can name the source folder's file in its place. This
                # `file` is a dump's path, not a source folder's as
                # NxwrightError's docstring has it: no finding is placed by it
                # until project_files.build has turned it into the folder's.
                refusal = NxwrightError("%s: %s" % (file_name, error))
                refusal.file, refusal.reason = file_name, str(error)
                raise refusal from None
            blocks.append(("%d.is" % picture_id,
                           encode_image_source(ImageSource(made.width, made.height, data,
                                                           suffix))))
            blocks.append(("%d.i" % picture_id, made.block))
    return blocks


def _copied_blocks(kind: CopiedKind, contents: list) -> list:
    """Returns [(block name, bytes)] for fonts, animations, videos, or
    sounds (`kind`), from their files' `contents` in ID order (dump_folder.py,
    copied_contents), each one's blocks in the order of `kind.blocks`, named
    by its ID."""
    return [("%d.%s" % (resource_id, extension), content)
            for resource_id, files in enumerate(contents)
            for (extension, _), content in zip(kind.blocks, files)]


def _container(blocks: list) -> bytes:
    """Returns the project file holding `blocks`, [(name, bytes)], in that order."""
    entries, offset = [], BLOCKS_START
    for name, block in blocks:
        entries.append(DirectoryEntry(name_field(name), offset, len(block),
                                      _PROGRAM_FLAGS if name == _PROGRAM_BLOCK else 0))
        offset += len(block)
    directory = encode_directory(entries)
    if len(directory) > DIRECTORY_COPY_OFFSET:
        raise NxwrightError("the project has too many blocks: %d entries do not fit the "
                            "directory" % len(entries))
    data = bytearray(BLOCKS_START)
    data[0:len(directory)] = directory
    data[DIRECTORY_COPY_OFFSET:DIRECTORY_COPY_OFFSET + len(directory)] = directory
    for position, text in (_MARKER, _VERSION):
        data[position:position + len(text)] = text
    for _, block in blocks:
        data += block
    return bytes(data)


def _check_written(data: bytes, blocks: list, settings: DeviceSettings):
    """Reads the written file back, and stops unless it holds `blocks` under a
    valid directory, with a manifest stamped for the screen model of
    `settings`."""
    container = HmiContainer(data)
    if not container.directory_checksum_is_valid():
        raise NxwrightError("self-check failed: the written directory checksum is wrong")
    if container.entry_count * ENTRY_SIZE + 8 > DIRECTORY_COPY_OFFSET:
        raise NxwrightError("self-check failed: the directory overlaps its copy")
    if dict(blocks) != container.blocks:
        raise NxwrightError("self-check failed: the blocks read back differ")
    manifest = container.blocks[_MANIFEST_BLOCK]
    parse_manifest(manifest)
    if manifest != with_model_manifest_stamp(manifest, settings.model.stamp_number):
        raise NxwrightError("self-check failed: the manifest stamp is wrong")
    for name, block in blocks:
        if name.endswith(".pa"):
            parse_page(block)
