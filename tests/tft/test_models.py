"""A project's screen model (tft/packaging.py and
tft/frame.py): the fixtures the probes of model_probes.py
kept once they matched the Nextion Editor's file, what header 1 gives of
the model, and what the rules take on each model.

Each test gives the function it checks its own input: a probe's page made
in memory on its model, in a Project of the facts it reads, and each
component's place, read from the probe's table (tests/tft/unit_inputs.py).
The probe that keeps fixtures is compared whole in tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.project.screen_models import MODELS
from nxwright.tft import frame, packaging
from tools.tft.probing import model_probes
from nxwright.tft.component_types import place_fits_its_record
from nxwright.tft.matching import Need, project_needs, unmatched
from nxwright.tft.packaging import Firmware, package
from nxwright.tft.tft_file import firmware_names
from tests.tft.made_tft import made_user_code
from tests.tft.t_components import FillStartAndLoadPieces, TypePieces
from tests.tft.unit_inputs import page, project_of


class PiecesTest(TypePieces, FillStartAndLoadPieces, unittest.TestCase):
    """Each component of the probe on a model of a smaller screen that keeps
    its whole user code, of every type, at its type's functions, against the
    probe's pieces: its memory, its drawing, its entries, its background
    fill, its events' start, and its blocks in the load section, on its page
    made in memory on that model (tests/tft/t_components.py)."""

    PROBES = model_probes.PROBES
    COUNT = 19
    FILL_COUNT = 17
    START_COUNT = 9
    LOAD_COUNT = 3


class HeaderTest(unittest.TestCase):

    def test_header_1_gives_the_model(self):
        # Its sizes at 0x0C, the longer side first, then as the model gives
        # them, and its device ID at 0x2E, as the Nextion Editor wrote them.
        project = project_of(page(screen="NX4827T043"), screen="NX4827T043", fonts=0)
        firmware = Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names("T")})
        data = package(project, made_user_code(), firmware)
        self.assertEqual(struct.unpack_from("<4H", data, 0x0C), (480, 272, 480, 272))
        self.assertEqual(data[0x2E:0x32], bytes.fromhex("b16e29ca"))


class RulesTest(unittest.TestCase):
    """The rules take each model of T, K, P, E, and F, and the page's size and a
    component's place as the model's screen is, at the project's rotation."""

    def test_each_model_of_t_k_p_e_and_f(self):
        covered = [Need("model", model.name, series=model.series) for model in MODELS
                   if model.series in ("T", "K", "P", "E", "F")]
        self.assertEqual(len(covered), 27)
        self.assertEqual(unmatched(covered, packaging.MATCHED), [])
        # A model nxwright does not know is refused.
        left = [Need("model", "NX0000F000", series="F")]
        self.assertEqual(unmatched(left, packaging.MATCHED), left)

    def test_the_page_s_size(self):
        def page(name: str, value: int, model: str, degrees: int = 0) -> Need:
            return Need("attribute", "page." + name, value.to_bytes(2, "little"),
                        series=model[6], model=model, rotation=degrees)
        covered = [page("w", 240, "NX3224T024"), page("h", 320, "NX3224T024"),
                   page("w", 272, "NX4827K043", 90), page("h", 1024, "NX1060P101", 270)]
        self.assertEqual(unmatched(covered, frame.MATCHED), [])
        # The Nextion Editor writes a page of any other size at its screen's.
        covered = [page("w", 320, "NX3224T024"), page("h", 480, "NX4827K043"),
                   page("w", 2001, "NX3224T024"), page("h", 1, "NX4827K043")]
        self.assertEqual(unmatched(covered, frame.MATCHED), [])

    def test_a_place_past_the_screen(self):
        # nxwright's build refuses a component past the screen on T, K, and
        # F, so nxwright writes any place as it is, on every series. Its record
        # stores the place, the size, and the right and bottom edges in 2
        # signed bytes each, where the most that fits is 32767.
        def text_at(x: int, y: int, w: int, h: int, series: str) -> Need:
            context = {name: value.to_bytes(2, "little", signed=True)
                       for name, value in (("x", x), ("y", y), ("w", w), ("h", h))}
            return Need("attribute", "text.x", context["x"], context=context, series=series)
        for series in ("T", "K", "P", "E", "F"):
            with self.subTest(series):
                for place in ((300, 10, 100, 30), (6001, 0, 2001, 2), (0, 0, 0, 0),
                              (32766, 32767, 2, 1)):
                    self.assertTrue(place_fits_its_record(text_at(*place, series)), place)
                for place in ((32767, 0, 2, 2), (0, 32767, 2, 2), (-1, 0, 2, 2), (0, 0, -1, 2)):
                    self.assertFalse(place_fits_its_record(text_at(*place, series)), place)

    def test_every_need_gives_the_model(self):
        project = project_of(page(series="K", screen="NX3224K028"), series="K",
                             screen="NX3224K028", fonts=0)
        self.assertEqual({need.model for need in project_needs(project)}, {"NX3224K028"})


if __name__ == "__main__":
    unittest.main()
