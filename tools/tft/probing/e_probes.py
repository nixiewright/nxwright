"""The E series' probes: each of P's probes (p_probes.py) but the
thermostat example's, on the E base folder (probes/E), NX4848E040 at 0
degrees, compared as a whole file, as a series' probes do. Run them with
`tools.tft.probe run e_probes`.

E writes the user code as P does, and differs from P in its screen and its
firmware alone (ResearchNotes/tft/e-series.md), which header 1 and the section
give. So the probes of the blank project and of three pages keep the whole
compile's fixtures, made on zeros for the firmware, as on P. The others
keep none: P's fixtures and the series comparison tests guard their user code.
"""
from dataclasses import replace

from tools.tft.probing import p_probes
from tools.tft.probing.component_probes import editor_file, whole_file
from tools.tft.probing.probe_runner import Probe

FIXTURES = "e"
_KEEPING = {"p-compile-T-blank", "p-compile-T-pages-ints-code"}


def _on_e(probe: Probe) -> Probe:
    """Returns P's probe `probe` on the E base folder, compared as a whole
    file, keeping the whole compile's fixtures when it is one of
    _KEEPING."""
    keeping = probe.name in _KEEPING
    return replace(probe, name="e-" + probe.name[len("p-"):], base="E", ours=whole_file,
                   theirs=editor_file, fixtures=FIXTURES if keeping else None,
                   kept=probe.kept if keeping else None)


# All but the thermostat example's, whose own app.toml gives P's screen, so
# on E's base folder it would build P's project again.
PROBES = [_on_e(probe) for probe in p_probes.PROBES if probe is not p_probes.THERMOSTAT_PROBE]
