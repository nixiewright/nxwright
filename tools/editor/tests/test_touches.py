"""The steps of `simulate --touch` (tools/editor/touches.py), parsed and
checked as the tool does before the simulator starts. They need neither the
Editor nor pywinauto."""
from pathlib import Path
import unittest

from tools.editor.touches import Picture, Press, Release, StepError, Wait, parse_steps

SCREEN = (800, 480)


class StepsTest(unittest.TestCase):

    def test_each_step(self):
        self.assertEqual(
            parse_steps("press 200,150; release; wait 500; picture tapped.png", SCREEN),
            [Press(200, 150), Release(200, 150), Wait(500), Picture(Path("tapped.png"))])

    def test_spaces_and_a_last_semicolon_are_allowed(self):
        self.assertEqual(parse_steps("  press 0 , 479 ;release;", SCREEN),
                         [Press(0, 479), Release(0, 479)])

    def test_a_list_may_end_with_a_press_held(self):
        # A picture of a component as it shows while held.
        self.assertEqual(parse_steps("press 1,2; picture held.png", SCREEN),
                         [Press(1, 2), Picture(Path("held.png"))])

    def test_refusals_name_the_step(self):
        cases = [
            ("", "no steps"),
            ("press 1,2; press 3,4", r"step 2, 'press 3,4': a press is held already"),
            ("release", r"step 1, 'release': no press is held"),
            ("press 800,0", "outside the screen, 800 by 480 pixels"),
            ("press 0,480", "outside the screen"),
            ("press -1,5", "a point is written X,Y"),
            ("press 1;2", "a point is written X,Y"),
            ("move 1,2", r"step 1, 'move 1,2': not a step"),
            ("press 1,2; release now", "not a step"),
            ("wait soon", "not a step"),
            # A digit Python does not read as a number.
            ("wait ²", "not a step"),
            ("picture", "not a step"),
        ]
        for text, message in cases:
            with self.subTest(text=text):
                with self.assertRaisesRegex(StepError, message):
                    parse_steps(text, SCREEN)

    def test_a_turned_screen_is_checked_at_its_own_size(self):
        self.assertEqual(parse_steps("press 470,790; release", (480, 800)),
                         [Press(470, 790), Release(470, 790)])
        with self.assertRaisesRegex(StepError, "outside the screen"):
            parse_steps("press 790,470", (480, 800))


if __name__ == "__main__":
    unittest.main()
