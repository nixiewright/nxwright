"""The bugs in a screen's firmware that nxwright's simulator matches on
purpose, each with the checks that show it on a real screen.

nxwright's simulator does what a real screen does, even where that is a bug,
so that code runs in a test the way it will run on the screen. Each release
of the Nextion Editor brings its own firmware. Run the module's checks on a
screen that runs a new release's firmware, to see whether the release fixed
one of the bugs. When a check's answer differs, the release may have fixed
its bug, and nxwright's simulator should stop matching it. See
tools/screen/README.md, The firmware's bugs, for how to run the checks.

A bug enters the list only after a real screen showed it. Each check
expects what an NX8048P070 sent with the firmware of the Nextion Editor
1.68.2.

The Nextion Editor's own bugs, which show in the TFT file it writes or in
the code it rejects, are in tools/tft/probing/matched_editor_bugs.py.
"""
from dataclasses import dataclass

from tools.screen.ram_probe import END, ENCODING, NEWFILE_THAT_DOES_NOT_FIT, Check, number

# What the screen answers to a read of an attribute that it does not find.
INVALID_VARIABLE = b"\x1a" + END


def text(stored: bytes) -> bytes:
    """Returns the screen's answer to a `get` of a text whose bytes, in the
    project's encoding, are `stored`."""
    return b"\x70" + stored + END


@dataclass(frozen=True)
class FirmwareBug:
    """A bug in a screen's firmware that nxwright's simulator matches.

    - what: what the screen does, with an example.
    - matched_in: the code that matches the bug, which is the code to
      change once the firmware fixes the bug. Each item is a pair of a
      file's path, relative to nxwright's folder, and the name of a
      function in that file.
    - checks: the checks that show the bug (ram_probe.Check).
    - encoding: the encoding that the probe's project must be built in for
      the checks.
    """
    what: str
    matched_in: tuple
    checks: tuple
    encoding: str = ENCODING


BUGS = [
    FirmwareBug(
        what="A file stream's `find` always gives 0, whether the file it is given is there "
             "or not. `sys0=fs0.find(\"ram/a.bin\")` sets `sys0` to 0 even when `ram/a.bin` "
             "is there.",
        matched_in=(("nxwright/testing/editor_machine.py", "_method_call"),),
        checks=(
            Check("A file stream's find gives 0 for a file that is there",
                  ('newfile "ram/a.bin",8', "sys0=7", 'sys0=fs0.find("ram/a.bin")', "get sys0",
                   'delfile "ram/a.bin"'),
                  number(0)),)),
    FirmwareBug(
        what="In `ram/`, a `newfile` whose size does not fit still deletes the existing "
             "file of that name, and does not create a new one. After `newfile \"ram/a.bin\",3`, a "
             "`newfile \"ram/a.bin\",3813` that does not fit leaves no `ram/a.bin`.",
        matched_in=(("nxwright/testing/editor_machine.py", "_ram_command"),),
        checks=(NEWFILE_THAT_DOES_NOT_FIT,)),
    FirmwareBug(
        what="If a condition reads an attribute that its component does not have, the "
             "comparison counts as true, whatever it compares the attribute with. When "
             "`b[2]` has no `bco`, both "
             "`if(b[2].bco==1)` and `if(b[2].bco!=1)` run their blocks. The screen also "
             "answers 0x1A for each read.",
        matched_in=(("nxwright/testing/editor_machine.py", "_condition"),),
        checks=(
            # The Touch Release event of t0 in the probe's project has the two
            # conditions of the example. The first adds 1 to sys1, and the
            # second adds 2.
            Check("A condition that reads an attribute its component lacks counts as true",
                  ("sys1=0", "click t0,0", "get sys1"),
                  INVALID_VARIABLE + INVALID_VARIABLE + number(3)),)),
    FirmwareBug(
        what="A file stream's `read` that would go past the end of its file reads "
             "nothing, but the text it reads into is still cut after its first `start` + "
             "`count` bytes. With "
             "the stream at the end of its file, `fs0.read(t0.txt,2,1)` cuts \"ABCDEF\" to "
             "\"ABC\".",
        matched_in=(("nxwright/testing/editor_machine.py", "_read_or_write"),),
        checks=(
            Check("A file stream's read past the end of its file still cuts the text it "
                  "reads into",
                  ('newfile "ram/a.bin",8', 'fs0.open("ram/a.bin")', "fs0.val=8", 't0.txt="IJ"',
                   "fs0.read(t0.txt,0,1)", "get t0.txt", 't0.txt="ABCDEF"',
                   "fs0.read(t0.txt,2,1)", "get t0.txt", "fs0.close()", 'delfile "ram/a.bin"'),
                  text(b"I") + text(b"ABC")),)),
    FirmwareBug(
        what="In shift-jis, `strlen`, `substr`, and `-=` do not count characters the way "
             "the encoding defines them. A half-width katakana, such as ｱ, is a single byte, "
             "but counts as one character together with the byte after it: \"ｱa\" has a "
             "`strlen` of 1. If that byte is the first half of the next character, "
             "`substr` splits that character. A character whose first byte is 0x81, such as "
             "、, counts as 2. nxwright's simulator counts the same way in gb2312, big5, and "
             "ks_c_5601-1987. For those encodings, this counting was seen in the Nextion "
             "Editor's simulator, and has not been checked on a real screen.",
        matched_in=(("nxwright/project/zi_font.py", "counted_characters"),),
        checks=(
            Check("In shift-jis, strlen counts a half-width katakana and the byte after it "
                  "as one character",
                  ('t0.txt="ｱa"', "strlen t0.txt,sys0", "get sys0"),
                  number(1)),
            Check("In shift-jis, strlen counts a character whose first byte is 0x81 as two",
                  ('t0.txt="、"', "strlen t0.txt,sys0", "get sys0"),
                  number(2)),
            # The answer is ｱ, then the first byte of 亜.
            Check("In shift-jis, substr splits the character after a half-width katakana",
                  ('t0.txt="ｱ亜a"', "substr t0.txt,t1.txt,0,1", "get t1.txt"),
                  text(b"\xb1\x88")),
            # The answer is 亜 alone.
            Check("In shift-jis, -= removes a half-width katakana and the byte after it as "
                  "one character",
                  ('t0.txt="亜ｱa"', "t0.txt-=1", "get t0.txt"),
                  text(b"\x88\x9f")),),
        encoding="shift-jis"),
    FirmwareBug(
        what="`spstr` looks for its separator one byte at a time, so it also finds the "
             "separator in the second byte of a character. In shift-jis, ァ is the bytes "
             "0x83 and 0x40, and 0x40 is \"@\". With the separator \"@\", the first part of "
             "\"ァ@a\" is the byte 0x83 alone. nxwright's simulator does the same in gb2312, "
             "big5, and ks_c_5601-1987. For those encodings, a separator found inside a "
             "character was seen in the Nextion Editor's simulator, and has not been checked "
             "on a real screen.",
        matched_in=(("nxwright/testing/editor_machine.py", "_command"),),
        checks=(
            Check("In shift-jis, spstr finds its separator in the second byte of a character",
                  ('t0.txt="ァ@a"', 'spstr t0.txt,t1.txt,"@",0', "get t1.txt"),
                  text(b"\x83")),),
        encoding="shift-jis"),
]
