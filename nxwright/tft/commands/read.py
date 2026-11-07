"""split a TFT file into its parts, and check its checksums, sizes, and places

  nxwright tft-read <file.tft>

Prints the file's series, its Nextion Editor's version, its section's table,
and its user code's parts and pages, then each checksum, size, or place that
does not hold. Exits with 1 when one does not.
"""
import argparse
from pathlib import Path
import sys

from nxwright.tft.tft_file import TftFileError, read_tft


def main(arguments: list) -> int:
    parser = argparse.ArgumentParser(prog="nxwright tft-read",
                                     description="Splits a TFT file into its parts, and checks "
                                     "its checksums, sizes, and places.")
    parser.add_argument("file", type=Path)
    options = parser.parse_args(arguments)
    try:
        tft = read_tft(options.file.read_bytes(), str(options.file), check=False)
    except (OSError, TftFileError) as error:
        print("nxwright tft-read: %s" % error, file=sys.stderr)
        return 1
    print("\n".join(describe(tft)))
    return 1 if tft.problems else 0


def describe(tft) -> list:
    """Returns the lines that describe `tft`'s parts, then its problems."""
    lines = ["%s: %d bytes, series %s, written by the Nextion Editor %d.%d.%d" % (
        tft.where, len(tft.data), tft.series, *tft.version),
        "section at 0x%x, user code at 0x%x" % (tft.section_place, tft.user_code_place)]
    for number, row in enumerate(tft.table):
        if row.place or row.size:
            lines.append("  row %d, %s: at 0x%x, %d bytes" % (number, row.name, row.place,
                                                              row.size))
    code = tft.user_code
    if code is None:
        lines.append("user code: %d bytes, not split, as header 2 cannot be read"
                     % len(tft.user_code_bytes))
    else:
        lines.append("user code: %d bytes" % len(tft.user_code_bytes))
        for name, (start, end) in code.places().items():
            lines.append("  %s: 0x%x to 0x%x" % (name, start, end))
        parts = code.block_parts()
        for part in dict.fromkeys(parts):
            lines.append("  %s: %d blocks" % (part, parts.count(part)))
    lines.extend("problem: %s" % problem for problem in tft.problems)
    if not tft.problems:
        lines.append("every checksum, size, and place holds")
    return lines
