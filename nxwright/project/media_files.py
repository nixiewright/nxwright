"""The files of animations, videos, and sounds: the frames of an animation
and of a video, and the length of a sound, as the screen plays them; an
animation's two files written, as GmovMaker and the Editor write them; a
video's, as VideoBox writes it, and made again for another rotation; a
sound, as the Editor's Audio panel writes it (docs/format.md, Animations,
videos, and sounds); and a picture file of an SD card, as PictureBox writes
it, and read (docs/format.md, Pictures for the SD card).

GmovMaker's file of an animation (its "N.gmovs" block), the screen's form
of it (its "N.gmov" block), and a video (its "N.v" block) share a layout.
All numbers are little-endian:
  +0   8 bytes  "GMOV", the rotation's marker, "V" for GmovMaker's file or
                "R" for the screen's form, a line feed, and a zero byte; or
                "VIDE", the rotation's marker, "P", the frame rate, and a
                zero byte for a video
  +8   u32      the header's size (76)
  +12  u32      the number of frames
  +16  u16 u16  the width and height
  +24  u32      the file's size, less the header's
  +36  u32      how long a run lasts, in milliseconds: a video's to where
                one that does not loop stops
  +40  u32      the size of the entries and frames
  +44  u32      the size of the closing chunk, 4,096
  +48  u32      256 in an animation's files, 0 in a video
then, from the header's end, an entry of 40 bytes per frame:
  +0   u32      its kind: the file's form in its high byte, 2 in
                GmovMaker's file, 4 in the screen's form, and 1 in a video;
                the rotation's marker in its low byte
  +8   u32      where the frame starts, counted from the first entry
  +12  u16 u16  the frame's width and height
  +16  u32      the frame's size
  +24  u32      an animation's frame's duration in milliseconds
  +28  u32      when an animation's frame starts, in milliseconds
Each file ends with a chunk of 4,096 bytes: "hmic", its size less 8, and
zeros. The other bytes are zero, or not understood.

A frame of GmovMaker's file is a PNG picture in a .NET serialisation of a
System.Drawing.Bitmap: a prefix of 161 bytes, the same for every frame but
for the PNG's length at its end, the PNG, and an end byte. A frame of the
screen's form is a header of 20 bytes, 0, then the JPEG picture's width and
height, then zeros; then the JPEG picture, coded at the IJG's quality 82,
the frame padded with black at its right and bottom to whole blocks of 16
pixels: 33 by 17 became a JPEG of 48 by 32. A video's frame is the JPEG
picture alone, coded at quality 80, padded with white.

The rotation's marker is that of the screen the frames are stored for, as
a screen copy's (screen_copy.py): 0x0A, plus the rotation in degrees / 90.
For a turned screen, VideoBox and the Editor's Gmov panel pad each frame,
then turn it as the screen stores a picture (screen_copy.stored_order): at
90 degrees, a frame 72 by 40 is a JPEG picture of 48 by 80. The header's
and the entries' sizes stay the frame's own. GmovMaker has no direction
setting, and each of its files seen has the marker of 0. (Worked out from
files VideoBox and the Editor wrote, at each rotation.)

The Editor's simulator showed which frame plays when (tests/test_playback.py):
an animation's frame for as long as its duration; a video's frame n from
n * 1000 / its frame rate milliseconds, to the next whole millisecond. A
run of a video lasts its frames' number * 1000 / its frame rate, rounded
up, as its `stim` showed, and one that does not loop stops at that time
rounded down, as its `tim` showed. A sound's run lasts its samples' time,
rounded up to the next millisecond.
"""
from dataclasses import dataclass
import bisect
import io
import struct
import zlib

from PIL import Image

from nxwright import NxwrightError
from nxwright.project.pictures import read_picture, write_png
from nxwright.project.screen_copy import (OPAQUE, ROTATION_MARKER_0, ROTATIONS, decode_alphas,
                                          encode_alphas)

# A video's or a sound's `from` naming a file on an SD card, by its `path`,
# rather than one of the project's, by its `vid`.
FROM_CARD = 1
# The quality, on the IJG's scale, of the JPEG pictures of the Editor's
# screen form of an animation, and of VideoBox's videos.
SCREEN_QUALITY = 82
VIDEO_QUALITY = 80
# How many of a video file's first bytes give its kind, the rotation it is
# made for, and its frame rate (video_rotation).
VIDEO_HEAD_SIZE = 8
# A file's magic: its kind's four letters, the rotation's marker, then its
# form's letters (the opening comment).
_ANIMATION_LETTERS, _VIDEO_LETTERS = b"GMOV", b"VIDE"
_SCREEN_FORM, _GMOVMAKER_FORM, _VIDEO_FORM = b"R\n\0", b"V\n\0", b"P"
_HEADER_SIZE = 76
_ENTRY_SIZE = 40
_FRAME_HEADER_SIZE = 20     # before each of an animation's frames
_JPEG_START = b"\xff\xd8"
_PNG_START = b"\x89PNG\r\n\x1a\n"
# A JPEG picture's frame headers, baseline, extended, and progressive, and its scan.
_JPEG_FRAMES, _JPEG_SCAN = (0xC0, 0xC1, 0xC2), 0xDA
# An entry's kind, by the file's form, before the rotation's marker is added.
_GMOVMAKER_KIND, _SCREEN_KIND, _VIDEO_KIND = 0x02000000, 0x04000000, 0x01000000
# The header's word at +48 in both of an animation's files; its meaning is
# not known, and a video has 0 there.
_ANIMATION_WORD = 256
# What VideoBox pads a frame with, white, and a wholly transparent pixel's colour.
_WHITE, _BLACK = (255, 255, 255), (0, 0, 0)
# A WAV file's formats of samples: PCM, float, and the extensible format,
# which names one of them in its subformat, from this byte of the format
# chunk. The Editor's Audio panel cuts the chunk to its first 16 bytes, and
# an extensible one's subformat with it.
_PCM, _FLOAT, _EXTENSIBLE = 1, 3, 0xFFFE
_SUBFORMAT_AT = 24
# The size of the Editor's `hmic` chunk.
_SOUND_NOTE_SIZE = 504
# Each byte's bits read the other way round (screen_crc).
_BITS_REVERSED = bytes(int(format(value, "08b")[::-1], 2) for value in range(256))
# PictureBox's qualities, by the names its list gives them, on the IJG's scale.
CARD_PICTURE_QUALITIES = {"highest": 100, "very-high": 96, "high": 80, "middle": 70, "low": 50,
                          "very-low": 30}
# A picture file of PictureBox's (.xi): its magic, then a header laid out as
# a screen copy's (screen_copy.py): the rotation's marker, then 0, 0, and 1;
# two words whose meaning is not known, always 0xFFFF and 24; the picture's
# own width and height; the size of what follows; and where its alpha section
# starts, from the header's end, or 0 for none.
_CARD_PICTURE_MAGIC = b"hmipicxi"
_CARD_PICTURE_HEADER = struct.Struct("<BBBBIIHHII")
_CARD_PICTURE_UNKNOWN = (0xFFFF, 24)
_CLOSING_SIZE = 4096
_CLOSING = b"hmic" + struct.pack("<I", _CLOSING_SIZE - 8) + bytes(_CLOSING_SIZE - 8)
# A .NET BinaryFormatter stream of a System.Drawing.Bitmap up to its data's
# length: its header, the System.Drawing library, the Bitmap class with its
# one member, "Data", and that byte array's record. Then come the length,
# the array's type (2, bytes), the bytes, and the stream's end (0x0B).
_BITMAP_PREFIX = bytes.fromhex(
    "0001000000ffffffff01000000000000000c02000000"
    + b"QSystem.Drawing, Version=2.0.0.0, Culture=neutral, PublicKeyToken=b03f5f7f11d50a3a".hex()
    + "0501000000" + b"\x15System.Drawing.Bitmap".hex() + "01000000" + b"\x04Data".hex()
    + "07020200000009030000000f03000000")
_BYTE_ARRAY, _STREAM_END = b"\x02", b"\x0b"
# A JPEG picture of the screen's form is padded to whole blocks of this many pixels.
_BLOCK = 16


@dataclass(frozen=True)
class Frames:
    """What a run of an animation or a video shows, and when."""
    width: int          # each frame's own width and height
    height: int
    pictures: tuple     # each frame's JPEG picture, in order, padded and turned as stored
    starts: tuple       # when each frame starts showing, in ms from the run's start
    length: int         # how long a run lasts, in ms: the component's `stim`
    end: int            # where a run that does not loop stops, in ms
    rotation: int = 0   # the screen's rotation the pictures are stored for
    rate: int = 0       # a video's frames a second, its `fps`; 0 for the others

    def at(self, time: int) -> int:
        """Returns the number of the frame showing `time` ms into a run."""
        return min(max(bisect.bisect_right(self.starts, time) - 1, 0), len(self.pictures) - 1)


def animation_frames(screen_form: bytes) -> Frames:
    """Returns the frames of an animation's screen form.

    Raises NxwrightError for a file that is not one, a rotation's marker
    there is not, or a frame that lies outside the file or holds no JPEG
    picture."""
    if screen_form[:4] != _ANIMATION_LETTERS or screen_form[5:8] != _SCREEN_FORM:
        raise NxwrightError("not the screen's form of an animation")
    rotation = _rotation(screen_form[4], "the animation's")
    width, height, entries = _entries(screen_form)
    pictures, starts, time = [], [], 0
    for number, (place, size, duration) in enumerate(entries):
        pictures.append(_picture(screen_form, number, place + _FRAME_HEADER_SIZE,
                                 size - _FRAME_HEADER_SIZE))
        starts.append(time)
        time += duration
    return Frames(width, height, tuple(pictures), tuple(starts), time, time, rotation)


def gmovmaker_frames(data: bytes) -> list:
    """Returns the frames of GmovMaker's file of an animation, as
    animation_files takes them: [(an RGBA image, its duration in ms)], each
    picture read from its frame's PNG.

    Raises NxwrightError for a file that is not GmovMaker's form, saying so
    of the screen's form; for one whose rotation's marker is not that of no
    rotation, which every file of GmovMaker's seen had; and for a frame that
    lies outside the file or holds no PNG picture."""
    if data[:4] != _ANIMATION_LETTERS or data[5:8] != _GMOVMAKER_FORM:
        if data[:4] == _ANIMATION_LETTERS and data[5:8] == _SCREEN_FORM:
            raise NxwrightError("the form the screen shows, which the Nextion Editor makes of "
                                "GmovMaker's file: give GmovMaker's file")
        raise NxwrightError("not a file of GmovMaker's")
    if data[4] != ROTATION_MARKER_0:
        raise NxwrightError("a rotation marker of 0x%02X, where every file of GmovMaker's seen "
                            "has 0x%02X, for no rotation" % (data[4], ROTATION_MARKER_0))
    _, _, entries = _entries(data)
    frames = []
    for number, (place, size, duration) in enumerate(entries):
        if place + size > len(data):
            raise NxwrightError("frame %d lies outside the file" % number)
        frame = data[place:place + size]
        # A .NET serialisation of a bitmap: a prefix, the PNG, and an end byte.
        start = frame.find(_PNG_START)
        end = _png_end(frame, start) if start >= 0 else -1
        if end < 0:
            raise NxwrightError("frame %d holds no PNG picture" % number)
        try:
            frames.append((read_picture(frame[start:end]), duration))
        except NxwrightError as error:
            raise NxwrightError("frame %d: %s" % (number, error)) from None
    return frames


def _png_end(data: bytes, start: int) -> int:
    """Returns where the PNG picture at `start` of `data` ends, past its
    IEND chunk, read chunk by chunk by their lengths; or -1 when it does not
    end within `data`."""
    place = start + len(_PNG_START)
    while place + 12 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, place)
        place += 12 + length
        if kind == b"IEND":
            return place if place <= len(data) else -1
    return -1


def video_frames(video: bytes) -> Frames:
    """Returns the frames of a video file.

    Raises NxwrightError for a file that is not one, a rotation's marker
    there is not, a frame rate of 0, or a frame that lies outside the file
    or holds no JPEG picture."""
    rotation = video_rotation(video)
    rate = video[6]
    if rate == 0:
        raise NxwrightError("the video's frame rate is 0")
    width, height, entries = _entries(video)
    pictures = tuple(_picture(video, number, place, size)
                     for number, (place, size, _) in enumerate(entries))
    starts = tuple(-(-1000 * number // rate) for number in range(len(pictures)))
    return Frames(width, height, pictures, starts, -(-1000 * len(pictures) // rate),
                  1000 * len(pictures) // rate, rotation, rate)


def video_rotation(head: bytes) -> int:
    """Returns the rotation of the screen a video file's frames are stored
    for, from `head`, its first VIDEO_HEAD_SIZE bytes or more. Raises
    NxwrightError for a file that is not a video file, or a rotation's
    marker there is not."""
    if len(head) < VIDEO_HEAD_SIZE or head[:4] != _VIDEO_LETTERS or head[5:6] != _VIDEO_FORM:
        raise NxwrightError("not a video file")
    return _rotation(head[4], "the video's")


def sound_frames(sound: bytes) -> Frames:
    """Returns a sound's run as Frames: none to show, and its length.

    Raises NxwrightError for a file that is not a WAV file."""
    length = sound_length(sound)
    return Frames(0, 0, (), (), length, length)


def sound_length(sound: bytes) -> int:
    """Returns how long a WAV file plays, in ms, rounded up: the frames its
    data chunk holds, at its rate. It takes every sound the Editor's Audio
    panel keeps: PCM or float samples of any size, tagged as either or as
    the extensible format, whose subformat the panel may have cut off.

    Raises NxwrightError for a file that is not a WAV file, one of other
    samples, such as compressed ones, or one whose rate or frame size is 0."""
    form, samples = _wav_format_and_samples(sound)
    tag, _, rate, _, frame_size = struct.unpack_from("<HHIIH", form)
    if tag == _EXTENSIBLE and len(form) >= _SUBFORMAT_AT + 2:
        tag, = struct.unpack_from("<H", form, _SUBFORMAT_AT)
    if tag not in (_PCM, _FLOAT, _EXTENSIBLE):
        raise NxwrightError("not a WAV file the screen plays: its samples are neither PCM "
                            "nor float")
    if rate == 0:
        raise NxwrightError("not a WAV file the screen plays: its rate is 0")
    if frame_size == 0:
        raise NxwrightError("not a WAV file the screen plays: its frames are 0 bytes")
    return -(-1000 * (len(samples) // frame_size) // rate)


def animation_files(frames: list, rotation: int = 0) -> tuple:
    """Returns (GmovMaker's file, the screen's form) of an animation, its
    `frames` [(an RGBA Pillow image, duration in ms)], all of one size, for
    a screen turned `rotation` degrees. GmovMaker's file is the same at
    every rotation. The screen's form has no transparency: a pixel keeps its
    own colour, and one wholly transparent is black, as the Editor's form of
    a frame of both showed.

    Raises NxwrightError for a rotation there is not, no frames, frames of
    two sizes, a duration under 1 ms, a size of 0 or past 65,535, or a run
    past 4,294,967,295 ms."""
    marker = _marker(rotation)
    if not frames:
        raise NxwrightError("an animation needs a frame")
    width, height = frames[0][0].width, frames[0][0].height
    if any((image.width, image.height) != (width, height) for image, _ in frames):
        raise NxwrightError("an animation's frames must all be %d by %d, as its first" % (
            width, height))
    if any(not isinstance(duration, int) or duration < 1 for _, duration in frames):
        raise NxwrightError("a frame lasts 1 ms at least")
    run = sum(duration for _, duration in frames)
    _check_size_and_run("an animation", width, height, run)
    pngs = [write_png(width, height, image.tobytes()) for image, _ in frames]
    gmovmaker = [(_BITMAP_PREFIX + struct.pack("<I", len(png)) + _BYTE_ARRAY + png + _STREAM_END,
                  duration) for png, (_, duration) in zip(pngs, frames)]
    padded = _padded(width, height)
    screen = []
    for image, duration in frames:
        stored = _turned(_opaque(image, *padded), rotation)
        screen.append((struct.pack("<III8x", 0, stored.width, stored.height)
                       + _jpeg(stored, SCREEN_QUALITY), duration))
    # GmovMaker has no direction setting: its files carry the upright marker.
    upright = _marker(0)
    return (_frames_file(_ANIMATION_LETTERS + bytes((upright,)) + _GMOVMAKER_FORM,
                         _GMOVMAKER_KIND + upright, width, height, gmovmaker, run,
                         _ANIMATION_WORD),
            _frames_file(_ANIMATION_LETTERS + bytes((marker,)) + _SCREEN_FORM,
                         _SCREEN_KIND + marker, width, height, screen, run, _ANIMATION_WORD))


def video_frame(image, rotation: int = 0) -> bytes:
    """Returns the JPEG picture of a video's frame, `image` (an RGBA
    Pillow image), as VideoBox codes one for a screen turned
    `rotation` degrees: padded with white at its right and bottom to whole
    blocks of 16 pixels, turned (the opening comment), at quality 80. It
    has no transparency, a pixel keeping its own colour and a wholly
    transparent one black, as in an animation's screen form (assumed:
    VideoBox reads frames without it).

    Raises NxwrightError for a rotation there is not."""
    padded = _padded(image.width, image.height)
    return _jpeg(_turned(_opaque(image, *padded, _WHITE), rotation), VIDEO_QUALITY)


def video_file(width: int, height: int, rate: int, pictures: list, rotation: int = 0) -> bytes:
    """Returns a video file, as VideoBox writes it, of `pictures`, its
    frames' JPEG pictures (video_frame) of a video `width` by `height`,
    playing `rate` frames a second, for a screen turned `rotation` degrees.

    Raises NxwrightError for a rotation there is not, no frames, a rate
    outside 1 to 255, which the file keeps in a byte, a size of 0 or past
    65,535, a run past 4,294,967,295 ms, or a file past 4 GB."""
    marker = _marker(rotation)
    if not pictures:
        raise NxwrightError("a video needs a frame")
    check_video_rate(rate)
    # Where a run that does not loop stops, as the header keeps it.
    run = len(pictures) * 1000 // rate
    _check_size_and_run("a video", width, height, run)
    return _frames_file(_VIDEO_LETTERS + bytes((marker,)) + _VIDEO_FORM + bytes((rate, 0)),
                        _VIDEO_KIND + marker, width, height,
                        [(picture, 0) for picture in pictures], run, 0)


def check_video_rate(rate: int):
    """Raises NxwrightError unless a video's file can keep `rate`, which it
    holds in a byte: from 1 to 255 frames a second."""
    if not 1 <= rate <= 255:
        raise NxwrightError("a video plays from 1 to 255 frames a second")


def sound_file(wav: bytes, name: str) -> bytes:
    """Returns `wav`, a WAV file of PCM samples of 8 or 16 bits, mono or
    stereo, as a project stores it, its samples unchanged: the RIFF header,
    the first 16 bytes of its format chunk, the Editor's `hmic` chunk,
    holding the check value (screen_crc) and `name`, and its samples, padded
    with zeros to a whole number of 4 bytes. Its other chunks are left out.

    Raises NxwrightError for a file that is not such a WAV file, or a name
    of more than 484 bytes, which `hmic` holds no more of."""
    form, samples = _wav_format_and_samples(wav)
    form = form[:16]
    tag, channels, rate, _, _, bits = struct.unpack("<HHIIHH", form)
    if tag != _PCM or bits not in (8, 16) or channels not in (1, 2) or rate == 0:
        raise NxwrightError("not a WAV file of PCM samples of 8 or 16 bits, mono or stereo")
    samples += bytes(-len(samples) % 4)
    data = b"data" + struct.pack("<I", len(samples)) + samples
    stored = name.encode("ascii")
    head = b"crc\0" + struct.pack("<II", 4, screen_crc(data[:len(samples)])) + b"name"
    room = _SOUND_NOTE_SIZE - len(head) - 4
    if len(stored) > room:
        raise NxwrightError("a sound's name is at most %d bytes" % room)
    note = head + struct.pack("<I", len(stored)) + stored
    body = (b"WAVE" + b"fmt " + struct.pack("<I", len(form)) + form + b"hmic"
            + struct.pack("<I", _SOUND_NOTE_SIZE) + note + bytes(_SOUND_NOTE_SIZE - len(note))
            + data)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def sound_file_problem(wav: bytes):
    """Returns what keeps `wav`, a sound's file, from being in the form the
    Editor's Audio panel writes (sound_file), or None: it has no `hmic`
    chunk, or that chunk's check value does not match its samples. A file
    that is not a WAV file at all has no such problem to report."""
    try:
        chunks = _wav_chunks(wav)
    except NxwrightError:
        return None
    if b"data" not in chunks:
        return None
    if b"hmic" not in chunks:
        return "it has no hmic chunk"
    note = chunks[b"hmic"][1]
    data_at, samples = chunks[b"data"]
    if not note.startswith(b"crc\0\x04\0\0\0") or len(note) < 12 or \
            struct.unpack_from("<I", note, 8)[0] != screen_crc(wav[data_at:data_at + len(samples)]):
        return "its hmic chunk's check value does not match its samples"
    return None


def screen_crc(data: bytes) -> int:
    """Returns the check value of `data` the Editor writes in a sound's
    `hmic` chunk: the CRC of the project's stamps (stamp.word_crc, from
    stamp.CRC_START), fed `data` as 32-bit little-endian words, the last
    padded with zeros, as the screen's STM32-like chip computes it in
    hardware. The Editor runs it over the data chunk's header and as many
    bytes on as the samples hold, so their last 8 bytes are left out.
    zlib computes it here, many times faster than word_crc, as the checks
    read every sound each time they run."""
    data += bytes(-len(data) % 4)
    words = bytearray(len(data))
    for at in range(4):
        words[at::4] = data[3 - at::4]
    # zlib's CRC-32 is this one with each byte's bits, and the result's,
    # read the other way round, and its result inverted.
    value = zlib.crc32(bytes(words).translate(_BITS_REVERSED)) ^ 0xFFFFFFFF
    return int(format(value, "032b")[::-1], 2)


@dataclass(frozen=True)
class CardPicture:
    """A picture file of an SD card in PictureBox's form (.xi), as an
    external picture shows it (card_picture_file)."""
    width: int          # the picture's own width and height
    height: int
    rotation: int       # the screen's rotation it is stored for
    jpeg: bytes         # its JPEG picture, padded and turned as it is stored
    alphas: tuple       # each stored pixel's 7-bit alpha, in the JPEG's order; None when opaque

    @property
    def stored_size(self) -> tuple:
        """The JPEG picture's width and height: the picture's own, padded to
        whole blocks of 16 pixels, and turned."""
        width, height = _padded(self.width, self.height)
        return (height, width) if self.rotation in (90, 270) else (width, height)


def card_picture_file(image, quality: int, rotation: int) -> bytes:
    """Returns the picture file of an SD card PictureBox writes of `image`
    (an RGBA Pillow image), at `quality` on the IJG's scale, for a screen
    turned `rotation` degrees: "hmipicxi"; a header laid out as a screen
    copy's (screen_copy.py); the JPEG picture, padded with black at its
    right and bottom to whole blocks of 16 pixels, then turned as a screen
    copy's pixels are, each pixel its own colour, a wholly transparent one
    black; and, when some pixel is not opaque, an alpha section coded as a
    screen copy's over the turned picture, the padding wholly transparent.

    Raises NxwrightError for a rotation or a quality there is not."""
    marker = _marker(rotation)
    if not 1 <= quality <= 100:
        raise NxwrightError("a JPEG picture's quality is from 1 to 100")
    width, height = _padded(image.width, image.height)
    jpeg = _jpeg(_turned(_opaque(image, width, height), rotation), quality)
    alphas = b""
    alpha = image.getchannel("A")
    if alpha.getextrema()[0] < 255:
        # The screen keeps 7 bits of alpha; the padding is wholly transparent.
        padded = Image.new("L", (width, height), 0)
        padded.paste(alpha.point(lambda value: value * OPAQUE // 255))
        alphas = encode_alphas(list(_turned(padded, rotation).tobytes()))
    header = _CARD_PICTURE_HEADER.pack(marker, 0, 0, 1,
                                       *_CARD_PICTURE_UNKNOWN, image.width, image.height,
                                       len(jpeg) + len(alphas),
                                       len(jpeg) if alphas else 0)
    return _CARD_PICTURE_MAGIC + header + jpeg + alphas


def is_card_picture(data: bytes) -> bool:
    """Whether `data` is a picture file of PictureBox's (.xi), by its magic."""
    return data.startswith(_CARD_PICTURE_MAGIC)


def read_card_picture(data: bytes) -> CardPicture:
    """Reads a picture file of an SD card in PictureBox's form
    (card_picture_file). Raises NxwrightError for a file that is not one,
    is cut short, or holds no JPEG picture."""
    start = len(_CARD_PICTURE_MAGIC) + _CARD_PICTURE_HEADER.size
    if not data.startswith(_CARD_PICTURE_MAGIC) or len(data) < start:
        raise NxwrightError("not a picture file of PictureBox's (.xi)")
    marker, _, _, _, _, _, width, height, size, alpha_at = _CARD_PICTURE_HEADER.unpack_from(
        data, len(_CARD_PICTURE_MAGIC))
    rotation = _rotation(marker, "the .xi file's")
    if start + size > len(data) or alpha_at > size:
        raise NxwrightError("the .xi file is cut short")
    jpeg = data[start:start + (alpha_at or size)]
    if not jpeg.startswith(_JPEG_START):
        raise NxwrightError("the .xi file holds no JPEG picture")
    picture = CardPicture(width, height, rotation, jpeg, None)
    stored = picture.stored_size
    # The alpha section, and the webview's mask of it, cover the JPEG's pixels.
    if _jpeg_size(jpeg) != stored:
        raise NxwrightError("the .xi file's JPEG picture is not the %d by %d its header gives"
                            % stored)
    if not alpha_at:
        return picture
    try:
        alphas = decode_alphas(data[start + alpha_at:start + size], stored[0] * stored[1])
    except NxwrightError:
        raise NxwrightError("the .xi file's alpha section does not cover its picture "
                            "exactly") from None
    return CardPicture(width, height, rotation, jpeg, tuple(alphas))


def _jpeg_size(jpeg: bytes):
    """Returns (width, height) of a JPEG picture, as its frame header gives
    them, or None when it has none before its scan."""
    at = len(_JPEG_START)
    while at + 4 <= len(jpeg) and jpeg[at] == 0xFF:
        marker = jpeg[at + 1]
        if marker in _JPEG_FRAMES and at + 9 <= len(jpeg):
            height, width = struct.unpack_from(">HH", jpeg, at + 5)
            return width, height
        if marker == _JPEG_SCAN:
            break
        at += 2 + struct.unpack_from(">H", jpeg, at + 2)[0]
    return None


def _wav_chunks(wav: bytes) -> dict:
    """Returns {kind: (place of its header in `wav`, body)} of the chunks of
    a WAV file, the first of each kind. Raises NxwrightError for a file that
    is not a WAV file, or a chunk cut short."""
    if len(wav) < 12 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise NxwrightError("not a WAV file")
    chunks, at = {}, 12
    while at + 8 <= len(wav):
        kind, size = wav[at:at + 4], struct.unpack_from("<I", wav, at + 4)[0]
        if at + 8 + size > len(wav):
            raise NxwrightError("the WAV file's %s chunk is cut short" % kind.decode("latin-1"))
        chunks.setdefault(kind, (at, wav[at + 8:at + 8 + size]))
        at += 8 + size + (size & 1)
    return chunks


def _wav_format_and_samples(wav: bytes) -> tuple:
    """Returns (the format chunk's body, the data chunk's body) of a WAV
    file. Raises NxwrightError for a file that is not a WAV file, or one
    without the two chunks, or whose format chunk is under 16 bytes."""
    chunks = _wav_chunks(wav)
    if b"fmt " not in chunks or b"data" not in chunks or len(chunks[b"fmt "][1]) < 16:
        raise NxwrightError("not a WAV file: it lacks a format or a data chunk")
    return chunks[b"fmt "][1], chunks[b"data"][1]


def _check_size_and_run(what: str, width: int, height: int, run: int):
    """Raises NxwrightError unless an animation's or a video's file can keep
    its size and its run, which it holds in 16 and 32 bits: from 1 to 65,535
    pixels each way, and at most 4,294,967,295 ms. `what` names it, as "a
    video"."""
    if not (0 < width <= 0xFFFF and 0 < height <= 0xFFFF):
        raise NxwrightError("%s is at least 1 and at most 65,535 pixels wide and high" % what)
    if run > 0xFFFFFFFF:
        raise NxwrightError("%s's run lasts 4,294,967,295 ms at most" % what)


def turned_video(video: bytes, rotation: int) -> bytes:
    """Returns a video file made again for a screen turned `rotation`
    degrees, as VideoBox would have made it, at the same rate: each frame
    decoded, turned back upright, cut to the video's own size, and coded
    again (video_frame). Coding a JPEG picture again loses a little of it.
    A video made for `rotation` already is returned as it is.

    Raises NxwrightError for a rotation there is not, and as video_frames
    does for a file it cannot read."""
    _check_rotation(rotation)
    frames = video_frames(video)
    if frames.rotation == rotation:
        return video
    pictures = []
    for picture in frames.pictures:
        with Image.open(io.BytesIO(picture)) as stored:
            # Turning by the rest of a whole turn puts it back upright.
            upright = _turned(stored.convert("RGBA"), (360 - frames.rotation) % 360)
        pictures.append(video_frame(upright.crop((0, 0, frames.width, frames.height)), rotation))
    return video_file(frames.width, frames.height, video[6], pictures, rotation)


def _padded(width: int, height: int) -> tuple:
    """A frame's size padded to whole JPEG blocks, as the Editor and
    VideoBox code it."""
    return -(-width // _BLOCK) * _BLOCK, -(-height // _BLOCK) * _BLOCK


def _check_rotation(rotation: int):
    """Raises NxwrightError unless a screen turns `rotation` degrees."""
    if rotation not in ROTATIONS:
        raise NxwrightError("a rotation is one of %s" % ", ".join(map(str, ROTATIONS)))


def _marker(rotation: int) -> int:
    """Returns the marker of a picture or frames stored for a screen turned
    `rotation` degrees, as a screen copy's (screen_copy.py). Raises
    NxwrightError for a rotation there is not."""
    _check_rotation(rotation)
    return ROTATION_MARKER_0 + rotation // 90


def _rotation(marker: int, owner: str) -> int:
    """Returns the rotation `marker` stands for (_marker). Raises
    NxwrightError for a marker there is not, saying it is `owner`'s, such
    as "the video's"."""
    rotation = (marker - ROTATION_MARKER_0) * 90
    if rotation not in ROTATIONS:
        raise NxwrightError("%s rotation marker %#x is not one known" % (owner, marker))
    return rotation


# How Pillow turns a picture into the order the screen stores it in, by the
# screen's rotation (screen_copy.stored_order): at 90 degrees, its columns
# from the left, each from the bottom, which is a quarter turn clockwise.
_TURNS = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
          270: Image.Transpose.ROTATE_90}


def _turned(picture: Image.Image, rotation: int) -> Image.Image:
    """Returns `picture` as the screen stores it for a screen turned
    `rotation` degrees: its width and height swap at 90 and 270 degrees.
    Raises NxwrightError for a rotation there is not."""
    _check_rotation(rotation)
    return picture if rotation == 0 else picture.transpose(_TURNS[rotation])


def _opaque(image: Image.Image, width: int, height: int, padding: tuple = _BLACK) -> Image.Image:
    """Returns `image`, RGBA, without transparency, as an RGB picture `width`
    by `height`: each pixel its own colour, but a wholly transparent one
    black, and the rest `padding`."""
    picture = image.convert("RGB")
    picture.paste(_BLACK, mask=image.getchannel("A").point(lambda alpha: 255 if alpha == 0 else 0))
    padded = Image.new("RGB", (width, height), padding)
    padded.paste(picture)
    return padded


def _jpeg(picture: Image.Image, quality: int) -> bytes:
    """Returns the baseline JPEG file of `picture`, RGB, at `quality` on the
    IJG's scale, its colour at half the width and height, with the
    standard's Huffman tables: as the Editor, VideoBox, and PictureBox write
    their pictures."""
    out = io.BytesIO()
    picture.save(out, "JPEG", quality=quality, subsampling=2, optimize=False, progressive=False)
    return out.getvalue()


def _frames_file(magic: bytes, kind: int, width: int, height: int, frames: list, run: int,
                 unknown: int) -> bytes:
    """Returns an animation's or a video's file of `frames` [(data, duration
    in ms)], a run lasting `run` ms, `unknown` being the header's word at
    +48, 256 in an animation's file and 0 in a video's."""
    entries, place, start = [], _ENTRY_SIZE * len(frames), 0
    for data, duration in frames:
        entries.append(struct.pack("<IIIHHIIII8x", kind, 0, place, width, height, len(data), 0,
                                   duration, start))
        place += len(data)
        start += duration
    if place + _CLOSING_SIZE > 0xFFFFFFFF:
        raise NxwrightError("the file would be larger than its sizes can say, 4 GB")
    body = b"".join(entries) + b"".join(data for data, _ in frames)
    header = struct.pack("<8sIIHHIIIIIIII24x", magic, _HEADER_SIZE, len(frames), width, height,
                         0, len(body) + _CLOSING_SIZE, 0, 0, run, len(body), _CLOSING_SIZE,
                         unknown)
    return header + body + _CLOSING


def _entries(data: bytes) -> tuple:
    """Returns (width, height, [(place, size, duration)]) of an animation's
    or a video's header and frame entries, each place from the file's start."""
    if len(data) < 20:
        raise NxwrightError("the file is shorter than its header")
    header_size, count = struct.unpack_from("<II", data, 8)
    width, height = struct.unpack_from("<HH", data, 16)
    if header_size + _ENTRY_SIZE * count > len(data):
        raise NxwrightError("the file is shorter than its %d frame entries" % count)
    entries = []
    for number in range(count):
        entry = header_size + _ENTRY_SIZE * number
        place, = struct.unpack_from("<I", data, entry + 8)
        size, = struct.unpack_from("<I", data, entry + 16)
        duration, = struct.unpack_from("<I", data, entry + 24)
        entries.append((header_size + place, size, duration))
    return width, height, entries


def _picture(data: bytes, number: int, start: int, size: int) -> bytes:
    """Returns frame `number`'s JPEG picture, `size` bytes from `start`."""
    if size < len(_JPEG_START) or start + size > len(data):
        raise NxwrightError("frame %d lies outside the file" % number)
    picture = data[start:start + size]
    if not picture.startswith(_JPEG_START):
        raise NxwrightError("frame %d holds no JPEG picture" % number)
    return picture
