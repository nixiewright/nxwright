"""The probes of the Nextion Editor 1.65.1 on F, whose TFT files nxwright does
not write: each is kept as the Editor writes it, compared with nothing
(probe_runner.kept_from_the_editor), so that the decompiler's tests read
the numbers F of 1.65.1 gives its commands, system variables, and colours
(decompiling/numbers.py, ResearchNotes/tft/older-editors.md).

Each has the project of a probe of F (f_probes.py): the blank project, the
system variables, the colours, each family's probe of each command, a
timer, a slider, and a scrolling text, and one of its own, of F's own
commands but beep and cfgpio, which 1.65.1 lacks, with sets given 2
arguments, as 1.65.1 takes no other number. Its fixtures are its user code,
in the parts the frame's probes keep (frame_probes.pieces), never the
firmware. Keep them with the Nextion Editor 1.65.1, from its zip's folder,
and an Editor name of its own, with the Editor tool's Python
(tools\\editor\\build\\venv\\Scripts\\python.exe), from nxwright's
folder:

  set NXWRIGHT_EDITOR=<the folder>\\NextionEditor.exe
  set NXWRIGHT_EDITOR_NAME=agent-b-1651
  <the tool's Python> -m tools.tft.probe keep editor_1_65_1_probes --version 1.65.1
"""
from tools.tft.probing import f_probes, frame_probes, statement_probes
from tools.tft.probing.probe_runner import Probe

# The folder of these probes' fixtures, by the Nextion Editor's version,
# which starts each probe's name too.
FIXTURES = "editor-1-65-1"
# The probes of F whose projects these take.
_PROJECTS = ("f-compile-T-blank", "f-statements-system-variables", "f-statements-colours",
             "f-screen-commands-each", "f-drawing-each-command", "f-text-commands-each",
             "f-serial-commands-each", "f-crc-commands-each", "f-device-and-buffer-commands-each",
             "f-waveform-commands-each", "f-undocumented-commands-each", "f-timer-one",
             "f-slider-one", "f-scrolling-text-one")
# F's own commands that 1.65.1 has, in program.s.
_OWN_COMMANDS = ["wepo 5,0", "repo sys0,0", "cuts 0,0,0,0,0,0,0", "gets 0,0", "sets 1,2",
                 "xnum 0,0,0,0,0,0,0,0,0,0", "piccolor 0,0,0,sys0"]


def _kept(name: str, change) -> Probe:
    """Returns the probe named after `name` on F, which makes `change` to
    F's base folder, as the Nextion Editor 1.65.1 writes it."""
    return Probe("%s-%s" % (FIXTURES, name), "F", change, None, frame_probes.editor_pieces,
                 FIXTURES)


def _probes() -> list:
    """Returns a probe of each project of _PROJECTS, and the probe of F's own
    commands."""
    named = {probe.name: probe for probe in f_probes.PROBES}
    return ([_kept(name, named[name].change) for name in _PROJECTS]
            + [_kept("f-own-commands", statement_probes.program_lines(_OWN_COMMANDS))])


PROBES = _probes()
