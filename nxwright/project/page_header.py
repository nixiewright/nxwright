"""The two fields of a page block's header that are not its size, count, or
name: bytes 16 to 23 and 40 to 55 (see page_block.py for the layout).

Worked out from files the Editor saved, 208 pages in all, and from pages the
user locked and unlocked in the Editor:
  +16..19  the password of the page's lock, as password_hash gives it
           (device_settings.py), the same hash as the project's password;
           zero for none
  +20      1 while the page is locked, 0 otherwise. The Editor will not let
           a locked page be changed, and adds its stock keyboards locked.
  +21..22  4f 21 on every page
  +23      0 for an ordinary page, or the Editor's system page it is
           (SYSTEM_PAGES). The Editor shows those with their own icon, and
           can reset one to its stock version; a project may change them.
  +40..43  01 44 02 and the project's character encoding, as the Editor
           writes them whenever it writes a page. A page it has not written
           since it was updated holds an older form, 01 43 01 00.
  +44..55  zero on every page
"""
from dataclasses import dataclass

from nxwright import NxwrightError
from nxwright.project.page_block import PageBlock

# Byte 23 of the system pages, by the name a page file gives them: the stock
# keyboards the Editor adds for a component's `key`, whose value is the same
# number. The Editor offers them as "full qwerty" (keybdA), "numeric
# keyboard" (keybdB), "speed dial" (keybdC), and "Chinese input" (keybdAP).
SYSTEM_PAGES = {"keyboard": 1, "keypad": 2, "speed-dial": 3, "chinese-input": 4}
# Bytes 16 to 19 of a page whose lock has no password.
NO_LOCK_PASSWORD = bytes(4)
_HEADER_21 = bytes.fromhex("4f21")
_HEADER_40_START = bytes.fromhex("014402")
_OLDER_HEADER_40_START = bytes.fromhex("01430100")
_HEADER_40_END = bytes(12)


@dataclass(frozen=True)
class PageHeader:
    """What a page's header bytes 16 to 23 say: the system page it is, a
    name of SYSTEM_PAGES, or None; whether it is locked; and its lock's
    password, as 4 bytes of password_hash, or NO_LOCK_PASSWORD."""
    system_page: str = None
    locked: bool = False
    lock_password_hash: bytes = NO_LOCK_PASSWORD


def header_16(header: PageHeader) -> bytes:
    """Returns the header bytes 16 to 23 of a page."""
    return (header.lock_password_hash + bytes([int(header.locked)]) + _HEADER_21
            + bytes([SYSTEM_PAGES.get(header.system_page, 0)]))


def header_40(encoding_code: int) -> bytes:
    """Returns the header bytes 40 to 55 of a page in a project whose
    encoding has the number `encoding_code`."""
    return _HEADER_40_START + bytes([encoding_code]) + _HEADER_40_END


def page_header_of(page: PageBlock) -> PageHeader:
    """Returns what `page`'s header says. Raises NxwrightError when its header
    is not one of the forms the Editor was seen to write, since a page file
    could not keep it."""
    marks = {number: name for name, number in SYSTEM_PAGES.items()}
    field_16, field_40 = page.unknown_16, page.unknown_40
    known_16 = field_16[4] in (0, 1) and field_16[5:7] == _HEADER_21 and field_16[7] in (0, *marks)
    known_40 = (field_40[:3] == _HEADER_40_START or field_40[:4] == _OLDER_HEADER_40_START) \
        and field_40[4:] == _HEADER_40_END
    if not (known_16 and known_40):
        raise NxwrightError("page %s: its header (%s, %s) is not one nxwright knows, so a page "
                            "file cannot keep it" % (page.name, field_16.hex(), field_40.hex()))
    return PageHeader(marks.get(field_16[7]), bool(field_16[4]), bytes(field_16[:4]))
