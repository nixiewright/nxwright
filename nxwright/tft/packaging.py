"""Packaging: every part of a TFT file but the user code: header 1, header 2,
the firmware and resources section, the padding, and every checksum
(tft_file.py gives the parts and how each is checked).

The firmware is an input (Firmware). A compile finds it on the user's
computer: in a TFT file or a Nextion Editor folder the user names, in the
cache of firmware found before, or in the installed Nextion Editor.
Otherwise, with the user's consent, it downloads it from Nextion's site
(firmware.py). The firmware must come from a matched version, 1.68.2. A
test gives zeros of the same sizes instead.
Packaging works out every field of header 2 itself, from the project and from
the places of the user code's parts (UserCode.places), so that it needs
nothing from the frame.

On P and E, rows 9 to 11 of the section's table hold the project's
animations, videos, and sounds, which T and K do not take
(ResearchNotes/tft/media-packaging.md). Header 2's 0x104 gives the number of
pictures, then the number of animations, 2 bytes each, and 0x108 the
number of videos, then the number of sounds. 0x110 gives the project's
encoding, as header 1's 0x33 and the user code's entries do too
(ResearchNotes/tft/encodings.md).

A sound of 22050 samples a second, 16 bits each, goes in as it is, mono or
stereo. The Nextion Editor refuses any other sound of that rate
(_sound_taken). It resamples a sound of any other rate to that form, and to
mono, with ffmpeg, at ffmpeg's defaults, and so does packaging, with the
ffmpeg the compile was given (_sound_as_written). A compile of such a sound
without ffmpeg stops, and says how to give it one.
"""
from dataclasses import dataclass
from pathlib import Path
import struct
import tempfile

from nxwright import NxwrightError
from nxwright.project.device_settings import encoding_code
from nxwright.project.ffmpeg import sound_as_wav
from nxwright.project.media_files import sound_file
from nxwright.project.screen_models import MODELS
from nxwright.project.zi_font import decodes, turned_font

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P, two_byte_start
from nxwright.tft.firmware_versions import MATCHED_VERSIONS, matched_versions_text
from nxwright.tft.matching import Rule
from nxwright.tft.project import Project
from nxwright.tft.reasons import NOT_SUPPORTED_YET
from nxwright.tft.tft_file import (HEADER_1_SIZE, HEADER_2_END, HEADER_2_WORDS, MACRO_ENTRY_SIZE,
                            TABLE_ROWS, TABLE_SIZE, UserCode, VARIABLE_SIZE, byte_form_crc,
                            encode_f_header_2, file_checksum, firmware_names, header_2_key,
                            series_crc)
# Each series' letter, by its code in a TFT file. Its name in tft_file,
# SERIES, here names the series packaging's probes matched (matching.py).
from nxwright.tft.tft_file import SERIES as SERIES_BY_CODE

# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# A sound the Nextion Editor puts in a TFT file as it is: 22050 samples a
# second, of 16 bits each. It resamples a sound of any other form to it
# (_sound_as_written).
_SOUND_RATE, _SOUND_BITS = 22050, 16


def _on_p(need) -> bool:
    """Whether the resource `need` is of a project of P or E, whose section
    holds animations, videos, and sounds."""
    return need.series in SERIES_WRITTEN_AS_P


def _wav_chunk(block: bytes, kind: bytes):
    """Returns the data of the first chunk of the 4 letters `kind` in the
    WAV file `block`, or None when it has none."""
    # The chunks follow the 12 bytes of the RIFF header, each its 4 letters,
    # its size, 4 bytes, then its data, padded to an even size.
    at = 12
    while at + 8 <= len(block):
        size = struct.unpack_from("<I", block, at + 4)[0]
        if block[at:at + 4] == kind:
            return block[at + 8:at + 8 + size]
        at += 8 + size + size % 2
    return None


def _sound_form(block: bytes):
    """Returns the form of the sound whose WAV file is `block`, (rate, bits
    a sample, channels), as its fmt chunk gives them, whatever the format of
    its samples, such as floating-point samples of 32 bits or ADPCM ones of
    4. Returns None when `block` is no WAV file."""
    if block[:4] != b"RIFF" or block[8:12] != b"WAVE" or _wav_chunk(block, b"data") is None:
        return None
    form = _wav_chunk(block, b"fmt ")
    if form is None or len(form) < 16:
        return None
    channels, rate = struct.unpack_from("<HI", form, 2)
    return rate, struct.unpack_from("<H", form, 14)[0], channels


def font_orientation(series: str, rotation: int) -> int:
    """Returns the orientation, in degrees, a TFT file of `series` keeps its
    fonts in, for a project at `rotation`: 0 on F, as the Nextion Editor
    writes each font so whatever the project's rotation, and the project's
    rotation on the other series."""
    return 0 if series in FONTS_AT_0_DEGREES else rotation


# A font's orientation, as the byte at +3 of its header gives it (nxwright's
# zi_font module docstring). It is read alone, as a font whose encoding
# nxwright does not know, kept from a project in such an encoding, is
# written as it is when it is in the TFT file's orientation already.
_ORIENTATION_PLACE = 3
_ORIENTATIONS = {0x0a: 0, 0x0b: 90, 0x0c: 180, 0x0d: 270}


def _stored_orientation(block: bytes):
    """Returns the orientation, in degrees, the font `block` is stored in,
    or None for a block too short to give one, or of a byte not known."""
    return (_ORIENTATIONS.get(block[_ORIENTATION_PLACE])
            if len(block) > _ORIENTATION_PLACE else None)


def _font_taken(need) -> bool:
    """Whether the compile writes the font of the resource need `need`: one
    in the TFT file's orientation, written as it is, or one of a kind
    nxwright reads (zi_font.decodes, from its header alone), which it
    turns. nxwright ought to turn any font, as the Nextion Editor does, so
    another is refused as not supported yet."""
    block = need.context["block"]
    return (_stored_orientation(block) == font_orientation(need.series, need.rotation)
            or decodes(block))


def _sound_taken(need) -> bool:
    """Whether the sound of the resource `need`, its WAV file, is on P or E:
    at 22050 samples a second, 16 bits a sample, mono or stereo, which the
    Nextion Editor writes as it is; or at any other rate, which it resamples
    with ffmpeg whatever the sound's bits and channels. It refuses any other
    sound of 22050 samples a second: of other bits than 16, as the fmt chunk
    gives them ("only 16 bits are supported"), or of more than two channels
    ("Vocal Track Number Out of Effective Range (1/2)"). It reads only the
    rate, bits, and channels, whatever the format of the samples, such as
    floating-point or ADPCM ones."""
    form = _sound_form(need.context["block"])
    if not _on_p(need) or form is None:
        return False
    rate, bits, channels = form
    return rate != _SOUND_RATE or (bits == _SOUND_BITS and channels in (1, 2))


def _firmware_taken(need) -> bool:
    """Whether the firmware of `need` comes from a version of the Nextion
    Editor that the probes matched (firmware_versions.py). Firmware of any
    other version, older or later, is refused. nxwright does not know how such
    firmware reads the user code, or how it numbers the commands."""
    return tuple(int(part) for part in need.subject.split(".")) in MATCHED_VERSIONS


# What packaging has matched with probes (matching.py): the firmware of the
# Nextion Editor 1.68.2, on each screen model of the T, K, P, E, and F series
# at each rotation, with pictures and fonts, and with the device settings
# (device_setting_probes.py); and on P and E, with animations, videos, and
# sounds.
MATCHED = [
    Rule("firmware", None, "the firmware of the Nextion Editor %s" % matched_versions_text(),
         _firmware_taken),
    Rule("series", "T", "the Basic series"),
    Rule("series", "K", "the Enhanced series"),
    Rule("series", "P", "the Intelligent series"),
    Rule("series", "E", "the Edge series"),
    Rule("series", "F", "the Discovery series"),
    # Each screen model of these series that nxwright knows: models differ in
    # their device ID and screen size alone, which header 1 gives.
    *[Rule("model", model.name, "%s, %d by %d" % (model.name, model.width, model.height))
      for model in MODELS if model.series in SERIES],
    *[Rule("rotation", str(degrees), "%d degrees" % degrees) for degrees in (0, 90, 180, 270)],
    Rule("resource", "picture", "any picture"),
    Rule("resource", "font", "a font in the TFT file's orientation (font_orientation), or one "
         "nxwright can turn to it", _font_taken, NOT_SUPPORTED_YET),
    Rule("resource", "animation", "any animation, on P and E", _on_p),
    Rule("resource", "video", "any video, on P and E", _on_p),
    Rule("resource", "sound", "on P and E, a sound of 22050 samples a second, 16 bits a sample, "
         "mono or stereo, written as it is, or one of any other rate, resampled with ffmpeg; "
         "the Nextion Editor refuses any other sound of 22050 samples a second", _sound_taken),
]

# The headers of a picture's block and a font's, in the project and in a TFT
# file (project/screen_copy.py and zi_font.py), and of an
# animation's and a video's (project/media_files.py).
PICTURE_HEADER = 24
FONT_HEADER = 44
MEDIA_HEADER = 76
# Where each picture's, font's, animation's, and video's header gives where
# its rest lies in the section's part of them (_headers_first).
PICTURE_PLACE_FIELD = 8
FONT_PLACE_FIELD = 24
MEDIA_PLACE_FIELD = 8
# Where each picture's header gives its ID in the section, which the
# project keeps at 0 (_headers_first).
PICTURE_ID_FIELD = 4
# The series whose fonts a TFT file keeps at 0 degrees, whatever the
# project's rotation (font_orientation).
FONTS_AT_0_DEGREES = ("F",)
# The header a TFT file gives each sound before the sounds: where the sound
# lies in the section's part of sounds, its length, then 8 bytes of zeros.
SOUND_HEADER = struct.Struct("<II8x")
# The series whose section size is 0x20000, and whose section has rows of
# animations, videos, and sounds; the others' is 0x10000.
LARGE_SECTIONS = ("P", "E")
# The series whose header 1 gives the memory file's storage size.
MEMORY_FILE_SERIES = ("P", "E")
# Header 1's places of the screen's rotation, in quarter turns, and of the
# device settings' one-time update, a byte each, and of the memory file's
# storage size, 4 bytes, on MEMORY_FILE_SERIES.
ROTATION_PLACE, ONE_TIME_UPDATE_PLACE, MEMORY_FILE_STORAGE_PLACE = 0x14, 0x16, 0x48
_SERIES_CODES = {letter: code for code, letter in SERIES_BY_CODE.items()}
# Header 1 holds zeros up to 0x4C, but for its fields with values.
_HEADER_1_FILL = 0x4C
# Header 1 holds 0xFF from 0x4C to its checksum, but for zeros from 0x54 to
# 0x6F, among which 0x58 gives the macros' table's place in the user code,
# which is the page index's in a project without macros, and 0x6E the number
# of macros, 2 bytes.
_ZEROS_FROM, _ZEROS_TO = 0x54, 0x70


@dataclass(frozen=True)
class Firmware:
    """The firmware a TFT file holds. `version` is the version of the Nextion
    Editor it comes from, as header 1 gives it, such as (1, 68, 2). `files`
    holds each firmware file's bytes, by its name (tft_file.firmware_names)."""
    version: tuple
    files: dict


def package(project: Project, user_code: UserCode, firmware: Firmware,
            ffmpeg: str = None) -> bytes:
    """Returns the whole TFT file of `project`, whose user code is
    `user_code`, around `firmware`, resampling a sound with the program
    `ffmpeg` where the Nextion Editor does (_sound_as_written). Raises
    KeyError when `firmware` lacks a file the project's series holds, and
    NxwrightError when a sound needs ffmpeg and `ffmpeg` is None."""
    model = project.settings.model
    series = model.series
    section_size = 0x20000 if series in LARGE_SECTIONS else 0x10000
    section, rows = _section(project, firmware, series, section_size, ffmpeg)
    user_place = section_size + len(section)
    code = user_code.to_bytes()
    file_size = user_place + len(code) + 4
    header_1 = _header_1(project, user_code, firmware, rows, section, section_size, file_size)
    header_2 = _header_2(project, user_code, rows, section_size, user_place)
    body = (header_1 + header_2 + b"\xff" * (section_size - HEADER_2_END) + section + code)
    return body + struct.pack("<I", file_checksum(body, model.device_id, series))


def _section(project: Project, firmware: Firmware, series: str, section_size: int,
             ffmpeg: str = None) -> tuple:
    """Returns the firmware and resources section, padded with zeros to a
    multiple of `section_size`, and its table's rows as (place, size). Its
    sounds are resampled with `ffmpeg` where the Nextion Editor resamples
    them (_sound_as_written)."""
    names = firmware_names(series)
    parts = [firmware.files[name] for name in names]
    # The device settings that ignore image or library resources leave the
    # pictures or the fonts out of the file. Their row stays, empty.
    settings = project.settings
    pictures = (b"" if settings.ignore_image_resources
                else _headers_first(_blocks(project, "picture"), PICTURE_HEADER,
                                    PICTURE_PLACE_FIELD, PICTURE_ID_FIELD))
    fonts = (b"" if settings.ignore_library_resources
             else _headers_first(_fonts(project), FONT_HEADER, FONT_PLACE_FIELD))
    rows, at = [], TABLE_SIZE
    for part in parts:
        rows.append((at, len(part)))
        at += len(part)
    # Rows 1 to 6 hold the series' firmware files; a series with fewer has
    # rows of zeros.
    rows += [(0, 0)] * (7 - len(names))
    # Rows 9 to 11: on P and E, the animations, videos, and sounds, an empty
    # part at the end when the project has none; on T and K, which take
    # none, zeros.
    media = []
    if series in LARGE_SECTIONS:
        media = [_headers_first(_blocks(project, kind), MEDIA_HEADER, MEDIA_PLACE_FIELD)
                 for kind in ("animation", "video")]
        media.append(_sounds([_sound_as_written(name, project.blocks[name], ffmpeg)
                              for kind, name in project.resources if kind == "sound"]))
    for part in [pictures, fonts] + media:
        rows.append((at, len(part)))
        at += len(part)
    rows += [(0, 0)] * (TABLE_ROWS - len(rows))
    table = b"".join(struct.pack("<III", place, size, 0) for place, size in rows)
    section = table + b"".join(parts) + pictures + fonts + b"".join(media)
    return section + bytes(-len(section) % section_size), rows


def _blocks(project: Project, kind: str) -> list:
    """Returns the project's blocks of resources of `kind`, in ID order."""
    return [project.blocks[name] for resource, name in project.resources if resource == kind]


def _fonts(project: Project) -> list:
    """Returns the project's font blocks, in ID order, as its TFT file holds
    them: each in the TFT file's orientation (font_orientation). A project
    may keep a font in any orientation, as the Nextion Editor turns it to
    that one as it compiles, so a font in another is turned
    (zi_font.turned_font). A font already in it is written as it is, its
    glyphs' bytes too, as turning it would code them again, whatever its
    encoding. Raises NxwrightError for a font nxwright cannot turn, which
    the match check refuses first (_font_taken)."""
    kept = font_orientation(project.settings.model.series, project.settings.rotation)
    return [block if _stored_orientation(block) == kept else turned_font(block, kept)
            for block in _blocks(project, "font")]


def _headers_first(blocks: list, header_size: int, place_field: int,
                   id_field: int = None) -> bytes:
    """Returns the section's part of pictures, fonts, animations, or videos,
    from their project blocks in ID order, each a header of `header_size`
    bytes then the rest. The part holds every header first, then every
    block's rest. In each header, the u32 at `place_field` gives where the
    block's rest lies in the part, and the one at `id_field`, if any, the
    block's ID. In the project, they give where the rest lies in the block,
    and 0. So one block alone is the same in both."""
    headers, place = [], header_size * len(blocks)
    for number, block in enumerate(blocks):
        header = bytearray(block[:header_size])
        struct.pack_into("<I", header, place_field, place)
        if id_field is not None:
            struct.pack_into("<I", header, id_field, number)
        headers.append(bytes(header))
        place += len(block) - header_size
    return b"".join(headers) + b"".join(block[header_size:] for block in blocks)


def _sound_as_written(block_name: str, block: bytes, ffmpeg: str) -> bytes:
    """Returns the sound whose project block is `block`, named `block_name`
    in the project, as the Nextion Editor writes it in a TFT file: as it is,
    at 22050 samples a second of 16 bits; or else resampled to that form,
    and to mono, with the program `ffmpeg`, at its defaults, as the Nextion
    Editor does with the ffmpeg its installation bundles, then kept as a
    project keeps a sound, under the name its block keeps, or none for a
    block without one (media_files.sound_file). Raises NxwrightError when it
    needs resampling and `ffmpeg` is None, saying how to give one."""
    form = _sound_form(block)
    if form is not None and form[:2] == (_SOUND_RATE, _SOUND_BITS):
        return block
    stored = _sound_name(block)
    # The messages name a sound without a name of its own by its block.
    name = stored or block_name
    if ffmpeg is None:
        rate, bits = form[:2] if form is not None else (0, 0)
        raise NxwrightError(
            "the sound %s has %d samples a second of %d bits each, which the Nextion Editor "
            "resamples to %d samples a second of 16 bits each with ffmpeg; ffmpeg is not on "
            "the PATH: install it, or name it with --ffmpeg" % (name, rate, bits, _SOUND_RATE))
    with tempfile.TemporaryDirectory(prefix="nxwright-sound-") as work:
        source, written = Path(work) / "source", Path(work) / "written"
        source.mkdir()
        written.mkdir()
        (source / "sound.wav").write_bytes(block)
        try:
            resampled = sound_as_wav(ffmpeg, source / "sound.wav", written, _SOUND_RATE,
                                     mono=True)
        except NxwrightError as error:
            # ffmpeg's words name the copy it read, sound.wav, not the sound.
            raise NxwrightError("the sound %s could not be resampled: %s" % (name, error)) \
                from None
    return sound_file(resampled, stored or "")


def _sound_name(block: bytes):
    """Returns the name a sound's project block keeps in its hmic chunk, or
    None when it has none. The chunk starts "crc", a 0 byte, the check
    value's size and the check value, 4 bytes each, then "name", the name's
    length, 4 bytes, and the name (media_files.sound_file)."""
    chunk = _wav_chunk(block, b"hmic")
    # A chunk too short for the name's length has no name.
    if chunk is None or len(chunk) < 20:
        return None
    length = struct.unpack_from("<I", chunk, 16)[0]
    return chunk[20:20 + length].decode("ascii", "replace")


def _sounds(blocks: list) -> bytes:
    """Returns the section's part of sounds, from their project blocks, each
    a WAV file, in ID order: a header of 16 bytes for each, first, giving
    where its file lies in the part and its length (SOUND_HEADER), then
    the files as they are."""
    headers, place = [], SOUND_HEADER.size * len(blocks)
    for block in blocks:
        headers.append(SOUND_HEADER.pack(place, len(block)))
        place += len(block)
    return b"".join(headers) + b"".join(blocks)


def _header_1(project: Project, user_code: UserCode, firmware: Firmware, rows: list,
              section: bytes, section_size: int, file_size: int) -> bytes:
    """Returns header 1, its checksum included."""
    settings = project.settings
    model, series = settings.model, settings.model.series
    major, minor, build = firmware.version
    header = bytearray(b"\xff" * HEADER_1_SIZE)
    header[:_HEADER_1_FILL] = bytes(_HEADER_1_FILL)
    header[_ZEROS_FROM:_ZEROS_TO] = bytes(_ZEROS_TO - _ZEROS_FROM)
    struct.pack_into("<I", header, 0x58, user_code.places()["macros"][0])
    struct.pack_into("<H", header, 0x6E, len(user_code.macros) // MACRO_ENTRY_SIZE)
    # 0x03 is "N", for Nextion; 0x32 and 0x38 hold the same in every file seen.
    # 0x33 holds the first byte of the encoding's two-byte characters, or 0.
    header[0x01:0x04] = bytes([major, minor]) + b"N"
    # The rotation, the series, the one-time update, which is 1 in the
    # Nextion Editor's file of a project that sets it, and the build of the
    # Editor's version, a byte each.
    header[ROTATION_PLACE] = settings.rotation // 90
    header[ROTATION_PLACE + 1] = _SERIES_CODES[series]
    header[ONE_TIME_UPDATE_PLACE] = int(settings.one_time_update)
    header[ONE_TIME_UPDATE_PLACE + 1] = build
    struct.pack_into("<HHHH", header, 0x0C, max(model.width, model.height),
                     min(model.width, model.height), model.width, model.height)
    header[0x2E:0x32] = model.device_id
    header[0x32:0x34] = bytes([0x21, two_byte_start(settings.encoding)])
    second = rows[2]
    values = {0x18: section_size + second[0], 0x22: second[1], 0x34: section_size,
              0x38: 0x0C, 0x3C: file_size, 0x40: len(section),
              0x44: series_crc(section, series)}
    # The device settings' memory file storage size, in bytes, which the
    # Nextion Editor writes on P and E only. Its project settings dialog
    # offers it only there.
    if series in MEMORY_FILE_SERIES:
        values[MEMORY_FILE_STORAGE_PLACE] = settings.memory_file_storage_size
    if series not in LARGE_SECTIONS:
        # The main firmware file, row 1, and two of its own values, at its
        # offsets 1 and 5. P and E give 0 in these fields.
        main_place, main = section_size + rows[1][0], firmware.files[firmware_names(series)[1]]
        offset_1, offset_5 = struct.unpack_from("<II", main, 1)
        values.update({0x04: main_place + offset_1, 0x08: offset_5,
                       0x1E: section_size + second[0], 0x26: main_place, 0x2A: rows[1][1]})
    for place, value in values.items():
        struct.pack_into("<I", header, place, value)
    struct.pack_into("<I", header, 0xC4, byte_form_crc(bytes(header[:0xC4])))
    return bytes(header)


def _header_2(project: Project, user_code: UserCode, rows: list, section_size: int,
              user_place: int) -> bytes:
    """Returns header 2, its checksum included. On T, K, P, and E, its words
    with values are XORed with the key, and the others hold 0xFFFFFFFF as
    stored. On F, every word is scrambled (encode_f_header_2), those past the
    values holding 0xFFFFFFFF before."""
    settings = project.settings
    model, series = settings.model, settings.model.series
    places = user_code.places()
    pages = len(project.pages)
    objects = sum(len(page.objects) for page in project.pages)
    # The place of the pictures, and of the fonts, is 0 when the device
    # settings leave them out of the file (_section), with or without any.
    pictures = 0 if settings.ignore_image_resources else section_size + rows[7][0]
    fonts = 0 if settings.ignore_library_resources else section_size + rows[8][0]
    words = [places["after the blocks"][0], places["variables"][0],
             len(user_code.variables) // VARIABLE_SIZE, places["variables"][1], section_size,
             user_place, user_place + places["page index"][0],
             user_place + places["page index"][1], pictures]
    words += ([section_size + rows[row][0] for row in (9, 10, 11)]
              if series in LARGE_SECTIONS else [0, 0, 0])
    # 0x104 and 0x108 give two counts each, 2 bytes apiece; T and K hold no
    # animations, videos, or sounds. 0x110 gives the project's encoding, by
    # its code in the project file.
    words += [fonts, 4 + len(user_code.blocks[0]), pages | (objects << 16),
              project.resource_count("picture") | (project.resource_count("animation") << 16),
              project.resource_count("video") | (project.resource_count("sound") << 16),
              project.resource_count("font"), encoding_code(project.settings.encoding)]
    if series == "F":
        words += [0xFFFFFFFF] * (HEADER_2_WORDS - len(words))
        header = b"".join(struct.pack("<I", word)
                          for word in encode_f_header_2(model.device_id, words))
    else:
        key = header_2_key(model.device_id, series)
        header = b"".join(struct.pack("<I", word ^ key) for word in words)
        header += b"\xff" * 4 * (HEADER_2_WORDS - len(words))
    return header + struct.pack("<I", byte_form_crc(header))
