"""The waveform commands' probes (instructions/waveform_commands.py): add,
addt, and cle, added to the T base folder in strict Nextion syntax, in
page0's Touch Release event beside the waveform s0 and the number n0, and
in program.s. Run them with `tools.tft.probe run waveform_command_probes`.

Each compares the blocks of its lines, as the statement probes do
(statement_probes.py), and keeps them as its fixture.
"""
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (ProgramChange, ours_in_event, ours_in_program,
                                            program_lines, theirs_in_event, theirs_in_program,
                                            touch_release_code)
from tools.tft.probing.waveform_probes import waveform_component

FIXTURES = "waveform-commands"


def _beside_a_waveform(lines: list) -> ProgramChange:
    """Returns a change that gives page0's Touch Release event `lines`, and
    puts the waveform s0 and the number n0 on page0."""
    return ProgramChange(code=touch_release_code(lines),
                         components=(waveform_component(), number_component(y=150)))


PROBES = [
    # Each command, its ID as s0.id and as a number, and a waveform's id
    # read into a variable.
    Probe("waveform-commands-each", "T", _beside_a_waveform([
        "add s0.id,0,10", "add 1,0,sys0", "add s0.id,1,255", "addt s0.id,0,100",
        "cle s0.id,0", "cle 1,255", "sys0=s0.id"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # Each kind of operand in each place: a number's val, system variables,
    # a long number, a negative one, and a space after each comma.
    Probe("waveform-commands-operands", "T", _beside_a_waveform([
        "add s0.id,0,n0.val", "add s0.id,sys0,sys1", "add sys0,0,10", "add s0.id,0,1000",
        "add s0.id,0,-5", "add s0.id, 0, 10", "addt s0.id,0,sys0", "addt 1,1,1000",
        "cle s0.id,sys0", "cle sys0,255", "cle s0.id, 255"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # The commands in program.s, before its page 0, their IDs as numbers and
    # variables.
    Probe("waveform-commands-in-program", "T", program_lines([
        "add 1,0,10", "add sys0,sys1,sys2", "addt 1,0,100", "cle 1,255", "cle sys0,0"]),
        ours_in_program, theirs_in_program, FIXTURES),
]
