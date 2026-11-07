"""The probes of the commands of the EEPROM and the GPIO pins that K has and
T has not (instructions/eeprom_and_gpio_commands.py): wepo, repo, wept,
rept, and cfgpio, on the K base folder, in page0's Touch Release event
beside t0, n0, and n1, with numbers, variables, a val, a txt, a text, and a
component; then in program.s. Run them with `tools.tft.probe run
eeprom_and_gpio_probes`.

Each compares the blocks of page0's Touch Release event, or of program.s,
alone, keeping them as its fixtures (statement_probes.py gives both).
"""
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (ours_in_event, ours_in_program, program_lines,
                                            theirs_in_event, theirs_in_program)

FIXTURES = "eeprom-and-gpio-commands"

PROBES = [
    # Each command with each kind of operand it takes. A number is repo's
    # destination too, which the Nextion Editor compiles.
    Probe("eeprom-and-gpio-each", "K", with_attributes([
        "wepo 5,0", "wepo sys0,10", "wepo n0.val,20", "wepo t0.txt,30", 'wepo "abc",40',
        "repo sys0,0", "repo n0.val,10", "repo t0.txt,20", "repo 5,0", "wept 0,10",
        "wept sys0,sys1", "rept 0,10", "rept sys0,sys1", "cfgpio 0,0,0", "cfgpio 1,1,0",
        "cfgpio 4,3,0", "cfgpio 2,1,n0"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # cfgpio's component as an ID past 255, and in hexadecimal, each written
    # as any number argument is.
    Probe("eeprom-and-gpio-cfgpio-components-of-other-forms", "K", with_attributes([
        "cfgpio 1,1,256", "cfgpio 2,1,0x01", "cfgpio 3,1,1000", "cfgpio 1,1,n0.val",
        "cfgpio 2,1,t0.bco"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # A variable as cfgpio's component, written as its operand.
    Probe("eeprom-and-gpio-cfgpio-of-a-variable", "K", with_attributes(["cfgpio 1,1,sys0"]),
          ours_in_event, theirs_in_event),
    # A text as repo's destination, written as any operand.
    Probe("eeprom-and-gpio-repo-to-a-text", "K", with_attributes(['repo "a",0']),
          ours_in_event, theirs_in_event, FIXTURES),
    Probe("eeprom-and-gpio-in-program-s", "K", program_lines([
        "wepo 5,0", "repo sys0,0", "rept 0,10", "wept sys0,sys1", "cfgpio 0,0,0"]),
        ours_in_program, theirs_in_program, FIXTURES),
]
