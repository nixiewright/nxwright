"""The E series (tools/tft/probing/e_probes.py): its probes that keep fixtures,
and the fields of header 1 that differ from P's.

The header test gives the compile its own input: a Project of the facts of
the E base folder's page, made in memory, without resources
(tests/tft/unit_inputs.py). E's probes that keep fixtures are whole compiles, of
a blank project and of three pages, which read the blocks of a project's
resources that only a whole build has. They are compared whole, as E's
sample, in tests/tft/test_whole_files.py, where the compile runs the match check
on both. test_series_followers.py gives E P's coverage: P's unit tests
on E's series, against P's pieces as E's table of differences changes
them.
"""
import struct
import unittest

from tools.tft.probing import e_probes
from nxwright.tft.commands.compile import compile_project
from nxwright.tft.firmware import firmware_from_tft
from nxwright.tft.tft_file import read_tft
from tests.tft.made_tft import made_tft
from tests.tft.unit_inputs import page, project_of


class FixtureTest(unittest.TestCase):

    def test_the_probes_that_keep_fixtures(self):
        # The whole compiles of E's sample (tests/tft/test_whole_files.py).
        self.assertEqual({probe.name for probe in e_probes.PROBES if probe.fixtures}, {
            "e-compile-T-blank",
            "e-compile-T-pages-ints-code",
        })


class AsOnPTest(unittest.TestCase):

    def test_header_1(self):
        # The series' code, 6, and the screen, 480 by 480.
        project = project_of(page(series="E"), series="E", fonts=0)
        data = compile_project(project, firmware_from_tft(made_tft("E"), "made.tft", "E"))
        self.assertEqual(data[0x15], 6)
        self.assertEqual(struct.unpack_from("<4H", data, 0x0C), (480, 480, 480, 480))
        self.assertEqual(read_tft(data, "nxwright's file").series, "E")


if __name__ == "__main__":
    unittest.main()
