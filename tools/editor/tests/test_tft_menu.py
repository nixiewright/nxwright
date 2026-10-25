"""Pressing File > TFT file output, as the tool's tft command does
(tools/editor/editor.py), against a stand-in for the File menu. It needs
neither the Editor nor a window, only the tool's packages."""
from types import SimpleNamespace
import unittest
from unittest import mock

from tools.editor import editor


class DroppingMenu:
    """A File menu whose first press to open it is lost, as a busy Nextion
    Editor lost it just after `open`: it lists its items only once open."""

    def __init__(self):
        self.is_open, self.presses = False, 0

    def invoke(self):
        self.presses += 1
        if self.presses > 1:
            self.is_open = not self.is_open

    def children(self):
        item = SimpleNamespace(element_info=SimpleNamespace(name=editor._TFT_MENU_ITEM))
        return [item] if self.is_open else []


class MenuWithoutItem(DroppingMenu):
    """A File menu that opens at once, but does not list the item."""

    def invoke(self):
        self.presses += 1
        self.is_open = not self.is_open

    def children(self):
        return [SimpleNamespace(element_info=SimpleNamespace(name="Open"))] if self.is_open else []


class TftMenuTest(unittest.TestCase):

    def test_a_menu_without_the_item_is_left_closed(self):
        menu = MenuWithoutItem()
        with mock.patch.object(editor, "_MENU_SHOWS", 0.2):
            self.assertIsNone(editor._press_tft_item(menu))
        self.assertEqual((menu.presses, menu.is_open), (2, False))

    def open_tft_output(self, presses: list):
        """Runs _open_tft_output with _press_tft_item giving `presses` in
        turn, and the output window showing once a press gives a list."""
        menu, dedicated = object(), SimpleNamespace(control=lambda name: None,
                                                    recorded=SimpleNamespace(pid=1))

        def wait_for(found, seconds, what, stop=None):
            return "the output window"
        with mock.patch.object(editor, "_only_match", return_value=menu), \
                mock.patch.object(editor, "_required", side_effect=lambda found, **_: found), \
                mock.patch.object(editor, "shown_windows", return_value=[]), \
                mock.patch.object(editor, "_press_tft_item", side_effect=presses) as press, \
                mock.patch.object(editor, "_wait_for", side_effect=wait_for):
            try:
                return editor._open_tft_output(dedicated, None)
            finally:
                self.presses = press.call_count

    def test_a_lost_press_of_file_is_pressed_again_in_the_loop(self):
        self.assertEqual(self.open_tft_output([None, []]), "the output window")
        self.assertEqual(self.presses, 2)

    def test_three_lost_presses_of_file_stop_the_command(self):
        with self.assertRaisesRegex(editor.EditorError, r"pressed File 3 times, and its menu "
                                                        r"did not list"):
            self.open_tft_output([None, None, None])
        self.assertEqual(self.presses, 3)

    def test_a_lost_press_of_the_menu_is_pressed_again(self):
        # The first press shows no item: it is a lost press, the menu is
        # left closed, and the next press opens it and presses its item.
        menu = DroppingMenu()
        with mock.patch.object(editor, "_MENU_SHOWS", 0.2), \
                mock.patch.object(editor, "_press_in_background", return_value=[]) as press:
            self.assertIsNone(editor._press_tft_item(menu))
            self.assertFalse(menu.is_open)
            press.assert_not_called()
            self.assertEqual(editor._press_tft_item(menu), [])
            press.assert_called_once()


if __name__ == "__main__":
    unittest.main()
