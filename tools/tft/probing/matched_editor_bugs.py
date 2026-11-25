"""The Nextion Editor's bugs that nxwright matches on purpose, each with the
probes that show it.

In strict Nextion syntax, nxwright does what the Nextion Editor does, even
where that is a bug, so that both compile a project into the same file.
Run the module's probes against each new release of the Nextion Editor, to
see whether the release fixed one of the bugs. When a probe no longer
matches, the release may have fixed its bug, and nxwright should stop
matching it. See tools/tft/README.md, Moving to a new release of the
Nextion Editor, for how to run the probes.

The module takes its probes from other modules. Its name does not end in
"_probes", so that anything reading every probe module, such as
`tools.tft.probe run --all`, skips it and finds each probe only once.
"""
from dataclasses import dataclass

from tools.tft.probing import (device_and_buffer_command_probes, e_probes, f_probes,
                               indirect_probes, k_probes, other_attribute_probes, overlap_probes,
                               p_probes, statement_probes, text_command_probes, text_room_probes)


@dataclass(frozen=True)
class EditorBug:
    """A bug in the Nextion Editor that nxwright matches.

    - what: what the Nextion Editor does, with an example.
    - matched_in: the code that matches the bug, which is the code to
      change once the Nextion Editor fixes the bug. Each item is a pair of
      a file's path, relative to nxwright's folder, and the name of a
      function or a constant in that file.
    - probes: the names of the probes that show the bug.
    """
    what: str
    matched_in: tuple
    probes: tuple


BUGS = [
    EditorBug(
        what="The Nextion Editor compiles the first part of a `for` only up to the parentheses "
             "of its first method call. It writes `for(sys0=fs0.close();sys0<1;sys0++)` with "
             "`sys0=fs0.close` as its first part, so the screen reads the method as an "
             "attribute and does not call it. Whatever follows the call is lost too: "
             "`sys0=fs0.open(t0.txt)+1` becomes `sys0=fs0.open`. nxlang does not have the bug, "
             "because nxwright compiles an nxlang `for` with such a call into its first part, "
             "followed by a `while` loop.",
        matched_in=(("nxwright/tft/instructions/for_statement.py", "_start_as_written"),
                    ("nxwright/testing/editor_machine.py", "_FOR_S_START_UP_TO_A_CALL")),
        probes=("p-file-stream-calls-in-a-for-s-start", "e-file-stream-calls-in-a-for-s-start")),
    EditorBug(
        what="The Nextion Editor does not clear a text's room, the bytes kept for the text in "
             "a page's memory. The bytes that the Nextion Editor does not write keep the values "
             "that an earlier page, or the int variables, put in the same place. For example, "
             "on the Intelligent series, if page0 has the text \"ABCDEFGHIJ\" and page1 has the "
             "text \"Hi\" in the same place, the Nextion Editor writes page1's text as \"Hi\", a "
             "zero byte, then \"DEFGHIJ\".",
        matched_in=(("nxwright/tft/frame.py", "_through_the_scratch_image"),),
        probes=("room-text-over-a-full-page", "room-qr-code-over-the-int-area",
                "p-text-rooms-across-pages")),
    EditorBug(
        what="The Nextion Editor does not check the name or the kind of an attribute reached "
             "through the screen's arrays. `b[1].foo=5` compiles although no component has a "
             "`foo` attribute, and `b[2].val=\"a\"` compiles although it puts text in a number.",
        matched_in=(("nxwright/tft/statements.py", "indirect_covered"),),
        probes=("indirect-assignments",)),
    EditorBug(
        what="The Nextion Editor writes only the low 32 bits of a number that does not fit "
             "in 32 bits, and does not report an error. `sys0=4294967296` sets `sys0` to 0, and "
             "`page 2147483648` is written as page -2147483648.",
        matched_in=(("nxwright/tft/statements.py", "_operand"),),
        probes=("statements-numbers-past-32-bits",)),
    EditorBug(
        what="The Nextion Editor lets a command write to an attribute that an assignment "
             "cannot set. It rejects `s0.id=5` (\"Assignment operation failed\"), but compiles "
             "`strlen t0.txt,s0.id`, which writes to `s0.id`. It also compiles "
             "`ucopy tc0.val,0,2,0`, which writes to a touch capture's `val`.",
        matched_in=(("nxwright/tft/instructions/text_commands.py", "_covered"),
                    ("nxwright/tft/instructions/device_and_buffer_commands.py", "_covered")),
        probes=("text-commands-other-attributes-as-destinations",
                "device-and-buffer-commands-touch-capture-val")),
    EditorBug(
        what="The Nextion Editor accepts a plain number, such as `5`, as the argument "
             "in which a command stores its result, although the command then has nowhere to "
             "store that result. `strlen t1.txt,5` compiles, and so does "
             "`findfile \"sd0/a.txt\",5` on the Intelligent series.",
        matched_in=(("nxwright/tft/instructions/text_commands.py", "_covered"),
                    ("nxwright/tft/instructions/file_commands.py", "_covered")),
        probes=("text-commands-operands", "p-commands-p-has-files-of-any-kind")),
    EditorBug(
        what="Code that reads a component's `aph` compiles on the Basic, Enhanced, and "
             "Discovery series, although their TFT files have no entry for an `aph`. In that "
             "code, the Nextion Editor writes the entry number that an `aph` has on the "
             "Intelligent series, which is the number of the component's first entry plus 6.",
        matched_in=(("nxwright/tft/component_types/__init__.py", "code_entry"),),
        probes=("other-attributes-read", "k-other-attributes-read", "f-other-attributes-read")),
    EditorBug(
        what="The Nextion Editor can have the screen redraw a component together with "
             "components that it does not overlap, and redraw the same one twice. If texts 1 to "
             "4 form a chain in which each one overlaps only its neighbours, the screen redraws "
             "texts 3, 2, 1, 2, and 3 with text 4.",
        matched_in=(("nxwright/tft/overlaps.py", "refreshed"),),
        probes=("overlap-chain-1-2-3-4",)),
]

# The modules that the bugs' probes are in.
_MODULES = (text_room_probes, indirect_probes, statement_probes, text_command_probes,
            device_and_buffer_command_probes, other_attribute_probes, overlap_probes,
            k_probes, f_probes, p_probes, e_probes)


def _probes() -> list:
    """Returns the probes that the bugs list, in the bugs' order."""
    named = {probe.name: probe for module in _MODULES for probe in module.PROBES}
    return [named[name] for bug in BUGS for name in bug.probes]


PROBES = _probes()
