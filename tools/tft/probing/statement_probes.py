"""The statement encoder's probes: lines of code added to the T base folder,
in strict Nextion syntax, a few lines of one kind a probe. Each compares the
blocks the encoder gives the lines with those the Nextion Editor wrote, and
keeps them as one fixture, its blocks back to back with their size words.

In program.s, the lines go before the base's `page 0`. The Nextion Editor
writes the lines' blocks, in order, then a `page 0` and a 0 word of its own,
which the probes leave out. In an event, the lines are those of the page's
Touch Release event, whose blocks follow the block holding the event's
name, up to a 0 word.

Run them with `tools.tft.probe run statement_probes`.
"""
from dataclasses import dataclass
from pathlib import Path

from tools.tft.probing.component_probes import with_components
from nxwright.tft.matching import code_lines
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe, ProbeMismatch
from nxwright.source.source_folder import NEXTION, app_text, parse_app
from nxwright.tft.compile_context import CompileContext
from nxwright.tft.statements import SYSTEM_VARIABLES, COLOURS, CodePlace, encode_code
from tools.tft.probing.text_probes import text_component
from nxwright.tft.tft_file import TftFileError, encode_blocks, read_tft

_BASE_DECLARATION = "int sys0=0,sys1=0,sys2=0"
# The Nextion Editor's own end of program.s: a `page 0`, then a 0 word.
_PROGRAM_END = [b"\x09\x0b\x04\x30", b""]
_FIXTURES = "statements"
_EVENT = "up"


def strict_app(text: str) -> str:
    """Returns app.toml's text `text`, its code made strict Nextion syntax
    from nxlang, the base folders' language."""
    return app_text(dict(parse_app(text), language=NEXTION), written=text)


def touch_release_code(lines: list) -> str:
    """Returns the text of page0.nx that gives page0's Touch Release event
    `lines`."""
    return "on page0.%s:\n%s" % (_EVENT, "".join("  %s\n" % line for line in lines))


def _strict(folder: Path):
    """Makes the folder's code strict Nextion syntax, so that the project
    holds each line as written."""
    app = folder / "app.toml"
    app.write_text(strict_app(app.read_text(encoding="utf-8")), encoding="utf-8")


def program_text(text: str, lines: tuple = (), declarations: tuple = (),
                 ints: tuple = ()) -> str:
    """Returns program.nx's text `text` with `declarations` after the base's
    own, as the Nextion Editor refuses one after any code, and `lines`
    before the base's `page 0`. `ints` are int variables, each such as
    "a=5", added to the base's own declaration, after sys2. A unit test's
    program.s in memory is made the same way (tests/tft/unit_inputs.py)."""
    declaration = ",".join([_BASE_DECLARATION, *ints])
    text = text.replace(_BASE_DECLARATION, "\n".join([declaration, *declarations]))
    return text.replace("page 0", "\n".join([*lines, "page 0"]))


@dataclass(frozen=True, eq=False)
class ProgramChange:
    """A probe's change that makes the folder's code strict Nextion syntax,
    gives program.nx the lines `program` and `declarations` (program_text),
    and gives page0 `components`, each in a page file's form, and the event
    code `code`. A unit test reads what it adds, as it reads a
    component_probes.ComponentsChange's, to make the same pages and
    program.s in memory (tests/tft/unit_inputs.py), their code strict. Two
    changes are equal only if they are the same one, as two functions are."""
    program: tuple = ()
    declarations: tuple = ()
    components: tuple = ()
    code: str = ""
    # The page it puts the components on, named as a ComponentsChange names
    # it. Its code is strict Nextion syntax.
    page = "page0"
    strict = True

    def __call__(self, folder: Path):
        _strict(folder)
        program = folder / "program.nx"
        program.write_text(program_text(program.read_text(encoding="utf-8"), self.program,
                                        self.declarations), encoding="utf-8")
        if self.code:
            (folder / "pages" / "page0.nx").write_text(self.code, encoding="utf-8")
        if self.components:
            with_components(*self.components)(folder)


def program_lines(lines: list, declarations: list = ()) -> ProgramChange:
    """Returns a probe's change: adds `declarations` after the base's own,
    as the Nextion Editor refuses one after any code, and `lines` before the
    base's `page 0` (ProgramChange)."""
    return ProgramChange(tuple(lines), tuple(declarations))


def event_lines(lines: list, declarations: list = ()) -> ProgramChange:
    """Returns a probe's change: gives page0's Touch Release event `lines`,
    and adds `declarations` to program.s after the base's own
    (ProgramChange)."""
    return ProgramChange(declarations=tuple(declarations), code=touch_release_code(lines))


def beside_a_text_and_numbers(lines: list, n0_val: int = 0) -> ProgramChange:
    """Returns a probe's change: gives page0's Touch Release event `lines`,
    declares `int a=1` in program.s, and puts on page0 the text t0, whose
    txt is "abc", the number n0, whose val is `n0_val`, and the number n1
    (ProgramChange)."""
    return ProgramChange(declarations=("int a=1",), code=touch_release_code(lines),
                         components=(text_component("t0", txt="abc"),
                                     number_component("n0", y=60, val=n0_val),
                                     number_component("n1", y=110)))


def ours_in_program(project) -> dict:
    """Returns the blocks the encoder gives program.s's lines in the built
    `project`, as the piece "program-s"."""
    from nxwright.tft.project import Project
    return program_blocks(Project.from_file(project))


def program_blocks(project) -> dict:
    """Returns the blocks the encoder gives program.s's lines in `project`,
    a Project, as the piece "program-s"."""
    blocks = encode_code(code_lines(project, project.program), CodePlace(),
                         CompileContext(project))
    return {"program-s": encode_blocks(blocks)}


def kept_blocks(probe: Probe, project) -> dict:
    """Returns the blocks the encoder gives the lines whose blocks a probe of
    the encoder keeps as its fixture, in `project`, a Project: program.s's
    lines for a probe that keeps them (ours_in_program), else the lines of
    page0's Touch Release event. A probe on P compares the whole file, but
    keeps the same blocks (its kept)."""
    kept = probe.kept or probe.ours
    return (program_blocks if kept is ours_in_program else event_blocks)(project)


def theirs_in_program(data: bytes) -> dict:
    """Returns program.s's blocks cut from the Nextion Editor's file, its own
    `page 0` and 0 word left out, as the piece "program-s". Raises
    ProbeMismatch when they do not end so."""
    code = _user_code(data)
    blocks = [block for block, part in zip(code.blocks, code.block_parts())
              if part == "program.s"]
    if blocks[-len(_PROGRAM_END):] != _PROGRAM_END:
        raise ProbeMismatch("program.s's blocks do not end with the Nextion Editor's own "
                            "page 0 and 0 word")
    return {"program-s": encode_blocks(blocks[:-len(_PROGRAM_END)])}


def ours_in_event(project) -> dict:
    """Returns the blocks the encoder gives the lines of page0's Touch Release
    event in the built `project`, as the piece "event"."""
    from nxwright.tft.project import Project
    return event_blocks(Project.from_file(project))


def event_blocks(project) -> dict:
    """Returns the blocks the encoder gives the lines of page0's Touch Release
    event in `project`, a Project, as the piece "event"."""
    from nxwright.project.page_block import Event
    page = project.pages[0].objects[0]
    lines = next(item.lines for item in page.items
                 if isinstance(item, Event) and item.name == _EVENT)
    blocks = encode_code(code_lines(project, b"\n".join(lines)), CodePlace(0, "page0", _EVENT),
                         CompileContext(project))
    return {"event": encode_blocks(blocks)}


def theirs_in_event(data: bytes) -> dict:
    """Returns the blocks of page0's Touch Release event cut from the Nextion
    Editor's file, as the piece "event". Raises ProbeMismatch when page 0
    holds no such event."""
    code = _user_code(data)
    blocks = [block for block, part in zip(code.blocks, code.block_parts())
              if part == "page 0"]
    if _EVENT.encode("ascii") not in blocks:
        raise ProbeMismatch("page 0's blocks hold no block naming the event %s" % _EVENT)
    start = blocks.index(_EVENT.encode("ascii")) + 1
    end = blocks.index(b"", start)
    return {"event": encode_blocks(blocks[start:end])}


def _user_code(data: bytes):
    try:
        return read_tft(data, "the Nextion Editor's file").user_code
    except TftFileError as error:
        raise ProbeMismatch(str(error)) from None


def _program_probe(name: str, lines: list, declarations: list = ()) -> Probe:
    return Probe(name, "T", program_lines(lines, declarations), ours_in_program,
                 theirs_in_program, _FIXTURES)


def _printh(count: int) -> str:
    """Returns a printh line of `count` bytes: 00, 01, and so on."""
    return "printh " + " ".join("%02x" % (number % 256) for number in range(count))


_OPERATORS = ("+", "-", "*", "/", "%", "&", "|", "^", "<<", ">>")
PROBES = [
    # A new project's own program.s: baud, dim, recmod, printh, and page.
    _program_probe("statements-new-project", []),
    _program_probe("statements-numbers", [
        "sys0=%s" % number for number in
        ("0", "5", "-5", "-99", "00", "007", "999", "1000", "0007", "-999", "-1000", "9600",
         "65535", "65536", "2147483647", "-2147483648")]),
    _program_probe("statements-program-variables",
                   ["sys0=a", "sys0=b", "a=sys2", "b=a+b"], ["int a=1,b=2"]),
    _program_probe("statements-system-variables",
                   ["sys0=%s" % name for name in sorted(SYSTEM_VARIABLES["T"])]
                   + ["%s=sys0" % name for name in sorted(SYSTEM_VARIABLES["T"])]),
    _program_probe("statements-colours", ["sys0=%s" % name for name in sorted(COLOURS["T"])]),
    _program_probe("statements-operators",
                   ["sys0=sys1%s2" % operator for operator in _OPERATORS]
                   + ["sys0+=1", "sys0-=1", "sys0+=sys1*2", "sys0-=dim+1", "sys0++", "sys0--",
                      "sys0=sys1+sys2-dim*3", "dim=sys0/2", "page 0", "dim++", "dim--",
                      "dim+=1", "a++", "a-=sys0", "sys0=RED+1", "sys0=1000+sys1",
                      "sys0=sys1-1000"], ["int a=1"]),
    # printh's bytes as written, in either case, from 1 byte to 16.
    _program_probe("statements-printh", [
        "printh ff", "printh FF", "printh 0A 0b",
        "printh 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16"]),
    # printh of 17, 64, and 253 bytes, the most a line of 767 characters
    # holds, in program.s and in an event.
    _program_probe("statements-printh-long", [_printh(17), _printh(64), _printh(253)]),
    # printh's argument of other characters than hexadecimal bytes, kept
    # as written, in strict Nextion syntax: a quote and an attribute among
    # them, beside the text t0 and the number n0.
    Probe("statements-printh-of-other-characters", "T", beside_a_text_and_numbers(
        ["printh 3G", 'printh "a"', "printh n0.val"]), ours_in_event, theirs_in_event,
        _FIXTURES),
    Probe("statements-printh-long-in-an-event", "T",
          event_lines([_printh(17), _printh(253)]), ours_in_event, theirs_in_event, _FIXTURES),
    # Each arithmetic operator's own assigning operator, such as *= and <<=,
    # and a minus after one, which starts a number.
    _program_probe("statements-compound-assignments", [
        "sys0*=10", "sys0/=-2", "sys0%=3", "sys0&=1", "sys0|=2", "sys0^=3", "sys0<<=1",
        "sys0>>=1", "sys0+=-1", "sys0-=-5", "sys0*=-1000", "sys0 *= 2", "a*=sys0+1", "dim*=2"],
        ["int a=1"]),
    # The same on attributes, through the screen's arrays, and as a for's
    # step, beside the text t0 and the numbers n0 and n1.
    Probe("statements-compound-assignments-in-an-event", "T", beside_a_text_and_numbers([
        "n0.val*=-1", "n0.val*=n1.val", "sys0*=n0.val+1", "b[2].val<<=n0.val",
        "sys0*=b[2].val", "n1.val%=7", "for(sys0=1;sys0<100;sys0*=2)", "{", "n0.val++", "}"]),
        ours_in_event, theirs_in_event, _FIXTURES),
    # Each kind of operand, and each operator, in an event.
    Probe("statements-event", "T",
          event_lines(["sys0=5", "// a comment", "sys1=sys0+dim", "dim=50", "sys2++",
                       "sys0=a", "a=RED", "sys0=1000", "sys0=-99", "sys0-=1", "sys0--",
                       "sys0+=sys1*2"]
                      + ["sys0=sys1%s2" % operator for operator in _OPERATORS], ["int a=1"]),
          ours_in_event, theirs_in_event, _FIXTURES),
]
