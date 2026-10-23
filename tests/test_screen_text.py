"""The text layout of what a simulation's screen shows
(nxwright/testing/screen_text.py)."""
from nxwright.project.pictures import write_png
from nxwright.testing.screen_text import screen_text
from nxwright.testing.simulation import Simulation
from tests.test_folder_check import edited_app
from tests.test_simulation import SimulationTestCase, placed


class ScreenTextTest(SimulationTestCase):

    def setUp(self):
        super().setUp()
        (self.root / "pictures").mkdir()
        (self.root / "pictures" / "dot.png").write_bytes(
            write_png(20, 20, bytes((200, 40, 40, 255)) * 400))
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app["pictures"].append("dot")))
        self.program("page page0\n")
        self.page("page0", [placed("t0", "text", 20, 10, txt="Temperature"),
                            placed("n0", "number", 240, 10, val=21),
                            placed("b0", "button", 20, 400, txt="Set"),
                            placed("p0", "picture", 600, 20, pic="dot"),
                            placed("t1", "text", 20, 200),
                            placed("t2", "text", 300, 200, txt="abc", pw=1),
                            placed("c0", "checkbox", 400, 200)])
        self.page("second", [])

    def test_each_component_shown_what_code_painted_and_those_hidden(self):
        # A line for each component that shows, in ID order: its name, type,
        # box, and what it shows. A password shows as the screen shows it.
        simulation = Simulation(self.root)
        for line in ("vis t1,0", "fill 10,300,50,20,63488", "line 0,0,10,10,0", "pic 400,300,0"):
            simulation.serial_input(line)
        simulation.press("b0")
        self.assertEqual(screen_text(simulation.drawing_inputs(), ["dot"]), "\n".join([
            "page page0 (800 x 480), background colour #ffffff",
            't0  text      20,10    100x50  "Temperature"',
            'n0  number    240,10   100x50  "21"',
            'b0  button    20,400   100x50  "Set"  pressed',
            'p0  picture   600,20   100x50  picture 0 "dot"',
            't2  text      300,200  100x50  "***"',
            "c0  checkbox  400,200  100x50  on",
            'painted: fill 10,300 50x20 #ff0000; line 0,0 to 10,10 #000000; '
            'pic 0 "dot" at 400,300',
            "hidden: t1"]))

    def test_a_picture_the_app_does_not_list(self):
        # Without a name for its ID, a picture is given by its ID alone.
        simulation = Simulation(self.root)
        self.assertIn("p0  picture   600,20   100x50  picture 0\n",
                      screen_text(simulation.drawing_inputs(), []))

    def test_the_page_before_while_ref_stop_holds(self):
        # The text says what the screen shows: after a page change while
        # ref_stop holds, still the page before, as the picture does.
        simulation = Simulation(self.root)
        for line in ("ref_stop", "page second"):
            simulation.serial_input(line)
        self.assertTrue(screen_text(simulation.drawing_inputs(), ["dot"])
                        .startswith("page page0 "))
        simulation.serial_input("ref_star")
        self.assertEqual(screen_text(simulation.drawing_inputs(), ["dot"]),
                         "page second (800 x 480), background colour #ffffff")

    def test_a_page_without_background_or_with_a_picture(self):
        for sta, said in ((0, "no background"), (2, 'background picture 0 "dot"')):
            with self.subTest(sta=sta):
                self.write("pages/second.page.toml",
                           '[page]\nname = "second"\ntype = "page"\nx = 0\ny = 0\nw = 800\n'
                           'h = 480\nsta = %d\npic = "dot"\n' % sta)
                simulation = Simulation(self.root, "second")
                self.assertEqual(screen_text(simulation.drawing_inputs(), ["dot"]),
                                 "page second (800 x 480), %s" % said)
