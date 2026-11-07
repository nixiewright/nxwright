"""A decoded page's two source files (tft/decompiling/page_files.py), read
back with nxwright's library (page_source.page_from_source), against the
probe's own page: each attribute the file keeps of each object, and each
event's code, without the blocks the Nextion Editor added.

The probes that keep their user code keep stand-in code, so the test of
their attributes reads their fixtures, and the tests of code have the
compile write a probe's pages in memory, which gives the encoder's own
blocks.
"""
import unittest

from nxwright.language.resource_names import ResourceNames
from nxwright.project.attribute_values import number_from_bytes
from nxwright.project.component_defaults import DEFAULTS_FILE, defaults_from_toml
from nxwright.project.page_block import Event
from nxwright.source.page_source import PageSource, page_from_source

from nxwright.tft import frame
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import CodeRun, decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from nxwright.tft.decompiling.page import decoded_page_values
from nxwright.tft.decompiling import page_files as page_files_module
from nxwright.tft.decompiling.page_files import page_files
from tools.tft.probing import (checkbox_probes, frame_probes, key_probes, scrolling_text_probes,
                           timer_probes)
from tests.tft.t_components import made_in_memory
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.test_frame import _facts
from tests.tft.unit_inputs import probe_facts, user_code_of

_DEFAULTS = defaults_from_toml(DEFAULTS_FILE.read_text(encoding="utf-8"), DEFAULTS_FILE.name)
# The attributes the file keeps only as whether they are 0: an effect.
_KEPT_AS_ZERO_OR_NOT = ("effect",)


def _names(project) -> ResourceNames:
    """Returns ResourceNames for `project`'s pictures and fonts, each named
    after its kind and ID, as a folder writer would choose them."""
    count = {kind: sum(each == kind for each, _ in project.resources)
             for kind in ("picture", "font")}
    return ResourceNames(["picture%d" % number for number in range(count["picture"])],
                         ["font%d" % number for number in range(count["font"])])


def _read_back(decoded_page, decoded, names, code: bool = True):
    """Returns the PageBlock nxwright's library builds from `decoded_page`'s
    two source files, or from its page file alone without `code`, as the
    probes' stand-in code is no code nxwright's library reads."""
    toml, events = page_files(decoded_page, decoded, names)
    return page_from_source(PageSource(toml, events if code else ""),
                            decoded_page.objects[0].name.text, names, _DEFAULTS,
                            encoding=decoded.encoding)


def _in_memory(module, name: str) -> tuple:
    """Returns (the Project of facts of the probe `name` of `module`, and the
    decoded file of the user code the compile writes for it)."""
    probe = next(probe for probe in module.PROBES if probe.name == name)
    project = probe_facts(probe)
    return project, decoded_user_code(frame.user_code(project), "T", "NX4832T035", 0,
                                      project.settings.encoding)


def _code(page_block, object_name: str, event: str) -> list:
    """Returns the lines of code of `object_name`'s event `event` in
    `page_block`, as text."""
    page_object = next(each for each in page_block.objects
                       if each.attribute("objname") == object_name.encode("latin-1"))
    return [line.decode("latin-1") for item in page_object.items
            if isinstance(item, Event) and item.name == event for line in item.lines]


class AttributesTest(unittest.TestCase):

    def test_each_page_of_each_probe(self):
        # Every attribute a decoder gives comes back from the page file as the
        # probe's own, but an effect, which the file keeps only as 0 or not,
        # and a page's place and size, which are the screen's.
        pages = objects = 0
        for probe in _probes_keeping_their_user_code():
            if not made_in_memory(probe):
                continue
            # The compile writes every page at the screen's place and size.
            project = _facts(probe)
            decoded = decoded_user_code(user_code_of(probe), probe.base, "NX4832T035", 0,
                                        "iso-8859-1")
            names = _names(project)
            for decoded_page, made in zip(decoded.pages, project.pages):
                read = _read_back(decoded_page, decoded, names, code=False)
                given = [decoded_page_values(decoded_page, decoded).attributes] + [
                    decoded_values(each, decoded_page, decoded).attributes
                    for each in decoded_page.objects[1:]]
                for attributes, back, own in zip(given, read.objects, made.objects):
                    with self.subTest(probe.name, page=decoded_page.page_id,
                                      object=back.attribute("objname")):
                        for name in attributes:
                            if name in _KEPT_AS_ZERO_OR_NOT:
                                self.assertEqual(
                                    number_from_bytes(back.attribute(name)) != 0,
                                    number_from_bytes(own.attribute(name) or b"\x00") != 0)
                            elif own.attribute(name) is not None:
                                self.assertEqual(back.attribute(name), own.attribute(name),
                                                 name)
                    objects += 1
                pages += 1
        # 209 pages, of 850 objects.
        self.assertEqual((pages, objects), (209, 850))


class CodeTest(unittest.TestCase):

    def test_a_page_s_events(self):
        # The page's load and loadend code, split at the Nextion Editor's
        # doevents, and its other events, each the probe's own lines.
        project, decoded = _in_memory(frame_probes, "frame-page-events")
        read = _read_back(decoded.pages[0], decoded, _names(project))
        own = project.pages[0].objects[0]
        for event in ("load", "loadend", "down", "up", "unload"):
            with self.subTest(event):
                self.assertEqual(_code(read, "page0", event),
                                 [line.decode("latin-1") for item in own.items
                                  if isinstance(item, Event) and item.name == event
                                  for line in item.lines])

    def test_the_code_the_nextion_editor_adds_is_left_out(self):
        # A key's lines after a text's own code, a timer's "S " block before
        # its own, a checkbox's switch of its val, and a scrolling text's
        # code in its page's load section: each event comes back as the
        # probe's own code alone.
        for module, name, object_name, event in (
                (key_probes, "key-text-on-the-keypad", "t0", "up"),
                (timer_probes, "timer-event-code", "tm0", "timer"),
                (checkbox_probes, "checkbox-one", "c0", "down"),
                (scrolling_text_probes, "scrolling-text-one", "page0", "load")):
            project, decoded = _in_memory(module, name)
            read = _read_back(decoded.pages[0], decoded, _names(project))
            own = next(each for each in project.pages[0].objects
                       if each.attribute("objname") == object_name.encode("latin-1"))
            with self.subTest(name):
                self.assertEqual(_code(read, object_name, event),
                                 [line.decode("latin-1") for item in own.items
                                  if isinstance(item, Event) and item.name == event
                                  for line in item.lines])

    def test_more_added_blocks_than_a_run_has(self):
        # The cut of a run of two blocks, of three the Nextion Editor added,
        # is refused, rather than keeping a block. One of two is cut.
        run = CodeRun(0x40, [b"a", b"b"])
        self.assertEqual(page_files_module._without(run, 1, 0), CodeRun(0x45, [b"b"]))
        self.assertRaises(DecodeError, page_files_module._without, run, 1, 2)

    def test_code_in_an_event_its_type_has_not(self):
        # A text's code under an event no text has is refused, not dropped.
        project, decoded = _in_memory(key_probes, "key-text-on-the-keypad")
        text = decoded.pages[0].objects[1]
        text.events["timer"] = text.events["up"]
        with self.assertRaisesRegex(DecodeError, "no event of"):
            page_files(decoded.pages[0], decoded, _names(project))

    def test_a_keyboard_page_is_its_system_page(self):
        project, decoded = _in_memory(key_probes, "key-text-on-the-keypad")
        toml, _ = page_files(decoded.pages[1], decoded, _names(project))
        self.assertIn('system_page = "keypad"', toml)


if __name__ == "__main__":
    unittest.main()
