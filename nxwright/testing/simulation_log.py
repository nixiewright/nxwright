"""The simulator's log (simulation.py): how each entry of a record of what
reached outside the screen reads, with the bytes the screen sends as the
vendor documents them."""
from nxwright import NxwrightError
from nxwright.project.device_settings import TextCodec


# The three bytes that end what the screen sends.
END = bytes([0xff, 0xff, 0xff])


# How the log may show the bytes the screen receives or sends: as text, in
# hexadecimal, or both.
LOG_FORMATS = ("text", "hex", "both")


def hex_bytes(data: bytes) -> str:
    return " ".join("%02x" % byte for byte in data)


def log_format(value, setting: str) -> str:
    """Returns `value`, one of LOG_FORMATS, as a launch configuration's
    `setting` gives it. Raises NxwrightError, saying why, for another."""
    if value not in LOG_FORMATS:
        raise NxwrightError("%s must be text, hex, or both, not %r" % (setting, value))
    return value


def shown(data: bytes, form: str, encoding: str) -> str:
    """Returns bytes the screen received or sent as the log shows them, in
    the form `form`: "hex", each byte as two hexadecimal digits; "text",
    read in `encoding`, the FF FF FF that ends an instruction or a reply left
    out, and a byte that is no character written as \\xNN; "both", the
    text, then the hexadecimal in brackets."""
    if form == "hex":
        return hex_bytes(data)
    body = data[:-len(END)] if data.endswith(END) else data
    text = "".join(_shown_character(character)
                   for character in TextCodec(encoding).decode_keeping_bytes(body))
    return text if form == "text" else "%s (%s)" % (text, hex_bytes(data))


def _shown_character(character: str) -> str:
    """A character of a text the log shows: a byte the encoding cannot read,
    which decoding kept as a lone surrogate, or a control character, as
    \\xNN; any other as it is."""
    code = ord(character)
    if 0xDC80 <= code <= 0xDCFF:
        return "\\x%02x" % (code - 0xDC00)
    if code < 0x20 or code == 0x7F:
        return "\\x%02x" % code
    return character


def value_bytes(value, length: int, encoding: str) -> bytes:
    """Returns the bytes `prints value,length` sends: a text's bytes, or a
    number's 4 bytes, low byte first; a length other than 0 keeps that many."""
    if isinstance(value, str):
        data = TextCodec(encoding).encode_keeping_bytes(value, "the text")
    else:
        data = (value % 2 ** 32).to_bytes(4, "little")
    return data[:length] if length else data


def sent_bytes(entry: tuple, encoding: str) -> bytes:
    """Returns the bytes an entry of "sent" sends: prints's and print's
    (value, length), printh's ("printh", hexadecimal text), or rdfile's
    ("rdfile", bytes). Raises NxwrightError for a text `encoding` cannot
    write."""
    if entry[0] == "rdfile" and isinstance(entry[1], bytes):
        return entry[1]
    if entry[0] == "printh" and isinstance(entry[1], str):
        try:
            return bytes.fromhex(entry[1])
        except ValueError:
            raise NxwrightError("printh %s is no hexadecimal" % entry[1]) from None
    return value_bytes(entry[0], entry[1], encoding)


def reply_bytes(entry: tuple, encoding: str) -> bytes:
    """Returns the bytes an entry of "replies" sends, as the vendor documents
    them. Raises NxwrightError for a text `encoding` cannot write."""
    kind, value = entry
    if kind == "get":
        return bytes([0x70 if isinstance(value, str) else 0x71]) + \
            value_bytes(value, 0, encoding) + END
    if kind == "sendme":
        return bytes([0x66, value]) + END
    return bytes(value)


def _sent_line(entry: tuple, encoding: str, form: str = "hex") -> str:
    """printh's hexadecimal shows as it was written, in hexadecimal, and as
    written when it is no hexadecimal."""
    if entry[0] == "printh" and isinstance(entry[1], str):
        if form == "hex":
            return "sends %s" % entry[1]
        try:
            return "sends %s" % shown(sent_bytes(entry, encoding), form, encoding)
        except NxwrightError:
            return "sends %s" % entry[1]
    try:
        return "sends %s" % shown(sent_bytes(entry, encoding), form, encoding)
    except NxwrightError:
        return "sends %r, which %s cannot write" % (entry[0], encoding)


def _reply_line(entry: tuple, encoding: str, form: str = "hex") -> str:
    try:
        return "sends %s (%s)" % (shown(reply_bytes(entry, encoding), form, encoding), entry[0])
    except NxwrightError:
        return "sends %r (%s), which %s cannot write" % (entry[1], entry[0], encoding)


def _eeprom_line(entry: tuple, encoding: str) -> str:
    kind, address, value = entry
    if kind == "wepo":
        return "EEPROM: wrote %s at %d" % (hex_bytes(value), address)
    return "EEPROM: read %r at %d" % (value, address)


def _gpio_line(entry: tuple, encoding: str) -> str:
    if entry[0] == "cfgpio":
        return "GPIO: pin %d set to mode %d, for %s" % entry[1:]
    kind, name, value = entry
    return "GPIO: %s %s %r" % (name, "set to" if kind == "write" else "read as", value)


# The records of what reached outside the screen, each with how to log an
# entry. Those of SENT also take the form the log shows what is sent in.
LOGGED = {
    "sent": _sent_line,
    "replies": _reply_line,
    "eeprom accesses": _eeprom_line,
    "gpio": _gpio_line,
    "file commands": lambda entry, encoding: "SD card: %s" % " ".join(map(str, entry)),
    "file errors": lambda entry, encoding: "SD card: %s of %s refused" % entry,
    "component errors": lambda entry, encoding: "%s %s: no component has that ID" % entry,
    "refusals": lambda entry, encoding: "%s refused, answering %02x" % (entry[1], entry[0]),
    "other commands": lambda entry, encoding: "not simulated: %s" % " ".join(map(str, entry)),
}

# The records of what the screen sends on its serial line, each with how to
# work out an entry's bytes.
SENT = {"sent": sent_bytes, "replies": reply_bytes}
