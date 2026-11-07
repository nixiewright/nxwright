"""The probes of the project's macros, call, and return
(instructions/call_statement.py, frame._macros): projects with a
`macros.nx` added to the T base folder, beside the text t0 and the numbers
n0 and n1 of statement_probes.beside_a_text_and_numbers, each compared
with the Nextion Editor's whole file, as the macros' table and header 1's
0x58 lie outside the blocks. Run them with `tools.tft.probe run macro_probes`.

The probe of calls and the one of labels keep the user code as fixtures.
"""
from dataclasses import dataclass
from pathlib import Path

from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ProgramChange, beside_a_text_and_numbers

FIXTURES = "macros"


def macros_text(macros) -> str:
    """Returns the text of macros.nx of `macros`, [(name, [line])], each
    under its heading, its lines indented by two spaces."""
    return "".join("macro %s:\n%s" % (name, "".join("  %s\n" % line for line in lines))
                   for name, lines in macros)


@dataclass(frozen=True, eq=False)
class MacrosChange(ProgramChange):
    """A statement_probes.ProgramChange that also writes `macros`, ((name,
    (line, ...)), ...), in the folder's macros.nx, after the rest. Without
    macros, it writes no macros.nx, as a folder without macros has none. A
    unit test reads the macros' text (macros_text) as it reads the rest, to
    make the same project in memory (tests/tft/unit_inputs.py)."""
    macros: tuple = ()

    @property
    def macros_text(self):
        """The text of the macros.nx it writes; None when it writes none."""
        return macros_text(self.macros) if self.macros else None

    def __call__(self, folder: Path):
        super().__call__(folder)
        if self.macros:
            (Path(folder) / "macros.nx").write_text(self.macros_text, encoding="utf-8")


def with_macros(macros: list, event: list, program: list = ()) -> MacrosChange:
    """Returns a probe's change: gives page0's Touch Release event the lines
    `event`, beside t0, n0, and n1, adds the lines `program` to program.s,
    and writes `macros`, [(name, [line])], in the folder's macros.nx
    (MacrosChange)."""
    beside = beside_a_text_and_numbers(event)
    return MacrosChange(tuple(program), beside.declarations, beside.components, beside.code,
                        tuple((name, tuple(lines)) for name, lines in macros))


PROBES = [
    # Calls from an event, from program.s, and from a macro; a return in the
    # middle of a macro; a macro without lines; and a name with a space.
    Probe("macros-called", "T", with_macros(
        [("first", ["sys0=1", "call second", "sys0=2"]),
         ("second", ["sys1=1", "return", "sys1=2"]), ("empty", []),
         ("with space", ["sys2=1"])],
        ["call first", "call empty", "sys2=3", "call with space"], ["call second"]),
        whole_file, editor_file, FIXTURES, user_code_kept),
    # The table's order: the CRCs of these names fall the other way from the
    # macro tab's order.
    Probe("macros-sorted-by-crc", "T", with_macros(
        [("delta", ["sys0=1"]), ("alpha", ["sys0=2"]), ("beta", ["sys0=3"]),
         ("gamma", ["sys0=4"])], ["call gamma"]),
        whole_file, editor_file),
    # The counter across program.s, the macros, and the event: labels,
    # gotos, and calls in each.
    Probe("macros-labels", "T", with_macros(
        [("m0", ["sys0=3"]), ("m1", ["ml:", "sys1=4", "goto ml"]), ("m2", ["sys2=5"])],
        ["call m1", "el:", "sys2=6", "goto el"], ["pl:", "sys0=1", "call m0"]),
        whole_file, editor_file, FIXTURES, user_code_kept),
    # Lines of each kind in a macro: assignments, a hexadecimal number, an
    # int variable, commands with a colour and an ID, bytes, a reference
    # through the screen's arrays, a text with each escape and a character
    # past ASCII, a comment, and if, while, and for, a return in an if's
    # body.
    Probe("macros-lines", "T", with_macros(
        [("kinds", ["sys0=0x10", "sys1=sys0*2+a", "cls RED", "vis 1,0", "printh 0d 0a",
                    'p[0].b[1].txt="x"', 'print "\\\\\\"\\ré"', "// a comment",
                    "if(sys0>1)", "{", "return", "}", "while(sys1<10)", "{", "sys1++", "}",
                    "for(sys2=0;sys2<3;sys2++)", "{", "sys0+=sys2", "}", "sys0=5"])],
        ["call kinds"]),
        whole_file, editor_file),
    # return without macros, in program.s and in an event.
    Probe("return-in-program-s-and-an-event", "T", with_macros(
        [], ["sys1=1", "return", "sys1=2"], ["sys0=1", "return", "sys0=2"]),
        whole_file, editor_file),
    # A component of a page by the page's name, which a macro takes as
    # program.s does, written as its text: set, given, and in a condition. A
    # macro has no page of its own, so it reaches into page0, with the text
    # t0 and the numbers n0 and n1 of with_macros.
    Probe("macros-page-array", "T", with_macros(
        [("m1", ["page0.b[2].val=5", "sys0=page0.b[sys0].val", "page0.b[a].val=1",
                 "if(page0.b[2].val==1)", "{", "sys0=1", "}"])], ["call m1"]),
        whole_file, editor_file, FIXTURES, user_code_kept),
]
