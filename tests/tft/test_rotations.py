"""A project's rotation (tft/packaging.py and
tft/frame.py): the fixtures the probes of rotation_probes.py
kept once they matched the Nextion Editor's file, the rotation header 1
gives, and what the rules take at each rotation.

Each test gives the function it checks its own input: a probe's page made
in memory at its rotation, in a Project of the facts it reads, and each
component's place, read from the probe's table (tests/tft/unit_inputs.py).
The probe that keeps fixtures is compared whole in tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.tft import frame, packaging
from tools.tft.probing import rotation_probes
from nxwright.tft.matching import Need, project_needs, unmatched
from nxwright.tft.packaging import Firmware, package
from nxwright.tft.tft_file import firmware_names
from tests.tft.made_tft import made_user_code
from tests.tft.t_components import FillStartAndLoadPieces, TypePieces
from tests.tft.unit_inputs import page, project_of


class PiecesTest(TypePieces, FillStartAndLoadPieces, unittest.TestCase):
    """Each component of the probe at 90 degrees that keeps its whole user
    code, of every type, at its type's functions, against the probe's
    pieces: its memory, its drawing, its entries, its background fill, its
    events' start, and its blocks in the load section, on its page made in
    memory at that rotation (tests/tft/t_components.py)."""

    PROBES = rotation_probes.PROBES
    COUNT = 19
    FILL_COUNT = 17
    START_COUNT = 9
    LOAD_COUNT = 3


class HeaderTest(unittest.TestCase):

    def test_header_1_gives_the_rotation(self):
        # Its byte 0x14: 0 to 3, for 0, 90, 180, and 270 degrees.
        firmware = Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names("T")})
        for degrees, code in ((90, 1), (180, 2), (270, 3)):
            with self.subTest(degrees=degrees):
                project = project_of(page(rotation=degrees), rotation=degrees, fonts=0)
                self.assertEqual(project.settings.rotation, degrees)
                self.assertEqual(package(project, made_user_code(), firmware)[0x14], code)


class RulesTest(unittest.TestCase):
    """The rules take each rotation, and the page's size and a component's
    place on the screen as the screen is at the project's rotation."""

    @staticmethod
    def page(name: str, value: int, series: str, rotation: int) -> Need:
        return Need("attribute", "page." + name, value.to_bytes(2, "little"), series=series,
                    rotation=rotation)

    def test_each_rotation(self):
        covered = [Need("rotation", str(degrees)) for degrees in (0, 90, 180, 270)]
        self.assertEqual(unmatched(covered, packaging.MATCHED), [])
        left = [Need("rotation", "45")]
        self.assertEqual(unmatched(left, packaging.MATCHED), left)

    def test_the_page_s_size(self):
        covered = [self.page("w", 480, "T", 90), self.page("h", 320, "T", 90),
                   self.page("w", 320, "K", 180), self.page("h", 480, "K", 180),
                   self.page("w", 480, "P", 270), self.page("h", 800, "P", 270)]
        self.assertEqual(unmatched(covered, frame.MATCHED), [])
        # A page of another size than the screen's at the rotation, which the
        # Nextion Editor writes at the screen's.
        covered = [self.page("w", 320, "T", 90), self.page("h", 480, "T", 270),
                   self.page("w", 480, "T", 0), self.page("h", 320, "K", 180),
                   self.page("w", 2001, "T", 90), self.page("h", 1, "K", 180)]
        self.assertEqual(unmatched(covered, frame.MATCHED), [])

    def test_every_need_gives_the_rotation(self):
        project = project_of(page(rotation=270), rotation=270, fonts=0)
        self.assertEqual({need.rotation for need in project_needs(project)}, {270})


if __name__ == "__main__":
    unittest.main()
