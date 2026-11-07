"""call and return, and the project's macros, on the T, K, P, E, and F series,
as the Nextion Editor 1.68.2 writes them (ResearchNotes/tft/macros.md). `call m0`
runs the project's macro m0, by its name, which may hold spaces, as in
`call my name`. `return` ends the run of code it is in: a macro, an event,
or program.s.

A call is a "J " block of the place of the block after its macro's "S "
block (label_numbers.py): `call m1`, with m1's "S " block at 0xb7, is
4a 20 03 c2 00 00 00. It takes a number of the counter, as a goto does.
The statement encoder gives it unwritten (label_numbers.CallBlock), and the
frame writes it once it lays out the macros (frame._macros). `return` is a
0 word, as one ends every run of code.

nxwright's build refuses a call of a macro the project lacks, as the
Nextion Editor refuses it.

nxwright takes a macro's name of ASCII letters, digits, underscores, and
spaces, starting with a letter or an underscore and not ending with a
space (macros_source.MACRO_NAME), and refuses any other as it reads a
project's macros. The macros' table gives the CRC of the name's bytes.
"""
from nxwright.tft.label_numbers import CallBlock, call_of
from nxwright.tft.matching import Rule
from nxwright.tft.statements import StatementError

# The series whose calls and macros the encoder and the frame write.
_SERIES = ("T", "K", "P", "E", "F")
RETURN = "return"


def starts_statement(line: str) -> bool:
    """Whether `line` is a call or `return`, each a statement of one line."""
    return call_of(line) is not None or line.strip(" \t") == RETURN


def encode_statement(lines: list, start: int, place, context, encode_run) -> tuple:
    """Returns the block of the call or the `return` at lines[start], a
    call's unwritten, and the index of the next line
    (instructions/__init__.py). Raises StatementError on a series whose
    calls the encoder does not write."""
    series = context.project.settings.model.series
    if series not in _SERIES:
        raise StatementError("the %s series' call and return are not encoded yet" % series)
    macro = call_of(lines[start])
    return [b"" if macro is None else CallBlock(macro)], start + 1


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = _SERIES

MATCHED = [
    Rule("code", None, "call of a macro, by its name, and return, in program.s, a macro, or "
         "an event; on T, K, P, E, and F", lambda need: starts_statement(need.value)),
    Rule("macro", None, "a macro, its blocks after program.s's: an \"S \" block of its number, "
         "its lines' blocks, as program.s's, and a 0 word; and its entry in the macros' table, "
         "the CRC of its name and its place, sorted by the CRC, before the page index; on T, "
         "K, P, E, and F", lambda need: True),
]
