"""The release sample: about 40 probes that a pass runs against a new
release of the Nextion Editor, to find where nxwright must change for it
(tools/tft/README.md). On each series, the sample has:
  - a program.s of every command, system variable, and colour the series
    has (release_command_probes.py);
  - the blank project, and one of three pages with int variables and code;
  - one of two timers;
  - probes that together have a component of every type the series has:
    a page of every type that T has, a touch capture among other types,
    and on P and E, a page of P's own types with a place, an audio, and a
    file stream;
  - one of forty pictures and eight fonts, and on P and E, one of an
    animation, a video, and a sound.

Each covers a kind of change that the probes of the releases from 1.60.1 to
1.68.2 found: the numbers of commands and system variables, the layouts,
the "S " blocks that start a timer's code, the blocks a component adds,
and the firmware files (ResearchNotes/tft/older-editors.md). Each compares the
whole file. The sample takes them from other modules, which keep them
matched. Its own name does not end in "_probes", so that what reads every
probe module, as `tools.tft.probe run --all` does, finds each of its probes
once, in its own module.

Run it with --again, with the new release's program named by
NXWRIGHT_EDITOR, and an Editor name of its own:

  <the tool's Python> -m tools.tft.probe run release_sample --again
"""
from tools.tft.probing import (compile_probes, e_probes, f_probes, k_probes, p_probes, page_probes,
                           release_command_probes, timer_probes, touch_capture_probes)

# The probes of every series that the sample takes, by their names on T.
# On another series, its probes module gives each its series' prefix, such
# as "k-".
_TAKEN = ("compile-T-blank", "compile-T-pages-ints-code", "timer-two",
          "page-every-type-on-no-background", "touch-capture-among-the-types-matched",
          "compile-T-forty-pictures-and-eight-fonts")
# The probes of P and E that the sample takes too.
_TAKEN_ON_P = ("place-every-type-at-the-entries-highest", "audio-at-its-defaults",
               "file-stream-at-its-defaults", "media-of-each")
# Where each series' probes are, and their prefix.
_MODULES = {"T": ((compile_probes, timer_probes, page_probes, touch_capture_probes), ""),
            "K": ((k_probes,), "k-"), "P": ((p_probes,), "p-"), "E": ((e_probes,), "e-"),
            "F": ((f_probes,), "f-")}


def _probes() -> list:
    """Returns the sample's probes, series by series, each series' probe of
    commands last."""
    commands = {probe.base: probe for probe in release_command_probes.PROBES}
    found = []
    for series, (modules, prefix) in _MODULES.items():
        named = {probe.name: probe for module in modules for probe in module.PROBES}
        taken = _TAKEN + (_TAKEN_ON_P if series in ("P", "E") else ())
        found += [named[prefix + name] for name in taken] + [commands[series]]
    return found


PROBES = _probes()
