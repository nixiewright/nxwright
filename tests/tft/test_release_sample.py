"""The release sample (tools/tft/probing/release_sample.py): the probes a
pass runs against a new release of the Nextion Editor (tools/tft/README.md). On each
series, it has each kind of probe it lists, every command, system variable,
and colour of the series, and a component of every type the series has.
"""
import importlib
import pkgutil
import re
import unittest

from nxwright.tft import component_types
from tools.tft.probing import release_sample
from tools.tft.probing.component_probes import whole_file
from nxwright.tft.statements import COLOURS, SYSTEM_VARIABLES, series_commands

_SERIES = ("T", "K", "P", "E", "F")
# The kinds of probe the sample has on each series, by the end of their
# names, and the series that have media.
_KINDS = ("compile-T-blank", "compile-T-pages-ints-code", "timer-two",
          "compile-T-forty-pictures-and-eight-fonts", "commands")
_MEDIA = ("P", "E")


def _of(series: str) -> list:
    """Returns the sample's probes of `series`."""
    return [probe for probe in release_sample.PROBES if probe.base == series]


def _types_of(series: str) -> set:
    """Returns the names of the component types that `series` has, such as
    "dual-state-button", as component_types/ gives them."""
    names = set()
    for module in pkgutil.iter_modules(component_types.__path__):
        found = importlib.import_module("nxwright.tft.component_types." + module.name)
        if series in getattr(found, "SERIES", ()):
            names.add(module.name.replace("_", "-"))
    return names


class ReleaseSampleTest(unittest.TestCase):

    def test_each_kind_on_each_series(self):
        for series in _SERIES:
            names = [probe.name for probe in _of(series)]
            kinds = _KINDS + (("media-of-each",) if series in _MEDIA else ())
            with self.subTest(series=series):
                for kind in kinds:
                    self.assertTrue(any(name.endswith(kind) for name in names), kind)

    def test_each_compares_the_whole_file(self):
        for probe in release_sample.PROBES:
            with self.subTest(probe.name):
                self.assertIs(probe.ours, whole_file)

    def test_a_component_of_every_type(self):
        for series in _SERIES:
            types = set()
            for probe in _of(series):
                text = "".join(component for component in
                               getattr(probe.change, "components", ()) or ()
                               if isinstance(component, str))
                types.update(re.findall(r'type = "([\w-]+)"', text))
            with self.subTest(series=series):
                self.assertEqual(types, _types_of(series))

    def test_every_command_system_variable_and_colour(self):
        for series in _SERIES:
            probe = next(probe for probe in _of(series) if probe.name.endswith("commands"))
            lines = list(probe.change.program) + probe.change.code.splitlines()[1:]
            words = {re.match(r"\s*([A-Za-z_]\w*)", line).group(1) for line in lines}
            with self.subTest(series=series):
                self.assertEqual(set(series_commands(series)) - words, set())
                read = {line[len("sys0="):] for line in probe.change.program
                        if line.startswith("sys0=")}
                self.assertEqual(set(SYSTEM_VARIABLES[series]) | set(COLOURS[series]), read)

    def test_names_are_unique(self):
        names = [probe.name for probe in release_sample.PROBES]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
