"""The differences between two sets of named bytes, such as the live blocks
of two project files, or the files of two folders.

A difference is a name that only one side has, or that both sides have with
different bytes. A name whose bytes differ comes with its runs. A run is a
stretch of neighbouring bytes that differ, given with where it starts and
with its bytes on each side.

`nxwright report` compares a project file with its rebuild this way
(source/report.py). It prints where the bytes differ, and never the bytes.
The Editor tool's release scripts print the bytes too
(tools/editor/release_pass.py).
"""
from dataclasses import dataclass

# The kinds of difference. ADDED is only on the second side, REMOVED is only
# on the first side, and CHANGED is on both sides with different bytes.
ADDED, REMOVED, CHANGED = "added", "removed", "changed"


@dataclass(frozen=True)
class Difference:
    """A file or block, `where`, that differs between two sides. `kind` is
    ADDED, REMOVED, or CHANGED. For a changed file or block, `runs` lists
    its runs, each as (where the run starts, the first side's bytes, the
    second side's bytes)."""
    where: str
    kind: str
    runs: tuple = ()


def differing_runs(first: bytes, second: bytes) -> tuple:
    """Returns the runs where `first` and `second` differ. A run is a stretch
    of neighbouring bytes that differ, given as (where it starts, the bytes
    of `first`, the bytes of `second`). When one side is longer, its bytes
    after the end of the shorter side make a run of their own."""
    runs = []
    start = None
    shorter = min(len(first), len(second))
    for place in range(shorter + 1):
        differs = place < shorter and first[place] != second[place]
        if differs and start is None:
            start = place
        elif not differs and start is not None:
            runs.append((start, first[start:place], second[start:place]))
            start = None
    if len(first) != len(second):
        runs.append((shorter, first[shorter:], second[shorter:]))
    return tuple(runs)


def compare_by_name(first: dict, second: dict) -> list:
    """Returns the Differences of `second` from `first`, matched by name
    and listed in the order of the names. Each side is {name: bytes}, the
    form in which HmiContainer gives a project file's live blocks."""
    found = []
    for name in sorted(set(first) | set(second)):
        if name not in first:
            found.append(Difference(name, ADDED))
        elif name not in second:
            found.append(Difference(name, REMOVED))
        elif first[name] != second[name]:
            found.append(Difference(name, CHANGED, differing_runs(first[name], second[name])))
    return found


def differing_ranges(runs: tuple) -> list:
    """Returns where the runs `runs` are, each as (its first place, its last
    place)."""
    return [(start, start + max(len(first), len(second)) - 1) for start, first, second in runs]


def ranges_text(ranges: list, most: int = None) -> str:
    """Returns the ranges of byte places `ranges` as text such as
    "0 to 3, 41, 43". Each range is (its first place, its last place), and
    the ranges must be given in rising order. Ranges that touch are joined.
    With `most`, the text gives that many ranges at most, then how many more
    there are."""
    joined = []
    for first, last in ranges:
        if joined and first == joined[-1][1] + 1:
            joined[-1][1] = last
        else:
            joined.append([first, last])
    shown = joined if most is None else joined[:most]
    texts = [str(first) if first == last else "%d to %d" % (first, last) for first, last in shown]
    more = len(joined) - len(shown)
    if more:
        texts.append("and %d more range%s" % (more, "" if more == 1 else "s"))
    return ", ".join(texts)
