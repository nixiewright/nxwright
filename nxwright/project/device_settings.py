"""The Editor's device settings, which a project keeps in its manifest header.

Manifest header bytes, all numbers little-endian:
  +11       series (screen_models.py)
  +12       rotation, in quarter turns
  +13       character encoding (ENCODINGS); each page block repeats it at +43
  +15       1 when "one time update of TFT files" is on
  +16..19   device ID: the screen model (screen_models.py)
  +20..23   the password, as its CRC (password_hash); zero when there is no
            password
  +32..35   memory file storage size, in bytes
  +38       1 when "ignore library resources at compile time" is on
  +39       1 when "ignore image resources at compile time" is on
The other header bytes (manifest_header gives their values) were the same in
every project the Editor saved, whatever its model or settings, apart from the
stamp, the header size, the table offset, and the resource count.

The two "one time update" and "memory file storage size" settings exist only
for the Intelligent (P) and Edge (E) series in the Editor.
"""
from dataclasses import dataclass
import struct

from nxwright import NxwrightError
from nxwright.project.screen_models import ScreenModel, model_with_id
from nxwright.project.stamp import CRC_START, word_crc

HEADER_SIZE = 96
# Manifest byte 13 by encoding.
ENCODINGS = {
    1: "ascii", 2: "gb2312", 3: "iso-8859-1", 4: "iso-8859-2", 5: "iso-8859-3",
    6: "iso-8859-4", 7: "iso-8859-5", 8: "iso-8859-6", 9: "iso-8859-7", 10: "iso-8859-8",
    11: "iso-8859-9", 12: "iso-8859-13", 13: "iso-8859-15", 14: "iso-8859-11",
    15: "ks_c_5601-1987", 16: "big5", 17: "windows-1255", 18: "windows-1256",
    19: "windows-1257", 20: "windows-1258", 21: "windows-874", 22: "koi8-r",
    23: "shift-jis", 24: "utf-8",
}
_ENCODING_CODES = {name: code for code, name in ENCODINGS.items()}
NO_PASSWORD = bytes(4)
# The encoding the Editor gives a new project.
DEFAULT_ENCODING = "iso-8859-1"


@dataclass(frozen=True)
class DeviceSettings:
    """The device settings of one project. `rotation` is in degrees (0, 90,
    180, or 270); `encoding` is a name of ENCODINGS; `password_hash` is the
    stored 4-byte value."""
    model: ScreenModel
    rotation: int
    encoding: str
    one_time_update: bool = False
    memory_file_storage_size: int = 0
    ignore_library_resources: bool = False
    ignore_image_resources: bool = False
    password_hash: bytes = NO_PASSWORD

    @property
    def page_size(self) -> tuple:
        """The (width, height) of a page, in pixels: the model's, swapped when
        the screen is turned 90 or 270 degrees."""
        width, height = self.model.width, self.model.height
        return (height, width) if self.rotation in (90, 270) else (width, height)

    @property
    def screen_copy_layout(self) -> tuple:
        """The (format, rotation) of the screen copies of new pictures
        (screen_copy.py): the model's format, in the pixel order of the
        rotation."""
        return self.model.picture_format, self.rotation


def read_device_settings(header: bytes):
    """Returns the DeviceSettings a manifest header stores, or None when its
    device ID is not a known model. Raises NxwrightError for values a known
    model's header cannot hold."""
    model = model_with_id(header[16:20])
    if model is None:
        return None
    if header[11] != model.series_code:
        raise NxwrightError("the manifest names %s but series %d" % (model.name, header[11]))
    if header[12] > 3:
        raise NxwrightError("the manifest's rotation %d is not 0 to 3" % header[12])
    if header[13] not in ENCODINGS:
        raise NxwrightError("the manifest's character encoding %d is not known" % header[13])
    return DeviceSettings(
        model=model, rotation=header[12] * 90, encoding=ENCODINGS[header[13]],
        one_time_update=bool(header[15]),
        memory_file_storage_size=struct.unpack_from("<I", header, 32)[0],
        ignore_library_resources=bool(header[38]), ignore_image_resources=bool(header[39]),
        password_hash=bytes(header[20:24]))


def manifest_header(settings: DeviceSettings) -> bytes:
    """Returns the manifest header for `settings`, with the stamp and the
    resource count left at zero. Raises NxwrightError for an encoding
    ENCODINGS does not hold."""
    header = bytearray(HEADER_SIZE)
    struct.pack_into("<I", header, 4, HEADER_SIZE)
    header[8:11] = b"\x01\x44\x21"
    header[11] = settings.model.series_code
    header[12] = settings.rotation // 90
    header[13] = encoding_code(settings.encoding)
    header[14] = 0x4f
    header[15] = int(settings.one_time_update)
    header[16:20] = settings.model.device_id
    header[20:24] = settings.password_hash
    struct.pack_into("<I", header, 24, HEADER_SIZE)
    struct.pack_into("<I", header, 32, settings.memory_file_storage_size)
    header[36] = 2
    header[38] = int(settings.ignore_library_resources)
    header[39] = int(settings.ignore_image_resources)
    header[65] = 3
    return bytes(header)


def is_password_hash_text(value) -> bool:
    """Whether `value` is a password's hash as a source folder writes it:
    password_hash's 4 bytes as 8 lower-case hexadecimal digits."""
    return (isinstance(value, str) and len(value) == 8
            and all(char in "0123456789abcdef" for char in value))


def password_hash(password: str) -> bytes:
    """Returns the 4 bytes the Editor stores for the project password
    `password`: the CRC of its checksums (stamp.py) over the password's bytes,
    stored little-endian. Worked out from projects the Editor saved with the
    passwords "abc" and "Password1".

    Raises NxwrightError for an empty password, which the Editor stores as
    NO_PASSWORD, and for a character outside ASCII. The Editor hashes such a
    character in Windows' own code page whatever the project's encoding: "é"
    in a utf-8 project as the byte e9. It then refuses that same password when
    the project is opened, so the project cannot be opened again.
    """
    if not password:
        raise NxwrightError("an empty password is no password: leave password_hash out")
    if not password.isascii():
        raise NxwrightError("the password has a character outside ASCII: the Nextion Editor may "
                            "then refuse it when the project is opened")
    return struct.pack("<I", word_crc(CRC_START, password.encode("ascii")))


class TextCodec:
    """Turns the bytes of a project's texts and code into characters and back,
    in the project's encoding `name`, a name of ENCODINGS.

    The Editor is a .NET program, and its encoding names are .NET's. Four of
    them name a Windows code page larger than Python's codec of that name;
    worked out for gb2312 from a project the Editor saved, from .NET's
    documentation for the other three. One, windows-874, names a codec that
    Python before 3.14 does not know by that name: its own codec is cp874.
    """

    _WINDOWS_CODE_PAGES = {"gb2312": "gbk", "ks_c_5601-1987": "cp949", "big5": "cp950",
                           "shift-jis": "cp932"}
    # The encodings whose own codec Python names otherwise, on every version
    # nxwright supports.
    _OWN_CODECS = {"windows-874": "cp874"}

    def __init__(self, name: str):
        encoding_code(name)
        self.name = name
        self._own_codec = self._OWN_CODECS.get(name, name)
        self._codec = self._WINDOWS_CODE_PAGES.get(name, self._own_codec)

    @property
    def codec_name(self) -> str:
        """The name of Python's codec this encoding's text goes through: its
        Windows code page, as cp950 for big5, or else its own codec."""
        return self._codec

    @property
    def own_codec_name(self) -> str:
        """The name of Python's codec of the encoding itself, as gb2312 for
        gb2312, whose texts go through a larger code page (codec_name)."""
        return self._own_codec

    def decode(self, data: bytes, where: str) -> str:
        """Returns the characters `data` holds. Raises NxwrightError, starting
        with `where`, when they are not text in this encoding, or would not
        encode back to the same bytes: some code pages decode two byte forms
        to one character."""
        try:
            text = data.decode(self._codec)
        except UnicodeDecodeError:
            text = None
        if text is None or text.encode(self._codec) != data:
            raise NxwrightError("%s: the bytes %s are not text in %s that nxwright can keep "
                                "exactly" % (where, data.hex(" "), self.name))
        return text

    def decode_keeping_bytes(self, data: bytes) -> str:
        """Returns the characters `data` holds, keeping each byte that is not
        text in this encoding as a character of its own (Python's
        surrogateescape), so that encode_keeping_bytes gives `data` back. For
        the bytes of a file, which may split a character."""
        return data.decode(self._codec, "surrogateescape")

    def encode_keeping_bytes(self, text: str, where: str) -> bytes:
        """Returns `text` as stored bytes, the reverse of decode_keeping_bytes.
        Raises NxwrightError, starting with `where`, for a character this
        encoding cannot store."""
        try:
            return text.encode(self._codec, "surrogateescape")
        except UnicodeEncodeError as error:
            raise NxwrightError("%s: %s cannot store %r" % (where, self.name,
                                                            error.object[error.start])) from None

    def encode(self, text: str, where: str) -> bytes:
        """Returns `text` as stored bytes. Raises NxwrightError, starting with
        `where`, for a character this encoding cannot store."""
        try:
            return text.encode(self._codec)
        except UnicodeEncodeError as error:
            raise NxwrightError("%s: %s cannot store %r" % (where, self.name,
                                                            error.object[error.start])) from None


def encoding_code(name: str) -> int:
    """Returns manifest byte 13 for the encoding `name`. Raises NxwrightError
    for a name ENCODINGS does not hold."""
    if name not in _ENCODING_CODES:
        raise NxwrightError("unknown character encoding %r; known: %s"
                            % (name, ", ".join(_ENCODING_CODES)))
    return _ENCODING_CODES[name]
