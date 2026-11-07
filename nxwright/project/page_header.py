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
           since it was updated has an older form, 01 43 01 00 or
           01 44 01 00. In one project for an NSPanel screen, 32 of the 38
           pages had 01 44 01 00, and the other 6 had the newer form.
  +44..55  zero on every page

When bytes 16 to 23 have a value that was not seen in those files, nxwright
keeps the value in its own field, and the build writes it back. A system
page mark or a lock value is kept as its number, and bytes 21 and 22 are
kept as they are. Like the Editor, the build writes bytes 40 to 55 in the
current form, whatever the page had. The finder of unknown content
(source/unknown_content.py) reports each value that was not seen.
"""
from dataclasses import dataclass, replace

from nxwright.project.page_block import PageBlock

# Byte 23 of the system pages, by the name a page file gives them: the stock
# keyboards the Editor adds for a component's `key`, whose value is the same
# number. The Editor offers them as "full qwerty" (keybdA), "numeric
# keyboard" (keybdB), "speed dial" (keybdC), and "Chinese input" (keybdAP).
SYSTEM_PAGES = {"keyboard": 1, "keypad": 2, "speed-dial": 3, "chinese-input": 4}
# Bytes 16 to 19 of a page whose lock has no password.
NO_LOCK_PASSWORD = bytes(4)
# Bytes 21 and 22, the same on every page seen.
HEADER_21 = bytes.fromhex("4f21")
_HEADER_40_START = bytes.fromhex("014402")
_OLDER_HEADER_40_STARTS = (bytes.fromhex("01430100"), bytes.fromhex("01440100"))
_HEADER_40_END = bytes(12)


@dataclass(frozen=True)
class PageHeader:
    """What a page's header bytes 16 to 23 say: the system page it is, a
    name of SYSTEM_PAGES or the number of an unknown mark, or None for an
    ordinary page; whether the page is locked, or the number of a lock value
    other than 0 and 1; the password of the page's lock, as 4 bytes of
    password_hash, or NO_LOCK_PASSWORD; and the page's bytes 21 and 22."""
    system_page: object = None
    locked: object = False
    lock_password_hash: bytes = NO_LOCK_PASSWORD
    header_21: bytes = HEADER_21


def header_16(header: PageHeader) -> bytes:
    """Returns the header bytes 16 to 23 of a page."""
    mark = SYSTEM_PAGES.get(header.system_page, header.system_page or 0)
    return (header.lock_password_hash + bytes([int(header.locked)]) + header.header_21
            + bytes([mark]))


def header_40(encoding_code: int) -> bytes:
    """Returns the header bytes 40 to 55 of a page in a project whose
    encoding has the number `encoding_code`."""
    return _HEADER_40_START + bytes([encoding_code]) + _HEADER_40_END


def header_40_form_known(field_40: bytes) -> bool:
    """Returns whether a page's header bytes 40 to 43, the start of
    `field_40`, are in a form that the Editor was seen to write."""
    return field_40[:3] == _HEADER_40_START or field_40[:4] in _OLDER_HEADER_40_STARTS


def header_44_known(field_40: bytes) -> bool:
    """Returns whether a page's header bytes 44 to 55, the rest of
    `field_40`, are all zero, as on every page seen."""
    return field_40[4:] == _HEADER_40_END


def page_header_of(page: PageBlock) -> PageHeader:
    """Returns the PageHeader of `page`, from its header bytes 16 to 23.
    Values that were not seen are kept too."""
    marks = {number: name for name, number in SYSTEM_PAGES.items()}
    field_16 = page.unknown_16
    mark, lock = field_16[7], field_16[4]
    return PageHeader(marks.get(mark, mark or None), bool(lock) if lock in (0, 1) else lock,
                      bytes(field_16[:4]), bytes(field_16[5:7]))


def with_lock(page: PageBlock) -> PageBlock:
    """Returns `page` locked, with no password. A page that is locked, or has
    any other lock value, stays as it is. So does a page with a password,
    even if it is unlocked, since locking it would bring back a password the
    user may have forgotten."""
    header = page_header_of(page)
    if header.locked or header.lock_password_hash != NO_LOCK_PASSWORD:
        return page
    return replace(page, unknown_16=header_16(replace(header, locked=True)))
