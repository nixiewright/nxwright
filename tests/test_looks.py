"""What an agent reads of a running simulation (testing/looks.py): the
components of the page shown, values, and the log."""
import json

from nxwright import NxwrightError
from nxwright.drawing.screen_pictures import ScreenPictures
from nxwright.testing.looks import components, log, screen, touch_refusal, values
from nxwright.testing.preview import Previews
from nxwright.testing.simulation import Simulation
from tests.test_simulation import SimulationTestCase, placed, table


class LooksTest(SimulationTestCase):

    def setUp(self):
        super().setUp()
        self.program("int count=0\n\npage page0\n")
        self.page("page0", [placed("t0", "text", 20, 10, txt="hi"),
                            placed("b0", "button", 20, 100), table("tm0", "timer", tim=50)],
                  "on b0.down:\n  count = count + 1\n  vis t0,0\n  prints \"pressed\",0\n")
        self.page("second", [])
        self.simulation = Simulation(self.root)

    def test_the_components_the_page_first_and_those_hidden(self):
        self.simulation.press("b0", 30, 110)
        self.simulation.release()
        self.assertEqual(components(self.simulation), [
            {"name": "page0", "type": "page", "x": 0, "y": 0, "w": 800, "h": 480,
             "shown": True},
            {"name": "t0", "type": "text", "x": 20, "y": 10, "w": 100, "h": 50, "shown": False},
            {"name": "b0", "type": "button", "x": 20, "y": 100, "w": 100, "h": 50,
             "shown": True},
            # A component without a place has no box.
            {"name": "tm0", "type": "timer", "x": None, "y": None, "w": None, "h": None,
             "shown": True}])

    def test_no_components_while_no_page_shows(self):
        self.program("int count=0\n")
        self.assertEqual(components(Simulation(self.root)), [])

    def test_values_all_or_those_named(self):
        everything = values(self.simulation)
        self.assertEqual((everything["count"], everything["t0.txt"]), (0, "hi"))
        self.assertEqual(values(self.simulation, ["t0.txt", "count"]),
                         {"t0.txt": "hi", "count": 0})

    def test_values_are_those_code_names_alone(self):
        # Not what the simulation records outside the page, as what was
        # sent, which is no value code reads; and every one is plain data.
        self.simulation.press("b0", 30, 110)
        everything = values(self.simulation)
        self.assertNotIn("sent", everything)
        json.dumps(everything)
        with self.assertRaisesRegex(NxwrightError, "nothing named sent"):
            values(self.simulation, ["sent"])

    def test_the_records_of_data_files_are_no_values(self):
        # The files data records hold, those shut out of theirs, and those
        # whose `path` code set are recorded, and are no values code reads.
        self.page("page0", [table("d0", "data-record", x=10, y=10, w=250, h=140,
                                  path="sd0/1.data", mode=1)])
        simulation = Simulation(self.root)
        simulation.serial_input('d0.path="sd0/2.data"')
        everything = values(simulation)
        self.assertEqual([name for name in everything if name.startswith("data ")], [])
        json.dumps(everything)

    def test_a_components_name_alone_gives_each_of_its_attributes(self):
        found = values(self.simulation, ["t0", "count"])
        self.assertEqual((found["t0.txt"], found["t0.x"], found["count"]), ("hi", 20, 0))
        self.assertEqual({name for name in found if name != "count"},
                         {name for name in values(self.simulation) if name.startswith("t0.")})
        # A name is a whole one: t0's attributes are not those of t.
        with self.assertRaisesRegex(NxwrightError, "nothing named t$"):
            values(self.simulation, ["t"])

    def test_names_the_page_does_not_know_are_refused_by_name(self):
        with self.assertRaisesRegex(NxwrightError, "nothing named t9.txt or speed"):
            values(self.simulation, ["count", "t9.txt", "speed"])

    def test_the_log_numbered_from_the_start(self):
        for _ in range(2):
            self.simulation.press("b0", 30, 110)
            self.simulation.release()
        lines = log(self.simulation)
        self.assertEqual([(entry["number"], entry["line"]) for entry in lines],
                         [(1, "sends 70 72 65 73 73 65 64"), (2, "sends 70 72 65 73 73 65 64")])
        self.assertEqual(lines[0]["time"], self.simulation.log[0][0])
        self.assertEqual(log(self.simulation, 1), lines[1:])
        self.assertEqual(log(self.simulation, 5), [])

    def test_the_log_after_a_line_that_is_no_number_is_refused(self):
        for after in (-1, "1", 1.5, True):
            with self.subTest(after=after):
                with self.assertRaisesRegex(NxwrightError, "a line's number, 0 or more"):
                    log(self.simulation, after)


class ScreenTest(SimulationTestCase):
    """screen: the text layout, the page shown, and its picture, from one
    drawing_inputs."""

    def setUp(self):
        super().setUp()
        self.page("page0", [placed("t0", "text", 20, 10, txt="hi")])

    def test_the_text_the_page_and_the_picture(self):
        self.program("page page0\n")
        shown = screen(Simulation(self.root), Previews(), ScreenPictures())
        self.assertEqual(shown["page"], "page0")
        self.assertIn('"hi"', shown["text"])
        self.assertEqual(shown["png"][:8], b"\x89PNG\r\n\x1a\n")

    def test_no_picture_unless_asked(self):
        self.program("page page0\n")
        shown = screen(Simulation(self.root), Previews(), ScreenPictures(), picture=False)
        self.assertEqual(sorted(shown), ["page", "text"])

    def test_before_a_page_shows(self):
        self.program("int count=0\n")
        self.assertEqual(screen(Simulation(self.root), Previews(), ScreenPictures()),
                         {"text": "no page shows yet", "page": None})


class TouchRefusalTest(SimulationTestCase):
    """touch_refusal, past what the MCP server's tests reach."""

    def test_before_a_page_shows(self):
        self.program("int count=0\n")
        self.page("page0", [])
        self.assertEqual(touch_refusal(Simulation(self.root), "press", 10, 10),
                         "no page shows yet, so the screen cannot be pressed")
