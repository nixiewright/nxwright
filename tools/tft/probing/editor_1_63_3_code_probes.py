"""The probes of the Nextion Editor 1.63.3's code on T, K, and P, whose TFT
files nxwright does not write: each is kept as the Editor writes it, compared
with nothing (probe_runner.kept_from_the_editor), so that the decompiler's
tests read the numbers 1.63.3 gives its commands (decompiling/numbers.py,
ResearchNotes/tft/older-editors.md).

Each has the project of a probe of each family's commands in program.s, on
each series: T's on T and on K, which has no such probes of its own for
most families, and P's own on P. Their code lies in program.s, which a test
reads without the rest of the user code. Each leaves out the lines of the
commands 1.63.3 lacks, which it refuses ("Do not support such instruction"
or "Invalid command"). Its fixtures are its user code, in the parts the
frame's probes keep (frame_probes.pieces), never the firmware. Keep them
with the Nextion Editor 1.63.3, from its zip's folder, and an Editor name of
its own, with the Editor tool's Python
(tools\\editor\\build\\venv\\Scripts\\python.exe), from nxwright's
folder:

  set NXWRIGHT_EDITOR=<the folder>\\NextionEditor.exe
  set NXWRIGHT_EDITOR_NAME=agent-b-1633
  <the tool's Python> -m tools.tft.probe keep editor_1_63_3_code_probes --version 1.63.3
"""
from tools.tft.probing import (crc_command_probes, device_and_buffer_command_probes,
                           drawing_probes, frame_probes, p_probes, screen_command_probes,
                           serial_command_probes, statement_probes, text_command_probes,
                           undocumented_command_probes, waveform_command_probes)
from tools.tft.probing.probe_runner import Probe

# The folder of these probes' fixtures, by the Nextion Editor's version,
# which starts each probe's name too.
FIXTURES = "editor-1-63-3"
# T's probes of each family's commands in program.s, by module.
_T_PROJECTS = ((drawing_probes, "drawing-in-program"),
               (screen_command_probes, "screen-commands-in-program"),
               (text_command_probes, "text-commands-in-program"),
               (serial_command_probes, "serial-commands-in-program"),
               (crc_command_probes, "crc-commands-in-program"),
               (device_and_buffer_command_probes, "device-and-buffer-commands-in-program"),
               (waveform_command_probes, "waveform-commands-in-program"),
               (undocumented_command_probes, "undocumented-commands-in-program"))
# P's own, and those of the commands P has and T has not.
_P_PROJECTS = ("p-drawing-in-program", "p-screen-commands-in-program",
               "p-text-commands-in-program", "p-serial-commands-in-program",
               "p-crc-commands-in-program", "p-device-and-buffer-commands-in-program",
               "p-waveform-commands-in-program", "p-undocumented-commands-in-program",
               "p-commands-p-has-in-program", "p-undocumented-commands-p-has-in-program")
# The commands the Nextion Editor 1.63.3 refuses on each series.
_REFUSED = {"T": {"getv"}, "K": {"getv"},
            "P": {"getv", "beep", "meup", "gets", "sets", "beepset"}}


def _kept(name: str, series: str, probe: Probe) -> Probe:
    """Returns the probe named after `name` on `series`, of the lines of
    program.s of `probe`'s change but those of the commands 1.63.3 refuses
    there, as the Nextion Editor 1.63.3 writes it."""
    change = probe.change
    lines = [line for line in change.program if line.split(" ", 1)[0] not in _REFUSED[series]]
    return Probe("%s-%s" % (FIXTURES, name), series,
                 statement_probes.program_lines(lines, change.declarations), None,
                 frame_probes.editor_pieces, FIXTURES)


def _probes() -> list:
    """Returns the probes of _T_PROJECTS on T and on K, and of _P_PROJECTS on
    P."""
    found = []
    for module, name in _T_PROJECTS:
        probe = next(each for each in module.PROBES if each.name == name)
        found += [_kept(name, "T", probe), _kept("k-" + name, "K", probe)]
    named = {probe.name: probe for probe in p_probes.PROBES}
    return found + [_kept(name, "P", named[name]) for name in _P_PROJECTS]


PROBES = _probes()
