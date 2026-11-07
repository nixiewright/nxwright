"""show where two TFT files first differ, part by part

  nxwright tft-compare <a.tft> <b.tft>

Prints, for each part of the file where the two differ, the piece where they
first differ, such as a header field or a block of the user code, with the
bytes around it. Exits with 1 when they differ. A file whose checksums do not
hold is still compared.
"""
import argparse
from pathlib import Path
import sys

from nxwright.tft.comparison import differences, report
from nxwright.tft.tft_file import TftFileError, read_tft


def main(arguments: list) -> int:
    parser = argparse.ArgumentParser(prog="nxwright tft-compare",
                                     description="Shows where two TFT files first differ, part "
                                     "by part.")
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    options = parser.parse_args(arguments)
    try:
        a, b = (read_tft(path.read_bytes(), str(path), check=False)
                for path in (options.a, options.b))
    except (OSError, TftFileError) as error:
        print("nxwright tft-compare: %s" % error, file=sys.stderr)
        return 1
    print(report(a, b))
    return 1 if differences(a, b) else 0
