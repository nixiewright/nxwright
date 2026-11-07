"""The frame's probes (frame.py): projects of pages without components on the
T base folder, with other numbers of pages and int variables, other page
names, and code in a page's events. Run them with
`tools.tft.probe run frame_probes`.

Each probe compares the user code part by part (pieces), with the code's
blocks from the statement encoder (statements.py). The fixtures are the
frame's output through stand_in_code instead, whose blocks are made up, so
that the frame's tests need neither the encoder nor anything the Nextion
Editor wrote.
"""
from dataclasses import asdict, dataclass
from pathlib import Path

from nxwright.tft import frame
from tools.tft.probing.probe_runner import Parts, Probe, ProbeError, ProbeMismatch
from nxwright.tft.project import Project
from nxwright.tft.tft_file import TftFileError, UserCode, encode_blocks, read_tft

# The program.s line every base folder declares its int variables on.
_INTS = "int sys0=0,sys1=0,sys2=0"
# The name each part of the user code is kept by (pieces), by the part's name
# in UserCode.places; then each part of its blocks, by block_parts' name.
# Every other part of the blocks is a page's, kept with the other pages'.
_KEPT_PARTS = {"after the blocks": "after-blocks", "variables": "variables", "data": "data",
               "page index": "page-index", "records": "records", "macros": "macros-table"}
_KEPT_BLOCK_PARTS = {"first block": "first-block", "program.s": "program-s",
                     "macros": "macros"}


def pieces(code: UserCode) -> dict:
    """Returns the user code `code` as the probes compare it: its first
    block, program.s's blocks, the pages' blocks, and the parts after them;
    and, in a project with macros, their blocks and their table."""
    parts = code.block_parts()

    def blocks_of(test) -> bytes:
        return encode_blocks([block for block, part in zip(code.blocks, parts) if test(part)])

    found = {"first-block": blocks_of(lambda part: part == "first block"),
             "program-s": blocks_of(lambda part: part == "program.s"),
             "pages": blocks_of(lambda part: part.startswith("page")),
             "after-blocks": code.after_blocks, "variables": code.variables, "data": code.data,
             "page-index": code.page_index, "records": code.records}
    if code.macros:
        found.update({"macros": blocks_of(lambda part: part == "macros"),
                      "macros-table": code.macros})
    return found


def parts_and_pieces(code: UserCode, laid: list, object_places: dict = None) -> Parts:
    """Returns the user code `code` as pieces() gives it, with where each
    piece the frame laid out lies among those parts (`laid`, a list of
    frame.Piece, as frame.laid_out gives it), and where each component lies
    (`object_places`, as frame.laid_out gives them). Raises ProbeError for a piece
    of the blocks that lies across two of their parts, as program.s's
    blocks after a `return` would, which block_parts gives the next part."""
    # Where each part of the blocks lies, among all the blocks.
    places, at = {}, 0
    for block, part in zip(code.blocks, code.block_parts()):
        name = _KEPT_BLOCK_PARTS.get(part, "pages")
        start = places.get(name, (at, at))[0]
        at += len(encode_blocks([block]))
        places[name] = (start, at)
    table = {}
    for piece in laid:
        if piece.part != "blocks":
            table[piece.name] = (_KEPT_PARTS[piece.part], piece.start, piece.end)
            continue
        part = next((name for name, (start, end) in places.items()
                     if start <= piece.start and piece.end <= end), None)
        if part is None:
            raise ProbeError("the piece %s lies across two parts of the user code's blocks"
                             % piece.name)
        table[piece.name] = (part, piece.start - places[part][0], piece.end - places[part][0])
    if len(table) != len(laid):
        raise ProbeError("two pieces of the user code share a name")
    # A fixture keeps where each object lies. A timer's numbers of the
    # counter are not a place, so they are left out.
    return Parts(pieces(code), table, {name: {key: value for key, value in asdict(place).items()
                                              if key != "timer_numbers"}
                                       for name, place in (object_places or {}).items()})


def stand_in_code(lines: list, place, context) -> list:
    """Returns a made-up block for each line of `lines`, in order, but where
    the statement encoder gives none: for a comment, and for one of
    program.s's int declarations, which the frame reads itself."""
    return [b"stand-in " + line.encode("utf-8") for line in lines
            if not (line.strip().startswith("//")
                    or (place.page is None and frame.declares_ints(line)))]


def _ours(project: Path) -> dict:
    return pieces(frame.user_code(Project.from_file(project)))


def editor_pieces(data: bytes) -> dict:
    """Returns the pieces (pieces) of the user code of the Nextion Editor's
    file `data`, which a frame probe compares. Raises ProbeMismatch for a
    file the reader cannot read."""
    try:
        return pieces(read_tft(data, "the Nextion Editor's file").user_code)
    except TftFileError as error:
        raise ProbeMismatch(str(error)) from None


def _kept(project: Path) -> Parts:
    return parts_and_pieces(*frame.laid_out(Project.from_file(project), stand_in_code))


@dataclass(frozen=True)
class AddedPage:
    """A page a frame probe adds, empty, with the event code `code`, which a
    unit test reads as it reads a component_probes.ComponentsChange's page
    (tests/tft/unit_inputs.py)."""
    page: str
    code: str = ""
    components: tuple = ()
    attributes: str = ""


@dataclass(frozen=True, eq=False)
class FrameChange:
    """A probe's change that adds the pages `pages`, each an AddedPage, gives
    page0 the event code `code`, and gives program.nx the int variables
    `ints` after the base's own on its declaration line, then the lines
    `declarations`, as statement_probes.program_text writes them. A unit
    test reads what it adds, to make the same pages and program.s in memory
    (tests/tft/unit_inputs.py), as it reads a component_probes.PagesChange. It
    is written here, as component_probes.py reads this module. Two changes
    are equal only if they are the same one, as two functions are."""
    pages: tuple = ()
    code: str = ""
    ints: tuple = ()
    declarations: tuple = ()
    page = "page0"
    components = ()
    attributes = ""

    @property
    def changes(self) -> tuple:
        return (self,) + tuple(self.pages)

    def __call__(self, folder: Path):
        from nxwright.source.source_folder import add_page
        for added in self.pages:
            add_page(folder, added.page)
            if added.code:
                (folder / "pages" / (added.page + ".nx")).write_text(added.code,
                                                                     encoding="utf-8")
        if self.code:
            (folder / "pages" / "page0.nx").write_text(self.code, encoding="utf-8")
        if self.ints or self.declarations:
            _program_with("\n".join([_ints(*self.ints), *self.declarations]))(folder)


def _with_pages(*names) -> FrameChange:
    """Returns a change that adds the pages `names`, each empty
    (FrameChange)."""
    return FrameChange(tuple(AddedPage(name) for name in names))


def _program_with(declaration: str):
    """Returns a change that puts `declaration` in place of the base folder's
    int declaration, such as "int sys0=0,sys1=0,sys2=0,a=5" for one more int
    on that line, or "" for none."""
    def change(folder: Path):
        program = folder / "program.nx"
        text = program.read_text(encoding="utf-8")
        if _INTS not in text:
            raise ValueError("%s has no %r" % (program, _INTS))
        program.write_text(text.replace(_INTS, declaration), encoding="utf-8")
    return change


def _ints(*more: str) -> str:
    return ",".join([_INTS] + list(more))


def int_declaration_of(length: int) -> str:
    """Returns an int declaration of `length` characters, as written: names
    of 14 characters, each set to a number of 1 to 10 digits. The Nextion
    Editor does not hold a declaration to the 767 characters it holds other
    lines to on T and K."""
    item = len("abcdefghijkl00=1")
    for count in range(1, 100):
        shortest = len("int ") + count * item + count - 1
        if shortest <= length <= shortest + 9 * count:
            extra, values = length - shortest, []
            for _ in range(count):
                digits = min(9, extra)
                extra -= digits
                values.append("1" + "2" * digits)
            return "int " + ",".join("abcdefghijkl%02d=%s" % (number, value)
                                     for number, value in enumerate(values))
    raise ValueError("no declaration of %d characters" % length)


def _with_ints_alone(folder: Path):
    """Leaves program.s its int declaration alone."""
    (folder / "program.nx").write_text(_INTS + "\n", encoding="utf-8")


# Code in each of page0's events.
_PAGE_EVENTS = FrameChange(code=(
    "on page0.load:\n  sys0=1\n\non page0.loadend:\n  sys0=2\n\n"
    "on page0.down:\n  sys0=3\n  sys1=6\n\non page0.up:\n  sys0=4\n\n"
    "on page0.unload:\n  sys0=5\n"))
# page0's down event of a comment alone.
_COMMENT_EVENT = FrameChange(code="on page0.down:\n  // nothing yet\n")
# A second page, with code in its load and up events.
_SECOND_PAGE_EVENTS = FrameChange((AddedPage(
    "page1", code="on page1.load:\n  sys0=7\n\non page1.up:\n  sys1=8\n"),))


def _with_a_comment_alone(folder: Path):
    """Leaves program.s a comment alone, which the Nextion Editor writes as
    a program.s of no lines."""
    (folder / "program.nx").write_text("// nothing\n", encoding="utf-8")


def _empty(folder: Path):
    """Leaves program.s empty, which the Nextion Editor writes as a new
    project's program.s."""
    (folder / "program.nx").write_text("", encoding="utf-8")


def _probe(name: str, change=None, fixtures: bool = False) -> Probe:
    return Probe("frame-" + name, "T", change, _ours, editor_pieces, "frame" if fixtures else None,
                 _kept)


# The probes keeping fixtures are the fewest that show each part: the page
# list's order and the page index on three pages, the int area and the
# variables' order with two more ints, the int values' bounds, and the events.
PROBES = [
    _probe("one-page"),
    _probe("two-pages", _with_pages("page1")),
    _probe("three-pages", _with_pages("page1", "page2"), fixtures=True),
    _probe("ten-pages", _with_pages(*("page%d" % number for number in range(1, 10)))),
    _probe("forty-pages", _with_pages(*("page%d" % number for number in range(1, 40)))),
    _probe("page-named-settings", _with_pages("settings")),
    _probe("page-name-of-14", _with_pages("Main_Screen_14")),
    _probe("page-name-of-1", _with_pages("p")),
    _probe("page-name-starting-with-_", _with_pages("_main")),
    _probe("no-ints", _program_with("")),
    _probe("one-int", _program_with("int sys0=0")),
    _probe("one-more-int", FrameChange(ints=("a=5",))),
    _probe("int-of-1000", FrameChange(ints=("a=1000",))),
    _probe("two-more-ints", FrameChange(ints=("a=5", "b=6")), fixtures=True),
    _probe("twenty-ints", FrameChange(ints=tuple("v%d=%d" % (n, n) for n in range(17)))),
    _probe("hundred-ints", FrameChange(ints=tuple("v%d=%d" % (n, n) for n in range(97)))),
    _probe("int-bounds", FrameChange(ints=("lo=-2147483648", "hi=2147483647")), fixtures=True),
    _probe("int-name-of-14", FrameChange(ints=("counter_value1=7",))),
    # Names of 15 to 32 characters, the most the Nextion Editor takes.
    _probe("int-names-past-14", FrameChange(ints=(
        "abcdefghijklmno=4", "settingsPending=1", "pic_buttonNumpadBackspacePressed=3")),
        fixtures=True),
    # Spaces after int, around a name, its "=", and its value, and before a
    # comma, which the Nextion Editor reads as none.
    _probe("int-declarations-with-spaces", FrameChange(declarations=(
        "int count = 7", "int  b=3", "int c=4 ,d=5", "int e = 5 , f = 6")), fixtures=True),
    # Values with leading zeros, a plus sign, and -0.
    _probe("int-values-of-other-forms", FrameChange(declarations=(
        "int a=007", "int b=+5", "int c=-0")), fixtures=True),
    # Hexadecimal values, each read as its low 4 bytes, a signed int.
    _probe("int-values-in-hexadecimal", FrameChange(declarations=(
        "int a=0x1", "int b=0x10", "int c=0x80000000", "int d=0xFFFFFFFF",
        "int e=0x0100000000")), fixtures=True),
    # A tab after int, and a space after the value.
    _probe("int-declarations-with-a-tab-and-a-space-after", FrameChange(declarations=(
        "int\ta=3", "int b=4 ")), fixtures=True),
    _probe("program-s-of-a-comment-alone", _with_a_comment_alone, fixtures=True),
    _probe("program-s-empty", _empty, fixtures=True),
    _probe("second-int-line", FrameChange(declarations=("int c=3",))),
    # A declaration of 1000 characters, past the 767 other lines may have.
    _probe("int-line-of-1000-characters",
           FrameChange(declarations=(int_declaration_of(1000),))),
    _probe("ints-alone", _with_ints_alone),
    _probe("two-pages-one-more-int", FrameChange((AddedPage("page1"),), ints=("a=5",))),
    _probe("page-events", _PAGE_EVENTS, fixtures=True),
    _probe("comment-alone-in-an-event", _COMMENT_EVENT),
    _probe("second-page-events", _SECOND_PAGE_EVENTS),
]
