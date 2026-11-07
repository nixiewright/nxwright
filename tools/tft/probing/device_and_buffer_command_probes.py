"""The probes of the device and serial buffer commands
(instructions/device_and_buffer_commands.py): lines of them added to the T
base folder, in strict Nextion syntax, each compared with the blocks the
Nextion Editor wrote, through the statement probes' own ways of cutting
them (statement_probes.py). Run them with
`tools.tft.probe run device_and_buffer_command_probes`.

Most probes in page0's Touch Release event put a text, t0, and two numbers,
n0 and n1, on page0, whose txt and vals the lines use, and declare the int
variable a in program.s. The probe of a touch capture's val puts a number,
n0, and a touch capture, tc0, there instead. Each probe keeps fixtures: the
blocks of the event or of program.s, back to back with their size words.
"""
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (beside_a_text_and_numbers, ours_in_event,
                                            ours_in_program, program_lines, theirs_in_event,
                                            theirs_in_program)
from tools.tft.probing.touch_capture_probes import touch_capture_component

FIXTURES = "device-and-buffer-commands"


PROBES = [
    # Each command, as the vendor's instruction set gives it.
    Probe("device-and-buffer-commands-each", "T", beside_a_text_and_numbers([
        "rest", "touch_j", "code_c", "ucopy n1.val,0,2,0", "udelete 2"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # Each kind of operand, across ucopy's places: int variables of
    # program.s, sys0 and a, a system variable, dim, a number's val, a
    # colour's name, and a txt where it copies to; numbers, a long one,
    # hexadecimal ones of 1 to 4 bytes, int variables, dim, a colour's name,
    # a val, and operands joined by the arithmetic operators where it takes a
    # number; a space after each comma; and attributes other than a txt or a
    # val, n0's x among them, which code may not set on T.
    Probe("device-and-buffer-commands-ucopy-operands", "T", beside_a_text_and_numbers([
        "ucopy sys0,0,2,0", "ucopy n0.val,sys0,sys1,1", "ucopy a,0,1,0", "ucopy n0.val,0,4,1",
        "ucopy n0.val,0x01,2,0", "ucopy n0.val, 0, 2, 0", "ucopy n0.val,1000,2,0",
        "ucopy n0.val,n1.val,2,0", "ucopy t0.txt,0,4,0", "ucopy n0.val,0,a,0x01",
        "ucopy RED,BLACK,2,0", "ucopy dim,0,2,0", "ucopy n0.val,dim,2,0",
        "ucopy n0.val,0x0100,0x000002,0xFFFFFFFF", "ucopy n0.val,sys0+1,2,0",
        "ucopy n0.val,0,1+1,0", "ucopy n0.val,0,2,n1.val-1", "ucopy t0.bco,0,2,0",
        "ucopy n0.val,t0.bco,2,0", "ucopy n0.x,0,2,0"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # A number, a hexadecimal number, and a negative one as ucopy's
    # destination, each written as any operand.
    Probe("device-and-buffer-commands-ucopy-to-numbers", "T", beside_a_text_and_numbers([
        "ucopy 5,0,2,0", "ucopy 0x05,0,2,0", "ucopy -1,0,2,0"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # Each kind of operand as udelete's count: int variables of program.s,
    # sys0 and a, a system variable, dim, a number's val, hexadecimal numbers
    # of 1 and 4 bytes, a long number, a colour's name, a negative one,
    # operands joined by the arithmetic operators, and a text's bco.
    Probe("device-and-buffer-commands-udelete-operands", "T", beside_a_text_and_numbers([
        "udelete sys0", "udelete n0.val", "udelete 0x02", "udelete 1000", "udelete a",
        "udelete BLACK", "udelete -1", "udelete dim", "udelete 0xFFFFFFFF", "udelete sys0+1",
        "udelete n0.val*2", "udelete t0.bco"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # A touch capture's val, which an assignment may not set, as ucopy's
    # destination, and where ucopy and udelete take a number.
    Probe("device-and-buffer-commands-touch-capture-val", "T", with_attributes(
        ["ucopy tc0.val,0,2,0", "ucopy n0.val,tc0.val,2,0", "udelete tc0.val"],
        [number_component(y=60), touch_capture_component(val=5)]),
        ours_in_event, theirs_in_event, FIXTURES),
    # The commands in program.s, before its page 0, without a component's
    # attribute, and with operands joined by the arithmetic operators.
    Probe("device-and-buffer-commands-in-program", "T", program_lines([
        "rest", "touch_j", "code_c", "ucopy sys0,0,2,0", "udelete 1", "ucopy a,sys1,2,1",
        "udelete sys0+1", "ucopy sys0,1+1,2,a*2"],
        ["int a=1"]),
        ours_in_program, theirs_in_program, FIXTURES),
]
