"""Finds the line of a TOML file's text that an error is about, for the
error's place (nxwright.place_text): the line that gives a key, the header
of a table, or the line where Python's TOML reader stopped. Keys and headers
are found by reading the text line by line, without parsing it, so a line
inside a multi-line string can be taken for a key of the file."""
import re
import tomllib

# A TOML line `key = value`, of a page file or of app.toml: its key, then
# its value.
KEY_LINE = re.compile(r"\s*([A-Za-z0-9_]+)\s*=(.*)")
# The start of a table's header, such as "[page]" or "[[component]]".
_TABLE_HEADER = re.compile(r"\s*\[")
# The part of a TOML error's text that gives the line where the reader
# stopped, such as "(at line 2, column 10)".
_ERROR_LINE = re.compile(r"\(at line (\d+), column \d+\)")


def key_line(text: str, key: str, table: str = None) -> int:
    """Returns the line, counted from 1, where the TOML text `text` gives
    `key`. Without `table`, the key must be at the top level. With `table`,
    a table's name such as "mcu", the key must be in that table. Returns 0
    when no line gives the key."""
    current = None
    for number, line in enumerate(text.split("\n"), start=1):
        if _TABLE_HEADER.match(line):
            # A header may end with a comment, as in "[page]  # main".
            current = line.split("#", 1)[0].strip().strip("[]").strip()
        elif current == table:
            found = KEY_LINE.match(line)
            if found and found[1] == key:
                return number
    return 0


def table_line(text: str, table: int) -> int:
    """Returns the line, from 1, of the header of a table of the TOML text
    `text`. `table` is the table's number, counted from 0 in the order of
    the headers. Returns 0 when the text has fewer tables."""
    headers = [number for number, line in enumerate(text.split("\n"), start=1)
               if _TABLE_HEADER.match(line)]
    return headers[table] if table < len(headers) else 0


def error_line(error: tomllib.TOMLDecodeError):
    """Returns the line, from 1, where Python's TOML reader stopped with
    `error`, read from the error's text. Returns None when the text gives no
    line, which happens for an error at the end of the file."""
    found = _ERROR_LINE.search(str(error))
    return int(found[1]) if found else None
