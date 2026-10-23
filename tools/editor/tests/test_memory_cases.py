"""Tests of the memory probe's projects (memory_cases.py): nxwright builds
them, as the probe builds them before the Editor compiles them. They need
neither the Editor nor pywinauto."""
from pathlib import Path
import tempfile
import unittest

from nxwright.project.container import HmiContainer
from tools.editor.memory_cases import (TYPES, Case, Component, Project, bounded_text,
                                       build_project, placement, varied_values)
from tools.editor.memory_probe import MIXED_CODE
from tools.editor.memory_series import SeriesProbe, varied_case_values


class BoundedTextTest(unittest.TestCase):

    def test_paired_as_the_build_pairs_them(self):
        # A sliding text's path_m sets aside room for its lines, bounding no text.
        for kind, buffer, text in (("text", "txt_maxl", "txt"), ("data-record", "path_m", "path"),
                                   ("sliding-text", "path_m", None), ("waveform", "molloc", None),
                                   ("hotspot", "txt_maxl", None)):
            with self.subTest(kind=kind, buffer=buffer):
                self.assertEqual(bounded_text(kind, buffer), text)


class VariedValuesTest(unittest.TestCase):

    def test_a_number_within_the_range_the_build_takes(self):
        # One more than an aph of 127 is past the Editor's range, which the
        # build refuses on every type, so the probe tries one less alone. A
        # text's spax, whose range is all its byte holds, tries both.
        self.assertEqual(varied_values("hotspot", "aph", {"aph": 127}), [126])
        self.assertEqual(varied_values("text", "aph", {"aph": 127}), [126])
        self.assertEqual(varied_values("text", "spax", {"spax": 5}), [6, 4])


class RefusedPageTest(unittest.TestCase):

    def test_a_page_the_editor_refuses_builds(self):
        # The probe measures the Editor's refusals, so it builds what the
        # build's own memory check refuses: here a QR code needing more than
        # its page leaves of a basic screen's memory.
        place = tuple(sorted(placement("qr-code", 480, 320).items()))
        project = Project("NX4832T035", (Case("need qr-code", (
            Component("qr-code", (("txt_maxl", 192),)),)),), (("qr-code", place),))
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(build_project(project, Path(folder)).is_file())


class KeyboardPageTest(unittest.TestCase):

    def test_a_project_holding_the_keypad(self):
        # A text bound to the keypad, which binds only a component of global
        # scope, beside nxwright's keypad page.
        place = tuple(sorted(placement("text", 480, 320).items()))
        project = Project("NX4832T035", (Case("keyboard text", (
            Component("text", (("vscope", 1), ("key", 2))),)),), (("text", place),),
            keyboards=("keypad",))
        with tempfile.TemporaryDirectory() as folder:
            pages = HmiContainer.from_file(build_project(project, Path(folder))) \
                .blocks_with_extension("pa")
            self.assertEqual(len(pages), 3)
        # A project without one is named as before keyboards could be held,
        # so that the probe's kept compiles are found again.
        self.assertEqual(Project("NX4832T035", (Case("type text", (Component("text"),)),))
                         .name(), "NX4832T035-2e1ee0395d3d40ec")


class BuildProjectTest(unittest.TestCase):

    def test_every_type_varied_and_a_mixed_page(self):
        # Every type with every attribute it may vary changed, and a page of
        # several types with event code, as the probe's first rounds give them.
        probe = SeriesProbe(None, "NX8048P050")
        cases = tuple(Case("varied %s" % kind,
                           (Component(kind, tuple(varied_case_values(probe, kind).items())),))
                      for kind in TYPES)
        cases += (Case("mixed 0", (Component("text"), Component("number"), Component("timer")),
                       (), MIXED_CODE),)
        project = Project(probe.model, cases, tuple(
            (kind, tuple(sorted(probe.base[kind].items()))) for kind in TYPES))
        with tempfile.TemporaryDirectory() as folder:
            built = build_project(project, Path(folder))
            pages = HmiContainer.from_file(built).blocks_with_extension("pa")
            self.assertEqual(len(pages), len(cases) + 1)


if __name__ == "__main__":
    unittest.main()
