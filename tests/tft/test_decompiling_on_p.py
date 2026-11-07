"""The decoders of a page and of the components of T's types on P
(tft/decompiling/page.py and component_types/), on the facts of probes of
P and of the key probes on P, as no probe of P that keeps its user code has
a key:

- each page and each component of those types, rebuilt from what its
  decoder reads back, compiles into the same user code
  (unit_inputs.rebuilt_user_code), on every probe of P whose pages are made
  in memory;
- each page whose every component has a decoder on P, written as its two
  source files and read back with nxwright's library, keeps each object's
  events as the probe's own code, without the code the Nextion Editor adds,
  such as a key's lines, on the probes of P that keep their user code. The
  other probes' code is often written in another form than the decoder of
  code writes, such as without an indent in an if's block.
"""
import importlib
import pkgutil
import unittest

from nxwright.project.page_block import Event

from nxwright.tft import frame
from tools.tft import probing
from nxwright.tft.component_types import KEYBOARD_PAGES
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from nxwright.tft.decompiling.page import decoded_page_values
from tools.tft.probing import key_probes
from tests.tft.t_components import made_in_memory
from tests.tft.test_decompiling_page_files import _names, _read_back
from tests.tft.test_decompiling_p_values import _probes
from tests.tft.unit_inputs import probe_facts, rebuilt_user_code

# The types whose decoders read them on P: the page, and T's types.
_DECODED = ("page", "text", "number", "xfloat", "button", "dual-state-button", "checkbox",
            "radio", "picture", "crop", "hotspot", "progress-bar", "slider", "gauge", "qr-code",
            "waveform", "scrolling-text", "timer", "variable", "touch-capture")
# The probes whose code the decoder of code writes in another form than the
# probe's, which tests/tft/test_decompiling_code.py tests: a macro under its
# readable name, labels under theirs, and a name of the page's own
# component without the page's name (D10).
_WRITTEN_OTHERWISE = ("p-macros-called", "p-goto-across-program-and-events",
                      "p-globals-on-two-pages")
# The probes whose facts alone do not compile: their code names a variable,
# __g0_0, that their facts do not declare.
_NOT_COMPILED_FROM_FACTS = ("data-record-in-code", "p-data-record-in-code")


def _values_of(decoded_object, decoded_page, decoded_file):
    """Returns the attributes the decoder of `decoded_object`'s type reads
    back, or None for a type _DECODED lacks."""
    if decoded_object.type_name not in _DECODED:
        return None
    if decoded_object.object_id == 0:
        return decoded_page_values(decoded_page, decoded_file).attributes
    return decoded_values(decoded_object, decoded_page, decoded_file).attributes


def _every_p_probe() -> list:
    """Returns each probe of P whose pages are made in memory, once each, but
    _NOT_COMPILED_FROM_FACTS."""
    found = {}
    for module_info in pkgutil.iter_modules(probing.__path__):
        if module_info.name.endswith("_probes"):
            module = importlib.import_module("tools.tft.probing." + module_info.name)
            for probe in getattr(module, "PROBES", []):
                # A probe of an older Nextion Editor, whose `ours` is None,
                # is another's to read.
                if (probe.base == "P" and made_in_memory(probe) and probe.ours is not None
                        and probe.name not in _NOT_COMPILED_FROM_FACTS):
                    found.setdefault(probe.name, probe)
    return list(found.values())


def _projects(probes: list) -> list:
    """Returns (a probe's name, its Project of facts) of each of `probes`,
    then of each key probe made in memory, on P."""
    return ([(probe.name, probe_facts(probe)) for probe in probes]
            + [(probe.name, probe_facts(probe, series="P")) for probe in key_probes.PROBES
               if made_in_memory(probe)])


def _events(page_object) -> dict:
    """Returns {event's name: its lines of code} of `page_object`."""
    return {item.name: item.lines for item in page_object.items if isinstance(item, Event)}


class DecodersTest(unittest.TestCase):

    def test_each_object_rebuilt_from_its_values(self):
        rebuilt = 0
        for name, project in _projects(_every_p_probe()):
            with self.subTest(name):
                code, again, count = rebuilt_user_code(project, _values_of)
                self.assertEqual(again, code)
                rebuilt += count
        # 3645 objects.
        self.assertEqual(rebuilt, 3645)

    def test_each_page_s_events(self):
        pages = added = keys = 0
        for name, project in _projects(_probes()):
            if name in _WRITTEN_OTHERWISE:
                continue
            settings = project.settings
            decoded = decoded_user_code(frame.user_code(project), "P", settings.model.name,
                                        settings.rotation, settings.encoding)
            for decoded_page, made in zip(decoded.pages, project.pages):
                # A keyboard page's own code has comments, which no TFT file
                # keeps.
                if (made.name in KEYBOARD_PAGES.values()
                        or any(each.type_name not in _DECODED for each in decoded_page.objects)):
                    continue
                with self.subTest(name, page=decoded_page.page_id):
                    read = _read_back(decoded_page, decoded, _names(project))
                    self.assertEqual([_events(each) for each in read.objects],
                                     [_events(each) for each in made.objects])
                    pages += 1
                    values = [decoded_values(each, decoded_page, decoded)
                              for each in decoded_page.objects[1:]]
                    added += sum(bool(each.added) for each in values)
                    keys += sum("key" in each.attributes for each in values)
        # 206 pages, with 111 components the Nextion Editor adds code for, 6
        # of them for a key.
        self.assertEqual((pages, added, keys), (206, 111, 6))


if __name__ == "__main__":
    unittest.main()
