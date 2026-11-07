"""The probes of the CRC commands (instructions/crc_commands.py): lines of
them added to the T base folder, in strict Nextion syntax, each compared
with the blocks the Nextion Editor wrote, through the statement probes' own
ways of cutting them (statement_probes.py). Run them with
`tools.tft.probe run crc_command_probes`.

The probes in page0's Touch Release event put a text, t0, and two numbers,
n0 and n1, on page0, whose txt and vals the lines use, and declare the int
variable a in program.s. Each probe keeps fixtures: the blocks of the event
or of program.s, back to back with their size words.
"""
from functools import partial

from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (beside_a_text_and_numbers, event_lines,
                                            ours_in_event, ours_in_program, program_lines,
                                            theirs_in_event, theirs_in_program)

FIXTURES = "crc-commands"

# The probes' page, where n0's val is 7.
_beside_n0_of_7 = partial(beside_a_text_and_numbers, n0_val=7)
# Lines of each command with system variables, those of table 4, as dim,
# and of table 8, as bkcmd, in each place a value goes, and in a sum; and
# one with a colour's name.
_SYSTEM_VARIABLE_LINES = [
    "crcrest 1,dim", "crcrest bkcmd,crcval", "crcrest 1,dim+1", "crcputs dim,1",
    "crcputs baud,4", "crcputs t0.txt,dims", "crcputs WHITE,2", "crcputu thsp,thup",
    "crcputu rand,sendxy", "crcputu 0,usize"]


PROBES = [
    # Each command, as the vendor's instruction set gives it.
    Probe("crc-commands-each", "T", _beside_n0_of_7([
        "crcrest 1,0xFFFF", "crcputs t0.txt,0", "crcputh 31 32 33", "crcputu 0,3"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # Each kind of operand, across the commands' places: numbers, long and
    # negative ones, hexadecimal numbers of 1 to 4 bytes, int variables, a
    # colour, a number's val, a text, an empty one, a long one, and a txt as
    # crcputs' value, and a space after a comma; then crcval read into sys0.
    Probe("crc-commands-operands", "T", _beside_n0_of_7([
        "crcrest 1,65535", "crcrest 1,0", "crcrest 1,-1", "crcrest 2,0xFFFF", "crcrest 1,0x00",
        "crcrest 1,0x12", "crcrest 1,0x0123", "crcrest 1,0xfFfF", "crcrest 1,0X12",
        "crcrest 1,0x010000", "crcrest 1,0xFFFFFFFF", "crcrest 0x01,0xFFFF", "crcrest a,sys0",
        "crcrest 1,n0.val", "crcrest 1, 0xFFFF", "crcputs n0.val,2", 'crcputs "abc",0',
        "crcputs sys0,4", "crcputs t0.txt,sys1", "crcputs n0.val,n1.val", "crcputs 1000,0",
        "crcputs -5,0", "crcputs 0x31,1", "crcputs RED,a", "crcputs t0.txt, 0",
        "crcputs t0.txt,0x02", "crcputs t0.txt,RED", 'crcputs "",0',
        'crcputs "%s",0' % ("a" * 100), "crcputu sys0,sys1", "crcputu 0,n0.val",
        "crcputu n0.val,1", "crcputu a,0x02", "crcputu 0x01,0x02", "crcputu RED,0",
        "crcputu 0, 3", "sys0=crcval"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # crcputh's bytes, kept as written: lowercase and uppercase, and 1, 16,
    # 17, and 64 bytes.
    Probe("crc-commands-bytes", "T", _beside_n0_of_7([
        "crcputh 0d 0a", "crcputh FF", "crcputh " + " ".join("%02x" % n for n in range(16)),
        "crcputh " + " ".join("%02X" % n for n in range(17)),
        "crcputh " + " ".join("%02x" % n for n in range(64))]),
        ours_in_event, theirs_in_event, FIXTURES),
    # crcputh's argument of other characters than hexadecimal bytes between
    # spaces, kept as written.
    Probe("crc-commands-bytes-of-other-characters", "T", _beside_n0_of_7([
        "crcputh 3G", "crcputh 0d0a"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # crcputh's argument of a backslash and a letter, in strict Nextion
    # syntax, which nxwright's build writes as a backspace, kept as written.
    Probe("crc-commands-bytes-of-a-control-character", "T",
          event_lines(["crcputh a\\b"]), ours_in_event, theirs_in_event, FIXTURES),
    # The commands in program.s, before its page 0, without a component's
    # attribute.
    Probe("crc-commands-in-program", "T", program_lines([
        "crcrest 1,0xFFFF", 'crcputs "abc",0', "crcputs sys0,2", "crcputh 31 32", "crcputu 0,3",
        "crcrest sys0,sys1", "crcputu sys0,0x01"]),
        ours_in_program, theirs_in_program, FIXTURES),
    # System variables, of both tables, and a colour, in each place, in an
    # event and in program.s.
    Probe("crc-commands-system-variables", "T", _beside_n0_of_7(_SYSTEM_VARIABLE_LINES),
          ours_in_event, theirs_in_event, FIXTURES),
    Probe("crc-commands-system-variables-in-program", "T", program_lines(
        [line for line in _SYSTEM_VARIABLE_LINES if "t0." not in line]),
        ours_in_program, theirs_in_program, FIXTURES),
]
