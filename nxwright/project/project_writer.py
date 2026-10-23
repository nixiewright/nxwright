"""Writing a project file (.HMI) from an existing project and an edited dump.

The writer copies the project and applies what changed in the dump:

  - pages: edited, added, removed, or reordered;
  - pictures, fonts, animations, videos, and sounds: added, removed, or
    reordered;
  - program.s: edited;
  - the macros, macros.s: added, edited, or removed.

Pages are matched to the project's page blocks by page name, pictures to its
pictures by the bytes of their files, and fonts, animations, videos, and sounds to
the project's by the bytes of their blocks. A replaced picture is a new
picture plus a removed one, and so for the others. The manifest is rebuilt
when the order or the set of any of them changed.

A new picture gets two blocks: its file, and a screen copy generated from it.
The dump's own screen copy files are output only and never read. Screen
copies are generated in the format and pixel order the project's own pictures
confirm (see screen_copy.py); a project whose pictures confirm none is refused.

Every block is written the way the Editor saves one, which keeps the file
usable by the Editor's later saves:

  - an old directory entry is marked stale: flags bit 0 set and the first
    byte of its name zeroed, since the Editor finds blocks by name;
  - a new or changed block is appended at the end of the file;
  - its entry is appended at the end of the directory.

The directory and its checksum are then written at offset 0 and at
DIRECTORY_COPY_OFFSET. Everything else in the file is left as it was.
Anything the writer does not handle stops it before anything is written.
"""
from dataclasses import dataclass, field
from pathlib import Path

from nxwright import NxwrightError
from nxwright.project.container import (DIRECTORY_COPY_OFFSET, ENTRY_SIZE, DirectoryEntry,
                                        HmiContainer, encode_directory, name_field, numbered_block)
from nxwright.project.device_settings import read_device_settings
from nxwright.project.dump_folder import (MACROS_BLOCK, MACROS_FILE, check_dump_format,
                                          check_ids_without_gaps, copied_contents, dump_pictures,
                                          page_text_files)
from nxwright.project.editor_limits import check_page_limits
from nxwright.project.page_block import encode_page, parse_page
from nxwright.project.page_text import page_from_text
from nxwright.project.picture_cache import make_screen_copy, opened_cache
from nxwright.project.pictures import read_picture
from nxwright.project.replacing import held_by_the_nextion_editor, is_project_file, written_beside
from nxwright.project.resources import (COPIED_KINDS, CopiedKind, ImageSource,
                                        check_manifest_matches_blocks, encode_image_source,
                                        encode_manifest, parse_image_source, parse_manifest,
                                        partner_name, with_kind_in_order)
from nxwright.project.screen_copy import (FORMAT_RAW, FORMAT_RAW_WITH_HEADER, ROTATIONS,
                                          UndecodedScreenCopyError, decode_screen_copy,
                                          matches_within_editor_rounding, screen_copy_format)
from nxwright.project.stamp import block_stamp, manifest_stamp, with_manifest_stamp, with_stamp

PROGRAM_BLOCK = "Program.s"
MANIFEST_BLOCK = "main.HMI"


@dataclass
class WritePlan:
    """The blocks to write and to retire, and what the dump expects the result
    to hold, worked out before anything is written."""
    blocks: dict = field(default_factory=dict)       # block name -> new block bytes
    removed: list = field(default_factory=list)      # block names to mark stale
    pages: list = field(default_factory=list)        # (block name, encoded page) in ID order
    # (".i" block name, (its file's bytes, its suffix)) in ID order.
    pictures: list = field(default_factory=list)
    new_screen_copies: dict = field(default_factory=dict)  # ".i" block name -> ScreenPixels
    # Screen copies taken from the picture cache: ".i" block name -> the block.
    # They have no pixels to decode back to, so the written block is compared.
    cached_screen_copies: dict = field(default_factory=dict)
    screen_copy_format: int = None      # of new screen copies, from the project's pictures
    screen_copy_rotation: int = None    # of new screen copies, from the project's pictures
    # Fonts, animations, videos, and sounds, by the extension of their listed
    # block: [(listed block name, the bytes of its blocks in the order of
    # CopiedKind.blocks)] in ID order.
    copied: dict = field(default_factory=dict)
    program: bytes = b""
    macros: bytes = None                # the macros' block, None when the dump has none
    manifest_reference: bytes = b""      # the project's manifest, stamped by the Editor
    changes: list = field(default_factory=list)      # readable lines for the report


class ProjectWriter:
    """Writes one output project from a project file and an edited dump."""

    def __init__(self, project_path: Path, dump_folder: Path, output: Path):
        self._project_path = Path(project_path)
        self._dump_folder = Path(dump_folder)
        self._output = Path(output)

    def write(self) -> list:
        """Writes the output project and returns readable lines describing the
        changes. Writes nothing and returns an empty list when nothing changed.

        An existing project file at the output is replaced, but only once
        the new one is written in full and has passed its self-check
        (replacing.written_beside). So a write that fails leaves it as it
        was. The output may be the project itself, which is read in full
        first.

        Raises NxwrightError when the output exists and is not a project
        file, the project or dump is not in a state the writer handles, or
        the written file fails its self-check.
        """
        # Replacing only a project file guards against a mistyped output,
        # such as a file of the dump.
        if self._output.exists() and not is_project_file(self._output):
            raise NxwrightError("%s exists and is not a project file; the writer replaces only "
                                "a project file" % self._output)
        container = HmiContainer.from_file(self._project_path)
        _check_project(container)
        manifest = parse_manifest(container.blocks[MANIFEST_BLOCK])
        check_manifest_matches_blocks(manifest, container.blocks)
        check_dump_format(self._dump_folder)
        plan = _plan(container, manifest, self._dump_folder)
        if not plan.blocks and not plan.removed:
            return []
        data = _apply(container, plan)
        _check_written(data, plan)
        with held_by_the_nextion_editor(self._output), \
                written_beside(self._output) as written:
            try:
                written.write_bytes(data)
            except OSError as error:
                raise NxwrightError("writing %s failed (%s)" % (self._output, error)) from None
        return plan.changes


def _check_project(container: HmiContainer):
    """Stops unless the project's directory is one the writer can append to."""
    if not container.directory_checksum_is_valid():
        raise NxwrightError("the project's directory checksum is wrong")
    # The directory and its copy each have a fixed area; the file must hold both.
    if container.file_size < 2 * DIRECTORY_COPY_OFFSET:
        raise NxwrightError("the project file is too small to hold the directory and its copy")
    offsets = [entry.offset for entry in container.entries]
    if offsets != sorted(offsets):
        raise NxwrightError("the project's directory is not in offset order")
    last = container.entries[-1] if container.entries else None
    if last is None or last.offset + last.size != container.file_size:
        raise NxwrightError("the project's last directory entry does not end at the end "
                            "of the file")
    for name in (MANIFEST_BLOCK, PROGRAM_BLOCK):
        if name not in container.blocks:
            raise NxwrightError("project has no %s block" % name)


def _plan(container: HmiContainer, manifest, dump_folder: Path) -> WritePlan:
    """Works out every block to write or retire from the dump's differences."""
    plan = WritePlan(manifest_reference=container.blocks[MANIFEST_BLOCK])
    _plan_pages(plan, container, manifest, dump_folder)
    _plan_pictures(plan, container, manifest, dump_folder)
    for kind in COPIED_KINDS:
        _plan_copied(plan, container, manifest, dump_folder, kind)
    _plan_program(plan, container, dump_folder)
    _plan_macros(plan, container, dump_folder)
    _plan_manifest(plan, container, manifest)
    return plan


def _plan_pages(plan: WritePlan, container: HmiContainer, manifest, dump_folder: Path):
    """Matches the dump's pages to the project's page blocks by page name."""
    files = page_text_files(dump_folder)
    check_ids_without_gaps(files, "page")
    project_blocks = {parse_page(container.blocks[name]).name: name
                      for name in manifest.block_names("pa")}
    next_number = _next_block_number(container, "pa")
    seen = set()
    for page_id in range(len(files)):
        page = page_from_text(files[page_id].read_text(encoding="utf-8"))
        check_page_limits(page, str(files[page_id].relative_to(dump_folder)))
        encoded = encode_page(page)
        page_name = parse_page(encoded).name
        if page_name in seen:
            raise NxwrightError("two page files are named %s" % page_name)
        seen.add(page_name)
        block_name = project_blocks.get(page_name)
        if block_name is None:
            block_name = "%d.pa" % next_number
            next_number += 1
            plan.blocks[block_name] = with_stamp(encoded)
            plan.changes.append("Added page %d (%s) as block %s" % (page_id, page_name, block_name))
        elif encoded[4:] != container.blocks[block_name][4:]:
            plan.blocks[block_name] = with_stamp(encoded)
            plan.changes.append("Replaced page %d (%s, block %s)" % (page_id, page_name, block_name))
        plan.pages.append((block_name, encoded))
    for page_name, block_name in project_blocks.items():
        if page_name not in seen:
            plan.removed.append(block_name)
            plan.changes.append("Removed page %s (block %s)" % (page_name, block_name))


def _plan_pictures(plan: WritePlan, container: HmiContainer, manifest, dump_folder: Path):
    """Matches the dump's picture files to the project's pictures by their
    bytes and their suffixes, which the pictures' records hold. Identical
    project pictures are matched in ID order."""
    files = dump_pictures(dump_folder)
    unmatched = {}                                   # (bytes, suffix) -> block names in ID order
    for name in manifest.block_names("i"):
        source = parse_image_source(container.blocks[name + "s"])
        unmatched.setdefault((source.data, source.suffix), []).append(name)
    # A picture's two blocks share their number.
    next_number = max(_next_block_number(container, "i"), _next_block_number(container, "is"))
    added = []
    for picture_id, (file_name, data, suffix) in enumerate(files):
        if unmatched.get((data, suffix)):
            block_name = unmatched[(data, suffix)].pop(0)
        else:
            block_name = "%d.i" % next_number
            next_number += 1
            added.append((picture_id, file_name, block_name, data, suffix))
        plan.pictures.append((block_name, (data, suffix)))
    for block_name in sorted((name for names in unmatched.values() for name in names),
                             key=lambda name: numbered_block(name, "i")):
        plan.removed += [block_name, block_name + "s"]
        plan.changes.append("Removed picture block %s" % block_name)
    if added:
        plan.screen_copy_format, plan.screen_copy_rotation = _screen_copy_layout(container,
                                                                                 manifest)
        with opened_cache() as cache:
            for picture_id, file_name, block_name, data, suffix in added:
                _plan_new_picture(plan, picture_id, file_name, block_name, data, suffix, cache)


def _plan_new_picture(plan: WritePlan, picture_id: int, file_name: str, block_name: str,
                      data: bytes, suffix: str, cache):
    """Adds the file's block and the screen copy of one new picture, its
    file `data` from the dump's `file_name`, of `suffix`, the screen copy
    made now or taken from `cache` (picture_cache.py, or None)."""
    try:
        made = make_screen_copy(data, plan.screen_copy_format, plan.screen_copy_rotation, cache)
    except NxwrightError as error:
        raise NxwrightError("%s: %s" % (file_name, error)) from None
    plan.blocks[block_name + "s"] = encode_image_source(ImageSource(made.width, made.height, data,
                                                                    suffix))
    plan.blocks[block_name] = made.block
    if made.pixels is None:
        plan.cached_screen_copies[block_name] = made.block
    else:
        plan.new_screen_copies[block_name] = made.pixels
    plan.changes.append("Added picture %d as block %s" % (picture_id, block_name))


def _screen_copy_layout(container: HmiContainer, manifest) -> tuple:
    """Returns (format, rotation) for new screen copies, as the project's own
    pictures confirm them.

    The format is the one every picture uses. A raw 1-by-1 picture in a project
    of another format does not count, since the Editor stores those raw.

    The rotation is confirmed by decoding pictures under each rotation and
    comparing them with their files. A picture that matches under more than one
    rotation confirms nothing, so the next one is tried. The project's rotation
    setting is not used then: "Save As" can leave it stale. A project with no
    picture that counts takes both from its settings, as a build does
    (_settings_layout): no picture can disagree with them.

    Format 3 ignores the rotation. One of its uncompressed pictures confirms the
    format. Its compressed ones are not decoded, so they confirm nothing.
    """
    names = manifest.block_names("i")
    if not names:
        return _settings_layout(container)
    pictures = []
    for name in names:
        try:
            pictures.append((name, screen_copy_format(container.blocks[name]),
                             parse_image_source(container.blocks[name + "s"])))
        except NxwrightError as error:
            raise NxwrightError("picture block %s: %s" % (name, error)) from None
    formats = sorted({kind for _, kind, source in pictures
                      if not (kind == FORMAT_RAW and source.width * source.height == 1)})
    if not formats:
        # Its only pictures are 1-by-1 raw ones, which confirm nothing.
        return _settings_layout(container)
    if len(formats) != 1:
        raise NxwrightError("new pictures need a project whose pictures share one screen copy "
                            "format; this one has formats %s" % formats)
    for name, kind, source in pictures:
        block = container.blocks[name]
        # Only format 3 has a variant that is not decoded.
        if kind != formats[0] or kind == FORMAT_RAW_WITH_HEADER and _is_undecoded(block):
            continue
        try:
            image = read_picture(source.data)
        except NxwrightError as error:
            raise NxwrightError("picture block %s: %s" % (name, error)) from None
        rotations = (0,) if kind == FORMAT_RAW_WITH_HEADER else ROTATIONS
        matching = [rotation for rotation in rotations if _decodes_to(block, image, kind, rotation)]
        if len(matching) == 1:
            return kind, matching[0]
        if not matching:
            raise NxwrightError("picture block %s does not match its picture in any screen rotation"
                                % name)
    if formats[0] == FORMAT_RAW_WITH_HEADER:
        raise NxwrightError("the project's format 3 pictures are all compressed, which is not "
                            "decoded, so none confirms the format of new ones")
    raise NxwrightError("every picture in the project looks the same in more than one screen "
                        "rotation, so none confirms the pixel order of new ones")


def _settings_layout(container: HmiContainer) -> tuple:
    """Returns (format, rotation) for new screen copies from the project's
    screen model and rotation (DeviceSettings.screen_copy_layout), for a
    project whose pictures confirm neither. Raises NxwrightError for a model
    nxwright does not know, whose format it cannot tell."""
    header = container.blocks[MANIFEST_BLOCK]
    settings = read_device_settings(header)
    if settings is None:
        raise NxwrightError("the project's screen model, device ID %s, is not one nxwright knows, "
                            "and no picture of the project confirms the screen copy format and "
                            "pixel order of new ones; add one in the Nextion Editor first"
                            % header[16:20].hex())
    return settings.screen_copy_layout


def _is_undecoded(block: bytes) -> bool:
    """Returns whether `block` is a screen copy that screen_copy.py recognises
    but cannot decode: a compressed format 3 picture."""
    try:
        decode_screen_copy(block, 0)
    except UndecodedScreenCopyError:
        return True
    except NxwrightError:
        pass
    return False


def _decodes_to(block: bytes, image, kind: int, rotation: int) -> bool:
    """Returns whether `block` decodes, in the pixel order of `rotation`, to
    `image`, within the Editor's rounding."""
    try:
        return matches_within_editor_rounding(decode_screen_copy(block, rotation), image, kind)
    except NxwrightError:
        # A compressed screen copy's second header fits only two of the rotations.
        return False


def _plan_copied(plan: WritePlan, container: HmiContainer, manifest, dump_folder: Path,
                 kind: CopiedKind):
    """Matches the dump's fonts, animations, videos, or sounds (`kind`) to
    the project's by the bytes of their blocks. Byte-identical ones are
    matched in ID order."""
    unmatched = [(name, _copied_blocks(container, kind, name))
                 for name in manifest.block_names(kind.listed)]
    # The blocks of one share their number.
    next_number = max(_next_block_number(container, extension) for extension, _ in kind.blocks)
    plan.copied[kind.listed] = []
    for resource_id, contents in enumerate(copied_contents(dump_folder, kind)):
        match = next((entry for entry in unmatched if entry[1] == contents), None)
        if match is None:
            block_name = "%d.%s" % (next_number, kind.listed)
            next_number += 1
            for (extension, _), content in zip(kind.blocks, contents):
                plan.blocks[partner_name(block_name, extension)] = content
            plan.changes.append("Added %s %d as block %s" % (kind.noun, resource_id, block_name))
        else:
            unmatched.remove(match)
            block_name = match[0]
        plan.copied[kind.listed].append((block_name, contents))
    for block_name, _ in unmatched:
        plan.removed += [partner_name(block_name, extension) for extension, _ in kind.blocks]
        plan.changes.append("Removed %s block %s" % (kind.noun, block_name))


def _copied_blocks(container: HmiContainer, kind: CopiedKind, block_name: str) -> tuple:
    """Returns the bytes of the blocks of the font, animation, video, or
    sound (`kind`) whose listed block is `block_name`, in the order of
    `kind.blocks`."""
    return tuple(container.blocks[partner_name(block_name, extension)]
                 for extension, _ in kind.blocks)


def _plan_program(plan: WritePlan, container: HmiContainer, dump_folder: Path):
    plan.program = (dump_folder / "program.s").read_bytes()
    if plan.program != container.blocks[PROGRAM_BLOCK]:
        plan.blocks[PROGRAM_BLOCK] = plan.program
        plan.changes.append("Replaced program.s")


def _plan_macros(plan: WritePlan, container: HmiContainer, dump_folder: Path):
    """Plans the macros' block as the dump's macros.s holds it. A dump
    without one has no macros: the project's block, if any, is removed."""
    path = dump_folder / MACROS_FILE
    plan.macros = path.read_bytes() if path.is_file() else None
    old = container.blocks.get(MACROS_BLOCK)
    if plan.macros is None and old is not None:
        plan.removed.append(MACROS_BLOCK)
        plan.changes.append("Removed the macros")
    elif plan.macros is not None and plan.macros != old:
        plan.blocks[MACROS_BLOCK] = plan.macros
        plan.changes.append("Added the macros" if old is None else "Replaced the macros")


def _plan_manifest(plan: WritePlan, container: HmiContainer, manifest):
    """Rebuilds the manifest when the order or set of any listed kind changed."""
    resources = with_kind_in_order(manifest.resources, "pa", [name for name, _ in plan.pages])
    resources = with_kind_in_order(resources, "i", [name for name, _ in plan.pictures])
    for extension, entries in plan.copied.items():
        resources = with_kind_in_order(resources, extension, [name for name, _ in entries])
    if resources != manifest.resources:
        original = container.blocks[MANIFEST_BLOCK]
        # The project's own manifest, stamped by the Editor, is the stamp's reference.
        plan.blocks[MANIFEST_BLOCK] = with_manifest_stamp(encode_manifest(original, resources),
                                                          original)
        plan.changes.append("Rewrote the manifest (%d resources)" % len(resources))


def _next_block_number(container: HmiContainer, extension: str) -> int:
    """Returns one more than the highest number used by a live block of
    `extension`, so new blocks never reuse a live name."""
    numbers = [numbered_block(name, extension) for name in container.blocks]
    return max([number for number in numbers if number is not None], default=-1) + 1


def _apply(container: HmiContainer, plan: WritePlan) -> bytes:
    """Returns the project bytes with the plan's blocks appended, its retired
    blocks marked stale, and the directory updated."""
    data = bytearray(container.data)
    entries = [DirectoryEntry(entry.name_field, entry.offset, entry.size, entry.flags)
               for entry in container.entries]
    live = {entry.name: entry for entry in entries if not entry.stale}
    for block_name, block in plan.blocks.items():
        old = live.get(block_name)
        entries.append(DirectoryEntry(name_field(block_name), len(data), len(block),
                                      old.flags if old else 0))
        if old:
            old.mark_stale()
        data += block
    for block_name in plan.removed:
        live[block_name].mark_stale()
    directory = encode_directory(entries)
    # The directory must end before its copy starts.
    if len(directory) > DIRECTORY_COPY_OFFSET:
        raise NxwrightError("the directory would no longer fit below its copy")
    # The space after the directory is not necessarily empty: when the Editor
    # shortens the directory it leaves the old entries behind. Only the entry
    # count marks the end, so that space is free to overwrite.
    for start in (0, DIRECTORY_COPY_OFFSET):
        data[start:start + len(directory)] = directory
    return bytes(data)


def _check_written(data: bytes, plan: WritePlan):
    """Reads the written bytes back and checks the directory, every stamp, and
    that the pages, pictures, fonts, animations, videos, sounds, and program
    are the ones the dump asked for, with each new screen copy decoding back
    to its picture, or, taken from the picture cache, equal to the cached
    one."""
    container = HmiContainer(data)
    if not container.directory_checksum_is_valid():
        raise NxwrightError("self-check failed: the written directory checksum is wrong")
    length = 4 + container.entry_count * ENTRY_SIZE + 4
    if data[DIRECTORY_COPY_OFFSET:DIRECTORY_COPY_OFFSET + length] != data[:length]:
        raise NxwrightError("self-check failed: the directory copy differs")
    manifest_block = container.blocks[MANIFEST_BLOCK]
    if (manifest_stamp(manifest_block, plan.manifest_reference)
            != int.from_bytes(manifest_block[:4], "little")):
        raise NxwrightError("self-check failed: the manifest stamp is wrong")
    manifest = parse_manifest(manifest_block)
    check_manifest_matches_blocks(manifest, container.blocks)
    if manifest.block_names("pa") != [name for name, _ in plan.pages]:
        raise NxwrightError("self-check failed: the page order differs from the dump")
    for page_id, (block_name, encoded) in enumerate(plan.pages):
        block = container.blocks[block_name]
        if block_stamp(block) != int.from_bytes(block[:4], "little") or block[4:] != encoded[4:]:
            raise NxwrightError("self-check failed: page %d does not match the dump" % page_id)
    sources = [(name, parse_image_source(container.blocks[name + "s"]))
               for name in manifest.block_names("i")]
    pictures = [(name, (source.data, source.suffix)) for name, source in sources]
    if pictures != plan.pictures:
        raise NxwrightError("self-check failed: the pictures differ from the dump")
    for block_name, pixels in plan.new_screen_copies.items():
        if decode_screen_copy(container.blocks[block_name], plan.screen_copy_rotation) != pixels:
            raise NxwrightError("self-check failed: the screen copy %s does not decode back to "
                                "its picture" % block_name)
    for block_name, block in plan.cached_screen_copies.items():
        if container.blocks[block_name] != block:
            raise NxwrightError("self-check failed: the screen copy %s differs from the one in "
                                "the picture cache" % block_name)
    for kind in COPIED_KINDS:
        found = [_copied_blocks(container, kind, name)
                 for name in manifest.block_names(kind.listed)]
        if found != [contents for _, contents in plan.copied[kind.listed]]:
            raise NxwrightError("self-check failed: the %ss differ from the dump" % kind.noun)
    if container.blocks[PROGRAM_BLOCK] != plan.program:
        raise NxwrightError("self-check failed: program.s differs from the dump")
    if container.blocks.get(MACROS_BLOCK) != plan.macros:
        raise NxwrightError("self-check failed: the macros differ from the dump")
