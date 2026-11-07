"""The decompiler on E, which writes its user code as P does
(ResearchNotes/tft/e-series.md): every page and component of every probe of E
whose pages are made in memory, rebuilt from what its decoder reads back,
compiles into the same user code (unit_inputs.rebuilt_user_code).
"""
import importlib
import pkgutil
import unittest

from tools.tft import probing
from nxwright.tft.decompiling.objects import decoded_values
from nxwright.tft.decompiling.page import decoded_page_values
from tests.tft.t_components import made_in_memory
from tests.tft.unit_inputs import probe_facts, rebuilt_user_code

# The probe whose facts alone do not compile: its code names a variable,
# __g0_0, that its facts do not declare.
_NOT_COMPILED_FROM_FACTS = ("e-data-record-in-code",)


def _values_of(decoded_object, decoded_page, decoded_file):
    """Returns the attributes the decoder of `decoded_object`'s type, or of
    its page, reads back."""
    if decoded_object.object_id == 0:
        return decoded_page_values(decoded_page, decoded_file).attributes
    return decoded_values(decoded_object, decoded_page, decoded_file).attributes


def _every_e_probe() -> list:
    """Returns each probe of E whose pages are made in memory, once each, but
    _NOT_COMPILED_FROM_FACTS."""
    found = {}
    for module_info in pkgutil.iter_modules(probing.__path__):
        if module_info.name.endswith("_probes"):
            module = importlib.import_module("tools.tft.probing." + module_info.name)
            for probe in getattr(module, "PROBES", []):
                # A probe of an older Nextion Editor, whose `ours` is None,
                # is another's to read.
                if (probe.base == "E" and made_in_memory(probe) and probe.ours is not None
                        and probe.name not in _NOT_COMPILED_FROM_FACTS):
                    found.setdefault(probe.name, probe)
    return list(found.values())


class DecodersOnETest(unittest.TestCase):

    def test_each_object_rebuilt_from_its_values(self):
        rebuilt = 0
        for probe in _every_e_probe():
            with self.subTest(probe.name):
                code, again, count = rebuilt_user_code(probe_facts(probe), _values_of)
                self.assertEqual(again, code)
                rebuilt += count
        # 3450 pages and components, of 917 probes.
        self.assertEqual(rebuilt, 3450)


if __name__ == "__main__":
    unittest.main()
