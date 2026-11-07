"""The comparison of what two TFT files hold (tft/decompiling/compared.py),
which the decompiler's round trip makes: files packaged in memory from
projects of facts (tests/tft/unit_inputs.py), around zeros for the firmware.
"""
import unittest

from nxwright.tft import frame
from nxwright.tft.comparison import differences
from nxwright.tft.decompiling.compared import mismatches
from nxwright.tft.decompiling.decoded_file import read_decoded
from nxwright.tft.packaging import Firmware, package
from tools.tft.probing.button_probes import button_component
from nxwright.tft.tft_file import firmware_names, read_tft
from tests.tft.unit_inputs import page, project_of


def _file(*pages, firmware_size: int = 16):
    """Returns the TFT file of a project of `pages` on T, without fonts,
    around zeros for the firmware, `firmware_size` bytes each file."""
    project = project_of(*pages, fonts=0)
    firmware = Firmware((1, 68, 2), {name: bytes(firmware_size)
                                     for name in firmware_names("T")})
    return read_tft(package(project, frame.user_code(project), firmware), "a file")


def _named(name: str) -> str:
    """Returns a button component named `name`, in a page file's form."""
    component = button_component()
    assert 'name = "b0"' in component
    return component.replace('name = "b0"', 'name = "%s"' % name)


class MismatchesTest(unittest.TestCase):

    def test_two_files_of_one_project(self):
        self.assertEqual(mismatches(_file(page(button_component())),
                                    _file(page(button_component()))), [])

    def test_an_attribute(self):
        # Found at the button's fields, and at the pieces that keep its
        # place byte for byte: its page's data and the records.
        found = mismatches(_file(page(button_component())), _file(page(button_component(x=11))))
        decoded = [each.where for each in found if each.where.startswith("pages")]
        self.assertTrue(decoded)
        self.assertTrue(all(where.startswith("pages[0].objects[1].") for where in decoded),
                        decoded)
        self.assertEqual(sorted(each.where for each in found if not each.where.startswith("pages")),
                         ["user code, page 0's data", "user code, records"])

    def test_a_name_by_its_text(self):
        # The file keeps a name only as its checksum. A name no guess
        # matches is read back as a readable name, so a file built again
        # with that name holds the same, though its bytes differ.
        original = _file(page(_named("custom")))
        readable = read_decoded(original).pages[0].objects[1].name
        self.assertFalse(readable.matched)
        again = _file(page(_named(readable.text)))
        self.assertTrue(differences(original, again))
        self.assertEqual(mismatches(original, again), [])

    def test_another_name(self):
        found = mismatches(_file(page(_named("b0"))), _file(page(_named("b1"))))
        self.assertEqual([(each.where, each.original, each.again) for each in found],
                         [("pages[0].objects[1].name", "b0", "b1")])

    def test_outside_the_user_code(self):
        # The firmware's files differ in size, so do the section, its table,
        # and the headers that give their places, byte for byte.
        found = mismatches(_file(page()), _file(page(), firmware_size=17))
        self.assertTrue(found)
        self.assertTrue(all(not each.where.startswith("pages") for each in found))
        self.assertIn("the section's table", {each.where.split(",", 1)[0] for each in found})

    def test_a_page_more(self):
        found = mismatches(_file(page()), _file(page(), page(name="page1")))
        self.assertIn("pages, its length", [each.where for each in found])


if __name__ == "__main__":
    unittest.main()
