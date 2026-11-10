"""A waveform's channel as a "wave" shape: its pixels
(drawing/waveform_drawing.py), which the webviews' painter
(editors/vscode/media/wave-painter.mjs) must match. Both are checked
against the same cases, in tests/fixtures/wave-painter/cases.json. This
module checks that the file contains what Python paints, and the
extension's test/wave-painter.test.mjs checks that the webviews' painter
gives the same pixels. After an intended change to both painters, write
the file again with:

    python -m tests.test_wave_painting write
"""
import json
from pathlib import Path
import sys
import unittest

from nxwright.drawing.screen_pictures import paint_drawing
from nxwright.drawing.waveform_drawing import wave_pixels
from nxwright.testing.preview import Previews
from nxwright.testing.simulation import Simulation
from tests.test_simulation import SimulationTestCase, table

CASES_FILE = Path(__file__).resolve().parent / "fixtures" / "wave-painter" / "cases.json"

# A long run of values that rise and fall by uneven steps.
_UNEVEN = [(place * 37) % 201 for place in range(60)]
# Each case's waveform: its width and height, its channel's points, oldest
# first, and its `dis` and `dir`.
_INPUTS = [
    # Fewer points than columns, in each direction.
    (8, 6, [0, 20, 60, 100, 40], 5, 0),
    (8, 6, [0, 20, 60, 100, 40], 5, 1),
    (8, 6, [0, 20, 60, 100, 40], 5, 2),
    # More points than columns: the latest are shown.
    (5, 10, list(range(0, 100, 7)), 10, 0),
    (5, 10, list(range(0, 100, 7)), 10, 1),
    (5, 10, list(range(0, 100, 7)), 10, 2),
    # Values below the bottom and above the top stay within the waveform.
    (6, 4, [-50, 0, 30, 500, 255], 100, 1),
    # `dis` scales the values, cut toward zero.
    (10, 20, [1, 2, 3, 99, 101, 150, 151], 33, 1),
    (10, 20, [1, 2, 3, 99, 101, 150, 151], 200, 0),
    (7, 9, [-7, -3, 3, 7], 50, 2),
    # One point, one column, no points, and no room.
    (3, 3, [1], 100, 0),
    (3, 3, [1], 100, 2),
    (1, 8, [10, 70, 30], 10, 0),
    (1, 8, [10, 70, 30], 10, 1),
    (4, 4, [], 100, 2),
    (0, 5, [1], 100, 0),
    (5, 0, [1], 100, 1),
    # A waveform wide enough for steep rises and falls side by side.
    (40, 30, _UNEVEN, 15, 0),
    (40, 30, _UNEVEN, 15, 1),
    (70, 30, _UNEVEN, 15, 2),
]


def cases() -> list:
    """Returns the cases: each waveform of _INPUTS with the pixels Python
    paints for it, as the cases' file holds them."""
    return [{"width": width, "height": height, "points": points, "dis": dis, "dir": direction,
             "pixels": [list(pixel) for pixel in wave_pixels(width, height, points, dis,
                                                             direction)]}
            for width, height, points, dis, direction in _INPUTS]


def cases_text() -> str:
    """Returns the text of the cases' file: a case to a line."""
    return "[\n%s\n]\n" % ",\n".join(json.dumps(case, separators=(",", ":")) for case in cases())


class WavePixelsTest(unittest.TestCase):

    def test_the_cases_file_holds_what_python_paints(self):
        self.assertEqual(CASES_FILE.read_text(encoding="utf-8"), cases_text(),
                         "the cases' file is not what wave_pixels gives: see this module's "
                         "opening comment")

    def test_each_direction(self):
        # Three points in a waveform four wide and five high, each value a
        # row: the latest first; the oldest first; and ending at the right.
        self.assertEqual(wave_pixels(4, 5, [0, 4, 2], 100, 0),
                         [(0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2), (2, 3), (2, 4)])
        self.assertEqual(wave_pixels(4, 5, [0, 4, 2], 100, 1),
                         [(0, 4), (1, 0), (1, 1), (1, 2), (1, 3), (1, 4), (2, 0), (2, 1), (2, 2)])
        self.assertEqual(wave_pixels(4, 5, [0, 4, 2], 100, 2),
                         [(1, 4), (2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (3, 0), (3, 1), (3, 2)])

    def test_a_wave_shape_is_painted_in_its_colour_over_what_is_under_it(self):
        drawing = {"width": 6, "height": 5, "transparent": False, "shapes": [
            {"component": "page0", "kind": "colour", "x": 0, "y": 0, "w": 6, "h": 5,
             "colour": "#102030"},
            {"component": "chart", "kind": "wave", "x": 1, "y": 0, "w": 4, "h": 5,
             "colour": "#ff8000", "points": [0, 4, 2], "dis": 100, "dir": 1}]}
        picture = paint_drawing(drawing)
        painted = {(x, y) for x in range(6) for y in range(5)
                   if picture.getpixel((x, y)) == (255, 128, 0)}
        self.assertEqual(painted, {(1 + column, row)
                                   for column, row in wave_pixels(4, 5, [0, 4, 2], 100, 1)})
        self.assertEqual(picture.getpixel((0, 0)), (16, 32, 48))
        self.assertEqual(picture.getpixel((5, 4)), (16, 32, 48))


class WaveformShapesTest(SimulationTestCase):

    def test_a_simulations_waveform_gives_a_wave_shape_for_each_of_its_channels(self):
        self.program("page page0\n")
        self.page("page0", [table("chart", "waveform", x=10, y=20, w=4, h=50, ch=2, dis=50,
                                  dir=1, pco0=31, pco1=63488)])
        simulation = Simulation(self.root)
        for value in (10, 20, 30, 40, 50):
            simulation.serial_input("add 1,0,%d" % value)
        drawing = Previews().simulation_drawing(simulation, simulation.drawing_inputs())
        waves = [shape for shape in drawing["shapes"] if shape["kind"] == "wave"]
        # The latest four points of channel 0 are shown, as the waveform is
        # four wide. Channel 1 has no point yet, and has its shape all the
        # same: where its points go once they come.
        box = {"component": "chart", "kind": "wave", "x": 10, "y": 20, "w": 4, "h": 50,
               "dis": 50, "dir": 1}
        self.assertEqual(waves, [dict(box, colour="#0000ff", points=[20, 30, 40, 50]),
                                 dict(box, colour="#ff0000", points=[])])
        # The points sent on their own are the drawing's own shapes.
        inputs = simulation.drawing_inputs()
        self.assertEqual(Previews().simulation_waves(simulation, inputs),
                         {"waveforms": [{"component": "chart", "shapes": waves}],
                          "page": "page0", "start": drawing["start"], "entry": drawing["entry"]})
        # A waveform that does not show sends none.
        simulation.serial_input("vis chart,0")
        self.assertEqual(Previews().simulation_waves(simulation, simulation.drawing_inputs())
                         ["waveforms"], [])


if __name__ == "__main__":
    if sys.argv[1:] == ["write"]:
        CASES_FILE.parent.mkdir(parents=True, exist_ok=True)
        CASES_FILE.write_bytes(cases_text().encode("utf-8"))
        print("wrote %s" % CASES_FILE)
    else:
        unittest.main()
