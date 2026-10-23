"""The screen's pinyin table, which its two pinyin commands read, pa_q and
pa_txt (editor_machine.py): the candidate characters of each pinyin
syllable, in gb2312.

The screen keeps the table in its firmware. The Nextion Editor's
installation folder holds it as input.bin, and every TFT file holds a copy,
the first of its firmware parts. It is the vendor's, so nxwright never
ships it: a simulation or a test reads the user's own copy
(read_pinyin_table).

The table starts with a row of 8 bytes for each syllable, then the
candidates of every syllable, two bytes each, back to back. A row holds
four 2-byte values, low byte first:
  - in row 0, the number of rows; in the others, how many bytes the
    previous row's candidates take;
  - the syllable's key, its low half then its high half;
  - the place in the table where the syllable's candidates start. They run
    to the next row's place, or to the table's end.
The key is the stamp CRC of the syllable's bytes, each byte fed as a word
(stamp.word_crc from stamp.CRC_START). The rows go by increasing key. Worked
out from the Nextion Editor 3.1.73's input.bin.

In a TFT file, the firmware part starts at the section size, which bytes
0x34 to 0x37 of the file give. It starts with a table of rows of three
4-byte values, a place and a size, then 0; its first row gives the pinyin
table's place, 0x90 from the part's start, and its size.
"""
from pathlib import Path
import struct
import sys

from nxwright import NxwrightError
from nxwright.project.stamp import CRC_START, word_crc

_ROW = struct.Struct("<HHHH")
# In a TFT file: where the section size is, and where the firmware part's
# first row places the pinyin table, from the part's start.
_SECTION_SIZE_PLACE = 0x34
_FIRMWARE_TABLE_PLACE = 0x90
# The uninstall entries where the Nextion Editor's installer records its
# folder, on 64-bit Windows and on 32-bit Windows.
_UNINSTALL_KEYS = (r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                   r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
_TABLE_FILE = "input.bin"


class PinyinTable:
    """A pinyin table, `data`, as the screen keeps it (the module's
    docstring). `where` says where it came from, for messages."""

    def __init__(self, data: bytes, where: str):
        self.data = bytes(data)
        self._places = _places(self.data, where)

    def place(self, syllable: bytes):
        """Returns (start, end), the place in `data` of the candidates of
        `syllable`, its bytes matched exactly; or None for a syllable the
        table lacks."""
        return self._places.get(word_crc(CRC_START, syllable))


def _places(data: bytes, where: str) -> dict:
    """Returns {key: (start, end)} of each row of the table `data`. Raises
    NxwrightError, starting with `where`, for data that is no pinyin table."""
    if len(data) < _ROW.size:
        raise NxwrightError("%s is too short to be a pinyin table" % where)
    count = _ROW.unpack_from(data)[0]
    if count == 0:
        raise NxwrightError("%s is no pinyin table: it holds no rows" % where)
    if count * _ROW.size > len(data):
        raise NxwrightError("%s is no pinyin table: its %d rows run past its end" % (where, count))
    rows = [_ROW.unpack_from(data, index * _ROW.size) for index in range(count)]
    keys = [high << 16 | low for _, low, high, _ in rows]
    if any(later <= earlier for earlier, later in zip(keys, keys[1:])):
        raise NxwrightError("%s is no pinyin table: its rows are not in the order of their keys"
                            % where)
    starts = [row[3] for row in rows] + [len(data)]
    if starts[0] < count * _ROW.size:
        raise NxwrightError("%s is no pinyin table: its candidates start among its rows" % where)
    for index in range(1, count + 1):
        if starts[index] < starts[index - 1]:
            raise NxwrightError("%s is no pinyin table: row %d's candidates start before row "
                                "%d's" % (where, index, index - 1)
                                if index < count else
                                "%s is no pinyin table: its last row's candidates start past "
                                "its end" % where)
    return {key: (starts[index], starts[index + 1]) for index, key in enumerate(keys)}


def read_pinyin_table(path: Path) -> PinyinTable:
    """Returns the pinyin table of the file `path`: input.bin, as the Nextion
    Editor's installation folder holds it, or a TFT file (a name ending in
    .tft), whose firmware part holds a copy. Raises NxwrightError for a file
    that cannot be read, or that holds no pinyin table."""
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as error:
        raise NxwrightError("the pinyin table %s cannot be read: %s"
                            % (path, error.strerror or error)) from None
    if path.suffix.lower() == ".tft":
        data = _tft_table(data, str(path))
    return PinyinTable(data, str(path))


def _tft_table(data: bytes, where: str) -> bytes:
    """Returns the pinyin table a TFT file's bytes, `data`, hold (the module's
    docstring). Raises NxwrightError for a file whose firmware part does not
    start with one."""
    refusal = NxwrightError("%s holds no pinyin table where a TFT file holds one" % where)
    if len(data) < _SECTION_SIZE_PLACE + 4:
        raise refusal
    section = struct.unpack_from("<I", data, _SECTION_SIZE_PLACE)[0]
    if section + 12 > len(data):
        raise refusal
    place, size, _ = struct.unpack_from("<III", data, section)
    start = section + place
    if place != _FIRMWARE_TABLE_PLACE or size == 0 or start + size > len(data):
        raise refusal
    return data[start:start + size]


def pinyin_table_of(table):
    """Returns the PinyinTable `table` gives: a PinyinTable, a path to read
    (read_pinyin_table), or None for none."""
    if table is None or isinstance(table, PinyinTable):
        return table
    return read_pinyin_table(Path(table))


def installed_pinyin_table():
    """Returns the path of input.bin in the installed Nextion Editor's
    folder, or None: elsewhere than on Windows, without the Nextion Editor,
    or without the file."""
    folder = _installed_editor_folder()
    if folder is None or not (folder / _TABLE_FILE).is_file():
        return None
    return folder / _TABLE_FILE


def _installed_editor_folder():
    """The folder the Nextion Editor's installer recorded in the registry, or
    None, as on another system than Windows."""
    if sys.platform != "win32":
        return None
    import winreg
    for key_path in _UNINSTALL_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    # An entry that cannot be read is another program's:
                    # the search goes on past it.
                    try:
                        with winreg.OpenKey(key, winreg.EnumKey(key, index)) as entry:
                            if winreg.QueryValueEx(entry, "DisplayName")[0] != "Nextion Editor":
                                continue
                            folder = winreg.QueryValueEx(entry, "InstallLocation")[0]
                    except OSError:
                        continue
                    # An empty folder would be the current one.
                    if folder:
                        return Path(folder)
        except OSError:
            continue
    return None
