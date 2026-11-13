"""The tool's add-page command (tools/editor/editor.py), run against
stand-ins for the Nextion Editor's windows. The tests need neither the
Nextion Editor nor a window, only the tool's packages."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from tools.editor import editor


def bar_item(control_type: str, name: str, pressed=None):
    """Returns a stand-in for an item of the Page panel's bar. `pressed`
    is what its press does."""
    return SimpleNamespace(element_info=SimpleNamespace(control_type=control_type, name=name),
                           invoke=pressed or (lambda: None))


class PagePanel:
    """A stand-in for the Page panel's bar: its buttons, then its page
    count. `on_first` is what a press of its first button does to the
    count."""

    def __init__(self, pages: int, on_first=lambda pages: pages + 1, buttons: int = 3):
        self.pages = pages
        self.on_first = on_first
        self.buttons = buttons

    def press_first(self):
        self.pages = self.on_first(self.pages)

    def bar(self, _editor) -> list:
        buttons = [bar_item("Button", "buttonItem%d" % number,
                            self.press_first if number == 1 else None)
                   for number in range(1, self.buttons + 1)]
        return buttons + [bar_item("Custom", str(self.pages))]


class AddPageTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        (self.folder / "work").mkdir()

    def added(self, panel: PagePanel, shown: str = "probe.HMI"):
        """Runs add_page on a stand-in Editor that shows `shown`, a file's
        name in the work folder, or a whole path, and whose Page panel is
        `panel`."""
        title = "Nextion Editor(%s)" % (self.folder / "work" / shown)
        main = SimpleNamespace(window_text=lambda: title)
        dedicated = SimpleNamespace(stop_on_crash=lambda: None, main_window=lambda: main,
                                    stop_if_blocked=lambda when: None)

        def press_now(button) -> list:
            button.invoke()
            return []
        with mock.patch.object(editor, "_stop_on_dialog"), \
                mock.patch.object(editor, "_page_panel_bar", side_effect=panel.bar), \
                mock.patch.object(editor, "_press_in_background", side_effect=press_now), \
                mock.patch.object(editor, "DIALOG_WAIT", 0.2):
            return editor.add_page(dedicated, self.folder)

    def test_the_first_button_adds_a_page_and_the_new_count_is_returned(self):
        panel = PagePanel(pages=2)
        self.assertEqual(self.added(panel), 3)
        self.assertEqual(panel.pages, 3)

    def test_a_project_that_is_not_a_copy_of_the_tools_is_refused_before_any_press(self):
        panel = PagePanel(pages=2)
        with self.assertRaisesRegex(editor.EditorError, "not a copy this tool opened"):
            self.added(panel, shown=str(Path(tempfile.mkdtemp()) / "someone's.HMI"))
        self.assertEqual(panel.pages, 2)

    def test_a_first_button_that_removes_a_page_is_reported_as_not_the_add_button(self):
        panel = PagePanel(pages=2, on_first=lambda pages: pages - 1)
        with self.assertRaisesRegex(editor.EditorError, "from 2 pages to 1"):
            self.added(panel)

    def test_a_press_that_changes_nothing_stops_after_the_wait(self):
        panel = PagePanel(pages=2, on_first=lambda pages: pages)
        with self.assertRaisesRegex(editor.EditorError, "waited .* for the Page panel"):
            self.added(panel)

    def test_a_bar_without_buttons_is_refused(self):
        with self.assertRaisesRegex(editor.EditorError, "has no button"):
            self.added(PagePanel(pages=2, buttons=0))

    def test_a_bar_that_does_not_end_with_a_number_is_refused(self):
        panel = PagePanel(pages=2)
        with mock.patch.object(panel, "bar",
                               return_value=[bar_item("Button", "buttonItem1")]), \
                self.assertRaisesRegex(editor.EditorError, "where its page count was"):
            self.added(panel)


if __name__ == "__main__":
    unittest.main()
