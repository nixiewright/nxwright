"""list what a TFT file's user code holds: its pages, objects, int variables, and code

  nxwright tft-listing <file.tft>

Prints the file's settings, its int variables, program.s's blocks, its
macros, and each page with each of its objects: its type, ID, name,
entries, drawing, and each event's blocks, then the pictures and fonts. A
name no guess matched is marked. Exits with 1 when the file cannot be read.
"""
import argparse
from pathlib import Path
import sys

from nxwright import NxwrightError

from nxwright.tft.decompiling.decoded_file import read_decoded
from nxwright.tft.decompiling.listing import listing_lines
from nxwright.tft.tft_file import read_tft


def main(arguments: list) -> int:
    parser = argparse.ArgumentParser(prog="nxwright tft-listing",
                                     description="Lists what a TFT file's user code holds: "
                                     "its pages, objects, int variables, and code.")
    parser.add_argument("file", type=Path)
    options = parser.parse_args(arguments)
    try:
        decoded = read_decoded(read_tft(options.file.read_bytes(), str(options.file),
                                        check=False))
    except (OSError, NxwrightError) as error:
        print("nxwright tft-listing: %s" % error, file=sys.stderr)
        return 1
    print("\n".join(listing_lines(decoded)))
    return 0
