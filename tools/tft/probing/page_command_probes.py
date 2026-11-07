"""The `page` command's probes (statements.py): `page` with a page's number,
its name, an int variable, and a system variable, in page0's Touch Release
event, on the T base folder with pages added, and in program.s; then with
other numbers, attributes, and values of operands joined by operators.
Run them with `tools.tft.probe run page_command_probes`.

Each probe in an event compares the blocks of page0's Touch Release event
alone, and each in program.s the blocks of program.s, keeping them as its
fixture (statement_probes.py gives both).
"""
from pathlib import Path

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.component_probes import PagesChange, on_pages, with_components
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (event_lines, ours_in_event, ours_in_program,
                                            program_lines, theirs_in_event, theirs_in_program)

FIXTURES = "page-command"


def with_pages(pages: list, change):
    """Returns a change that adds the pages `pages`, by name, then makes
    `change`."""
    def both(folder: Path):
        from nxwright.source.source_folder import add_page
        for name in pages:
            add_page(folder, name)
        change(folder)
    return both


def _on_added_pages(pages: list, change) -> PagesChange:
    """Returns a change that adds the pages `pages`, by name, each empty,
    then makes `change`, which changes page0, as with_pages does. A unit
    test reads what it adds, to make the same pages in memory
    (component_probes.PagesChange)."""
    return on_pages(*[with_components(page=name) for name in pages], change)


def _event_probe(name: str, pages: list, lines: list, declarations: list = (),
                 fixtures: bool = False) -> Probe:
    return Probe("page-" + name, "T", _on_added_pages(pages, event_lines(lines, declarations)),
                 ours_in_event, theirs_in_event, FIXTURES if fixtures else None)


# The probes keeping fixtures are the fewest that show each form: a page's
# number, its name, a variable, and `page` in program.s.
PROBES = [
    _event_probe("by-number", ["page1", "page2"], ["page 1", "page 2", "page 0"],
                 fixtures=True),
    _event_probe("by-name", ["page1", "settings"], ["page page1", "page settings", "page page0"],
                 fixtures=True),
    # Ten pages added: a number of two digits, and a name ending in two
    # digits.
    _event_probe("of-ten", ["page%d" % number for number in range(1, 11)],
                 ["page 10", "page page10"]),
    # The Nextion Editor checks no number against the project's pages.
    _event_probe("past-the-last", ["page1"], ["page 5", "page 255"]),
    _event_probe("by-variable", ["page1"], ["page sys0", "page a", "page dp"], ["int a=1"],
                 fixtures=True),
    Probe("page-in-program-s", "T", _on_added_pages(["page1"], program_lines(["page 1"])),
          ours_in_program, theirs_in_program, FIXTURES),
    # Numbers past 255, with leading zeros, signed, and hexadecimal, which
    # the Nextion Editor writes as any number; a number's val; values of
    # operands joined by operators, as an assignment's; and a colour's name.
    # The page holds t0, n0, and n1.
    Probe("page-values", "T", with_attributes([
        "page 256", "page 1000", "page 99999", "page 007", "page 0007", "page -1",
        "page -1000", "page 0x01", "page 0x0A+1", "page n0.val", "page n0.val+1",
        "page n0.val*n1.val", "page 1+1", "page sys0 + 1", "page 2*sys1-3", "page RED"]),
          ours_in_event, theirs_in_event, FIXTURES),
]
