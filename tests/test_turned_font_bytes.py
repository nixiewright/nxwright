"""Every font of the repository's fixtures and examples, turned to each
rotation, gives the bytes it gave when fixtures/fonts/turned-font-hashes.json
was recorded. The file gives the SHA-256 of each font turned to 0, 90, 180,
and 270 degrees, so that a change to how fonts are decoded, turned, or coded
cannot change a byte unseen.

A change that is meant to change those bytes records the file again:
`python -m tests.test_turned_font_bytes --record`."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest

from nxwright.project.container import HmiContainer
from nxwright.project.zi_font import turned_font

NXWRIGHT = Path(__file__).resolve().parent.parent
HASHES = NXWRIGHT / "tests" / "fixtures" / "fonts" / "turned-font-hashes.json"
ROTATIONS = (0, 90, 180, 270)
# The example's project file, whose font blocks are checked too.
PROJECT = NXWRIGHT / "examples" / "thermostat" / "thermostat.HMI"


def repository_fonts() -> dict:
    """Returns {name: font block} of every font of the fixtures and the
    examples: the .zi files, the .zi.gz files decompressed, and the font
    blocks of the example's project file, named by its path and the block's
    name."""
    fonts = {}
    for folder in (NXWRIGHT / "tests" / "fixtures", NXWRIGHT / "examples"):
        for path in sorted(folder.rglob("*.zi")) + sorted(folder.rglob("*.zi.gz")):
            data = path.read_bytes()
            fonts[path.relative_to(NXWRIGHT).as_posix()] = (
                gzip.decompress(data) if path.suffix == ".gz" else data)
    for name, block in sorted(HmiContainer.from_file(PROJECT).blocks.items()):
        if name.endswith(".zi"):
            fonts["%s %s" % (PROJECT.relative_to(NXWRIGHT).as_posix(), name)] = block
    return fonts


def turned_hashes(block: bytes) -> dict:
    """Returns {rotation: SHA-256} of the font `block` turned to each
    rotation, the rotation as text, as the file gives it."""
    return {str(rotation): hashlib.sha256(turned_font(block, rotation)).hexdigest()
            for rotation in ROTATIONS}


class TurnedFontBytesTest(unittest.TestCase):

    def test_each_font_gives_the_bytes_recorded(self):
        recorded = json.loads(HASHES.read_text(encoding="utf-8"))
        fonts = repository_fonts()
        self.assertEqual(sorted(fonts), sorted(recorded))
        for name, block in fonts.items():
            with self.subTest(font=name):
                self.assertEqual(turned_hashes(block), recorded[name])


if __name__ == "__main__":
    if sys.argv[1:] == ["--record"]:
        HASHES.write_text(json.dumps({name: turned_hashes(block)
                                      for name, block in repository_fonts().items()},
                                     indent=2) + "\n", encoding="utf-8", newline="\n")
    else:
        unittest.main()
