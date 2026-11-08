"""Writes a TFT file back as a source folder, in strict Nextion syntax, as
nxwright's library writes one (docs/source-folder.md):

- app.toml, with the pages, the resources, and the device settings the
  file keeps;
- defaults.toml, nxwright's component defaults;
- program.nx, its int variables' declaration, then its code;
- macros.nx, when the file has macros;
- each page's two files (page_files.py);
- each picture as a PNG file, and each font as its .zi file;
- on P and E, each animation as its two files, each video as its .video
  file, and each sound as its .wav file.

A picture's file is made from its screen copy, the form the file keeps
(nxwright's screen_copy.py). The build makes a screen copy from a picture
file by rounding each pixel's colour and alpha, so the PNG gives each pixel
a colour and an alpha that round back to the stored ones. A stored pixel
that no colour rounds to cannot come back, and is refused.

An animation's screen form is the block the file keeps, and the folder
keeps it as it is. The file does not keep GmovMaker's file of it, which a
source folder keeps beside it, and which the build copies into the project
without reading. So the folder writer makes GmovMaker's file again from the
frames the screen form shows, each turned upright, cut to the animation's
size, and lasting as long.

A name that no guess matched keeps its readable name (decoded_file.py).
decompiled_folder returns those names, each with what it names.
"""
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from PIL import Image

from nxwright import NxwrightError
from nxwright.language.resource_names import ResourceNames, check_names, font_header_name
from nxwright.project.component_defaults import DEFAULTS_FILE
from nxwright.project.device_settings import DeviceSettings, TextCodec
from nxwright.project.media_files import animation_files, animation_frames
from nxwright.project.pictures import read_picture, write_png
from nxwright.project.resources import ANIMATIONS, FONTS, SOUNDS, VIDEOS
from nxwright.project.screen_copy import decode_screen_copy, screen_copy_format, stored_pixels
from nxwright.project.screen_models import model_named
from nxwright.source.device_keys import device_keys
from nxwright.source.macros_source import MACROS_PATH, macros_to_source
from nxwright.source.page_source import page_nx_path, page_toml_path
from nxwright.source.source_folder import NEXTION, SOURCE_FORMAT, app_text

from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.code import decoded_lines
from nxwright.tft.decompiling.decoded_file import (ANIMATION_ROW, FONT_ROW, PICTURE_ROW, SOUND_ROW,
                                            VIDEO_ROW, DecodedFile, read_decoded)
from nxwright.tft.decompiling.page_files import page_files
from nxwright.tft.decompiling.resources import (media_blocks, picture_blocks, sound_blocks,
                                         stored_font_blocks)
from nxwright.tft.tft_file import TftFile, read_tft

# The names nxwright's extract gives a resource of each kind whose files
# hold none, from its ID.
_PICTURE_NAME, _FONT_NAME = "picture-%04d", "font-%02d"
_MEDIA_NAMES = {"animation": "animation-%02d", "video": "video-%02d", "sound": "sound-%02d"}
# How a screen form's frame, turned for the screen as nxwright's
# media_files._turned turns it, is turned upright again.
_UPRIGHT = {90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180,
            270: Image.Transpose.ROTATE_270}
# program.nx of a program.s of no lines. The build writes an empty
# program.nx as a new project's program.s, with lines of its own, and a
# comment alone as no lines.
_NO_LINES = "// Nothing runs at power-on.\n"
# The bits an RGB565 colour keeps of red, green, and blue: (shift, mask).
_CHANNELS = ((11, 0x1F), (5, 0x3F), (0, 0x1F))


class WrittenFolder(NamedTuple):
    """What the decompiler wrote a source folder from: `names`, each name no
    guess matched, as unmatched_names gives them; and `decoded`, the decoded
    file of the TFT file."""
    names: list
    decoded: DecodedFile


def decompiled_folder(tft_bytes: bytes, folder: Path) -> list:
    """Writes the source folder of the TFT file `tft_bytes` into `folder`,
    which must not exist or be an empty folder. Returns each name no guess
    matched, as (what it names, its decoded_file.Name), as unmatched_names
    gives them. Raises NxwrightError for a `folder` that is a file or holds
    files, TftFileError for a file the compile's reader cannot read,
    DecodeError for what the decoders cannot read back, and NxwrightError
    for what a source folder cannot keep. It writes nothing until it has
    read the whole file, but a write that fails leaves the files written
    before it."""
    return written_folder(read_tft(tft_bytes, "the TFT file"), folder).names


def written_folder(tft: TftFile, folder: Path) -> WrittenFolder:
    """Writes the source folder of `tft`, a file the compile's reader read,
    into `folder`, as decompiled_folder does, and returns what it wrote the
    folder from. Raises as decompiled_folder does."""
    folder = Path(folder)
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise NxwrightError("%s is not an empty folder" % folder)
    decoded = read_decoded(tft)
    counts = {kind: sum(each.kind == kind for each in decoded.resources)
              for kind in ("picture", "font", "animation", "video", "sound")}

    def part(row: int) -> bytes:
        return tft.table_part(tft.table[row])
    blocks = {"picture": picture_blocks(part(PICTURE_ROW), counts["picture"]),
              "font": stored_font_blocks(part(FONT_ROW), counts["font"]),
              "animation": media_blocks(part(ANIMATION_ROW), counts["animation"]),
              "video": media_blocks(part(VIDEO_ROW), counts["video"]),
              "sound": sound_blocks(part(SOUND_ROW), counts["sound"])}
    files = folder_files(decoded, blocks)
    for path, content in files.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_bytes(content)
    return WrittenFolder(unmatched_names(decoded), decoded)


def folder_files(decoded: DecodedFile, blocks: dict) -> dict:
    """Returns the source folder's files, {path within it: bytes}, of
    `decoded`, with `blocks`, {kind: its blocks in ID order}, of each kind
    of resource the file has: "picture", its screen copies; "font";
    "animation", its screen forms; "video"; and "sound". A kind left out
    has none. Raises as decompiled_folder does."""
    pictures, fonts = blocks.get("picture", []), blocks.get("font", [])
    media = {kind: [_MEDIA_NAMES[kind] % number for number in range(len(blocks.get(kind, [])))]
             for kind in _MEDIA_NAMES}
    names = ResourceNames([_PICTURE_NAME % number for number in range(len(pictures))],
                          _font_names(fonts), media["animation"], media["video"],
                          media["sound"])
    files = {"defaults.toml": DEFAULTS_FILE.read_bytes()}
    for name, block in zip(names.pictures, pictures):
        files["pictures/%s.png" % name] = picture_file(block, decoded.rotation)
    for name, block in zip(names.fonts, fonts):
        files["fonts/%s%s" % (name, FONTS.suffixes[0])] = block
    gmovmaker, screen_form = ANIMATIONS.suffixes
    for name, block in zip(names.animations, blocks.get("animation", [])):
        files["%s/%s%s" % (ANIMATIONS.folder, name, gmovmaker)] = gmovmaker_file(block)
        files["%s/%s%s" % (ANIMATIONS.folder, name, screen_form)] = block
    for kind, names_of_kind in ((VIDEOS, names.videos), (SOUNDS, names.sounds)):
        for name, block in zip(names_of_kind, blocks.get(kind.noun, [])):
            files["%s/%s%s" % (kind.folder, name, kind.suffixes[0])] = block
    pages = []
    for decoded_page in decoded.pages:
        page_name = decoded_page.objects[0].name.text
        toml, events = page_files(decoded_page, decoded, names)
        files[page_toml_path(page_name)] = toml.encode("utf-8")
        files[page_nx_path(page_name)] = events.encode("utf-8")
        pages.append(page_name)
    files["program.nx"] = _program_text(decoded).encode("utf-8")
    if decoded.macros:
        codec = TextCodec(decoded.encoding)
        macros = [(macro.name.text, [_text(codec, line, MACROS_PATH)
                                     for line in decoded_lines(macro.code, None, decoded)])
                  for macro in decoded.macros]
        files[MACROS_PATH] = macros_to_source(macros).encode("utf-8")
    settings = DeviceSettings(model_named(decoded.model), decoded.rotation, decoded.encoding,
                              one_time_update=decoded.one_time_update,
                              memory_file_storage_size=decoded.memory_file_storage_size)
    app = {"format": SOURCE_FORMAT, "language": NEXTION, "pages": pages,
           "pictures": names.pictures, "fonts": names.fonts, "animations": names.animations,
           "videos": names.videos, "sounds": names.sounds, **device_keys(settings)}
    files["app.toml"] = app_text(app, written=None).encode("utf-8")
    return files


def unmatched_names(decoded: DecodedFile) -> list:
    """Returns each name of `decoded` no guess matched, as (what it names,
    its decoded_file.Name): the pages and their components, in ID order,
    then the int variables, then the macros. What a name names is ("page",
    the page's ID), ("object", the page's ID, the component's ID), ("int",
    the name), or ("macro", the name). Two components on two pages may
    share a readable name, with two checksums."""
    found = []
    for decoded_page in decoded.pages:
        found += [(("page", decoded_page.page_id) if each.object_id == 0
                   else ("object", decoded_page.page_id, each.object_id), each.name)
                  for each in decoded_page.objects if not each.name.matched]
    return (found + [(("int", each.name.text), each.name) for each in decoded.ints
                     if not each.name.matched]
            + [(("macro", each.name.text), each.name) for each in decoded.macros
               if not each.name.matched])


def picture_file(block: bytes, rotation: int) -> bytes:
    """Returns a PNG file whose screen copy, as the build makes it at
    `rotation`, in the format of the screen copy `block`, is `block`.
    Raises DecodeError for a screen copy nxwright cannot decode, or one
    holding a pixel no colour and alpha round to."""
    try:
        kind = screen_copy_format(block)
        pixels = decode_screen_copy(block, rotation)
    except NxwrightError as error:
        raise DecodeError("a picture's screen copy cannot be read (%s)" % error, 0,
                          block[:24]) from None
    rgba, found = bytearray(), {}
    for stored in zip(pixels.colours, pixels.alphas):
        if stored not in found:
            found[stored] = _pixel_storing(*stored, kind)
        rgba += found[stored]
    return write_png(pixels.width, pixels.height, bytes(rgba))


def gmovmaker_file(screen_form: bytes) -> bytes:
    """Returns GmovMaker's file of the animation whose screen form is
    `screen_form`: its frames, as the screen form shows them, each turned
    upright and cut to the animation's size, each lasting as long. Raises
    DecodeError for a screen form nxwright cannot read, one with a frame
    whose picture it cannot read, and one whose frames GmovMaker's file
    cannot keep."""
    try:
        frames = animation_frames(screen_form)
        images = [read_picture(picture) for picture in frames.pictures]
    except NxwrightError as error:
        raise DecodeError("an animation's screen form cannot be read (%s)" % error, 0,
                          screen_form[:8]) from None
    ends = frames.starts[1:] + (frames.length,)
    upright = []
    for image, start, end in zip(images, frames.starts, ends):
        if frames.rotation:
            image = image.transpose(_UPRIGHT[frames.rotation])
        upright.append((image.crop((0, 0, frames.width, frames.height)), end - start))
    try:
        return animation_files(upright)[0]
    except NxwrightError as error:
        # Such as a screen form of no frames, or of a frame lasting 0 ms.
        raise DecodeError("an animation's frames cannot make GmovMaker's file (%s)" % error, 0,
                          screen_form[:8]) from None


def _pixel_storing(colour: int, alpha: int, kind: int) -> bytes:
    """Returns the red, green, blue, and alpha bytes of a pixel that a
    screen copy of format `kind` stores as the RGB565 `colour` and the
    7-bit `alpha`, the most opaque such pixel. Raises DecodeError when
    there is none."""
    wanted = [colour >> shift & mask for shift, mask in _CHANNELS]
    for pixel_alpha in range(255, -1, -1):
        stored_alpha, reaching = _rounding(kind)[pixel_alpha]
        if stored_alpha != alpha:
            continue
        channels = [reaching[number].get(value) for number, value in enumerate(wanted)]
        if None not in channels:
            return bytes(channels + [pixel_alpha])
    raise DecodeError("a picture holds a pixel of colour %04X and alpha %d, which no pixel of "
                      "a picture file gives" % (colour, alpha))


@lru_cache(maxsize=None)
def _rounding(kind: int) -> list:
    """Returns, for each alpha byte of a pixel, (the alpha a screen copy of
    format `kind` stores for it, then for red, green, and blue, {each value
    the stored colour keeps: the channel's byte that gives it}), the byte
    closest to that value's even spread over 0 to 255. It is read from
    nxwright's own rounding (stored_pixels), of a grey of every byte at
    every alpha, as red, green, and blue round alike."""
    greys = Image.frombytes("RGBA", (256, 256), bytes(
        byte for alpha in range(256) for grey in range(256) for byte in (grey, grey, grey, alpha)))
    stored = stored_pixels(greys, kind)
    table = []
    for alpha in range(256):
        reaching = []
        for shift, mask in _CHANNELS:
            closest = {}
            for grey in range(256):
                value = stored.colours[alpha * 256 + grey] >> shift & mask
                spread = value * 255 // mask
                if value not in closest or abs(grey - spread) < abs(closest[value] - spread):
                    closest[value] = grey
            reaching.append(closest)
        table.append((stored.alphas[alpha * 256], reaching))
    return table


def _font_names(fonts: list) -> list:
    """Returns a name for each font of `fonts`, as nxwright's extract names
    a new one: the name in its header, or else a name from its ID, never
    one taken before it, in any letter case."""
    names, taken = [], set()
    for number, block in enumerate(fonts):
        header_name = font_header_name(block)
        name = (header_name if header_name and header_name.lower() not in taken
                else _FONT_NAME % number)
        base, copy = name, 2
        while name.lower() in taken:
            name, copy = "%s-%d" % (base, copy), copy + 1
        names.append(name)
        taken.add(name.lower())
    check_names(names, "fonts")
    return names


def _program_text(decoded: DecodedFile) -> str:
    """Returns program.nx of `decoded`: one declaration of its int
    variables, if any, then its code, each line ended with a line end; or
    _NO_LINES, for a program.s of no lines."""
    codec = TextCodec(decoded.encoding)
    lines = ["int " + ",".join("%s=%d" % (each.name.text, each.value)
                               for each in decoded.ints)] if decoded.ints else []
    lines += [_text(codec, line, "program.nx")
              for line in decoded_lines(decoded.program, None, decoded)]
    return "".join(line + "\n" for line in lines) or _NO_LINES


def _text(codec: TextCodec, line: str, where: str) -> str:
    """Returns the decoded line of code `line` as text a source file keeps.
    The decoder keeps a byte that is not text in the encoding as a
    character of its own, which no source file can. Raises NxwrightError,
    starting with `where`, for such a byte."""
    return codec.decode(codec.encode_keeping_bytes(line, where), where)
