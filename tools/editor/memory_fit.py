"""The memory probe's reasoning, apart from the Editor, so that its tests need
neither it nor pywinauto (tests/test_memory_fit.py): reading what a compile
counted and refused, fitting a rule to an attribute's costs, and writing the
table nxwright reads (nxwright/project/memory_table.py, which says what a
rule is).

A compile's Output panel, as the Editor 3.1.73 writes it:
    Available Memory:3584
    Global Memory:16
    Total size of font:8,029
    Page:page0 Memory Occupied:16+20=36
    File Check Finish
    Compile Successful! 0 Errors, 0 Warnings,File Size:368,840
It checks types and attributes before it counts memory, and stops at the
first it refuses, naming it, as "Error:p09.c0.staOut of range". It lists the
pages' memory in order, and an overflow stops it too:
"Error:Page:p26 Error! Memory overflow:16+4072=4088".
"""
from dataclasses import dataclass
from fractions import Fraction
from math import floor
import re

import tomli_w

from nxwright.project.memory_table import Part

_MEMORY = re.compile(r"Available Memory:(\d+)$")
_GLOBAL = re.compile(r"Global Memory:(\d+)$")
_PAGE = re.compile(r"Page:(\S+) Memory Occupied:\d+\+(\d+)=\d+$")
_OVERFLOW = re.compile(r"Error:Page:(\S+) Error! Memory overflow:\d+\+(\d+)=\d+$")
_UNSUPPORTED = re.compile(r"Error:Unsupported component was found for this series device:"
                          r"(\w+)\.(\w+)$")
_OUT_OF_RANGE = re.compile(r"Error:(\w+)\.(\w+)\.(\w+)Out of range$")
_TEMPORARY = re.compile(r"Error:Page:(\S+) The remaining memory is not enough to run the "
                        r"temporary use of (.+?)\((-?\d+)\)")
_SUCCEEDED = re.compile(r"Compile Successful!")
_FAILED = re.compile(r"Error:Compile failed!")
# The roundings a rule may have, and the most units its bytes may be spread
# over: a waveform keeps 13 bytes for each 10 pixels of its width.
ROUNDINGS = (1, 2, 4, 8)
MOST_UNITS = 10
# The most bytes a page's part may take for each object it holds: 1 was seen.
MOST_OBJECT_BYTES = 8


@dataclass
class Compiled:
    """What a compile showed: the screen's memory and the project's global
    memory, None when it stopped before them; each page's own memory, by
    name, those it reached, the page an overflow stopped it on among them;
    and its refusal, if it failed: ("unsupported",
    page, component), ("out of range", page, component, attribute),
    ("overflow", page), ("temporary", page, the type's words, the bytes
    missing) for a type's temporary need, as a QR code's, or ("other", the
    line)."""
    memory: int
    global_memory: int
    pages: dict
    refusal: tuple
    succeeded: bool


def read_compile(output: str) -> Compiled:
    """Reads a compile's Output panel (the module's docstring). An error the
    probe does not know is the refusal ("other", line)."""
    memory = global_memory = refusal = None
    pages = {}
    succeeded = False
    for line in (line.strip() for line in output.splitlines()):
        if _MEMORY.match(line):
            memory = int(_MEMORY.match(line)[1])
        elif _GLOBAL.match(line):
            global_memory = int(_GLOBAL.match(line)[1])
        elif _PAGE.match(line):
            pages[_PAGE.match(line)[1]] = int(_PAGE.match(line)[2])
        elif _SUCCEEDED.match(line):
            succeeded = True
        elif _FAILED.match(line):
            pass
        elif line.startswith("Error:") and refusal is None:
            refusal = _refusal(line)
            if _OVERFLOW.match(line):
                # The page the compile stopped on: its own memory is given too.
                pages[_OVERFLOW.match(line)[1]] = int(_OVERFLOW.match(line)[2])
    return Compiled(memory, global_memory, pages, refusal, succeeded)


def _refusal(line: str) -> tuple:
    overflow = _OVERFLOW.match(line)
    if overflow:
        return ("overflow", overflow[1])
    unsupported = _UNSUPPORTED.match(line)
    if unsupported:
        return ("unsupported", unsupported[1], unsupported[2])
    out_of_range = _OUT_OF_RANGE.match(line)
    if out_of_range:
        return ("out of range",) + out_of_range.groups()
    temporary = _TEMPORARY.match(line)
    if temporary:
        # How much is missing, as a positive number of bytes.
        return ("temporary", temporary[1], temporary[2], -int(temporary[3]))
    return ("other", line)


def fit_part(attribute: str, costs: dict, domain=None) -> tuple:
    """Returns (Part, constant) such that each cost of `costs`, by the
    attribute's value, is the constant and the part's bytes for the value:
    the simplest rule (fewest units, then the least rounding) that fits
    every one. Returns None when none fits, or when two rules that fit
    differ on a value the attribute may take, so that more values must be
    measured to tell them apart. `domain` holds the values it may take,
    when they are known, as a choice's are; else those up to well beyond
    the values measured are taken."""
    fits = _fits(attribute, costs)
    if not fits:
        return None
    best = fits[0]
    low, high = min(costs), max(costs)
    for other in fits[1:]:
        if any(_cost(best, value) != _cost(other, value)
               for value in domain or range(low, high + 4 * (high - low) + 64)):
            return None
    return best


def _fits(attribute: str, costs: dict) -> list:
    values = sorted(costs)
    if len(values) < 2:
        return []
    low, high = values[0], values[-1]
    slope = Fraction(costs[high] - costs[low], high - low)
    # Rounding moves either end by less than its multiple.
    tolerance = Fraction(max(ROUNDINGS), high - low)
    fits = []
    for units in range(1, MOST_UNITS + 1):
        for bytes_ in range(max(0, floor((slope - tolerance) * units)),
                            floor((slope + tolerance) * units) + 1):
            if units > 1 and _shares_a_factor(bytes_, units):
                continue    # the same rule as with fewer units
            for rounding in ROUNDINGS:
                # An add of a whole rounding more is the constant's.
                for add in range(rounding):
                    part = Part(attribute, bytes_, units, add, rounding)
                    constant = costs[low] - part.of(low)
                    if all(constant + part.of(value) == costs[value] for value in values):
                        fits.append((part, constant))
    # The simplest first: the fewest units, the least rounding and add,
    # then the bytes nearest the slope.
    return sorted(fits, key=lambda fit: (fit[0].units, fit[0].round, fit[0].add,
                                         abs(Fraction(fit[0].bytes, fit[0].units) - slope)))


def _shares_a_factor(first: int, second: int) -> bool:
    return any(first % factor == 0 and second % factor == 0 for factor in range(2, second + 1))


def _cost(fit: tuple, value: int) -> int:
    part, constant = fit
    return constant + part.of(value)


def fit_objects(owns: dict) -> tuple:
    """Returns (Part, cost) for a page's part for its count of objects, the
    page among them, from `owns`: the own memory of pages holding n
    components of one type, by n, 0 for an empty page; `cost` is that
    type's. A type's cost and the bytes each object takes cannot be told
    apart when they share a rounding, as any split gives every page the
    same memory, so the fewest bytes an object that fit are taken, then the
    least rounding. None when nothing fits, or when two rules that fit
    differ on pages of more components."""
    fits = []
    for bytes_ in range(MOST_OBJECT_BYTES + 1):
        for rounding in ROUNDINGS:
            for add in range(rounding):
                part = Part("", bytes_, 1, add, rounding)
                cost = owns[1] - owns[0] - (part.of(2) - part.of(1))
                if all(_own(owns[0], part, cost, count) == own for count, own in owns.items()):
                    fits.append((part, cost))
    if not fits:
        return None
    best = fits[0]
    for part, cost in fits[1:]:
        if any(_own(owns[0], part, cost, count) != _own(owns[0], *best, count)
               for count in range(256)):
            return None
    return best


def _own(empty: int, part: Part, cost: int, count: int) -> int:
    return empty + count * cost + part.of(count + 1) - part.of(1)


def fit_times(first: Part, second: Part, first_at: int, costs: dict) -> tuple:
    """Tries the rule a waveform showed, where one attribute multiplies
    another's part: each channel keeps a buffer for its width. `first` and
    `second` are the two attributes' parts, each fitted with the other at
    its base value, the first's `first_at`; `costs` gives costs by (the
    first's value, the second's), both changed. Returns (parts, constant)
    if the second, a plain count, multiplies the first's part, and that
    fits every cost; else None."""
    if not costs or (second.units, second.add, second.round) != (1, 0, 1):
        return None
    # At the first's base value, each unit of the second added its own
    # bytes and the first's part.
    own = second.bytes - first.of(first_at)
    parts = (Part(second.attribute, own),) if own else ()
    parts += (Part(first.attribute, first.bytes, first.units, first.add, first.round,
                   second.attribute),)

    def counted(first_value: int, second_value: int) -> int:
        values = {first.attribute: first_value, second.attribute: second_value}
        return sum(part.cost_in(values) for part in parts)
    (first_value, second_value), cost = next(iter(costs.items()))
    constant = cost - counted(first_value, second_value)
    if any(constant + counted(*values) != cost for values, cost in costs.items()):
        return None
    return parts, constant


def table_text(editor: str, memory: dict, series: dict) -> str:
    """Returns the table as memory_costs.toml holds it. `memory` gives each
    model's memory by its name; `series` each series' costs by its letter,
    as memory_table.SeriesCosts holds them."""
    table = {"editor": editor, "memory": dict(sorted(memory.items())),
             "series": {letter: _series_fields(series[letter]) for letter in sorted(series)}}
    return _TABLE_HEADING + tomli_w.dumps(table)


# The table's opening comment, which tomli-w, writing no comments, leaves to us.
_TABLE_HEADING = ("# What the Nextion Editor's compile counts in memory, as\n"
                  "# tools/editor/memory_probe.py measured it (docs/format.md, Memory).\n"
                  "# Written by the probe: measure again rather than edit.\n\n")


def _series_fields(costs) -> dict:
    fields = {"page": costs.page, "objects": _part_fields(costs.objects),
              "global": costs.global_memory, "int": costs.int_bytes,
              "global_component": costs.global_component}
    if costs.refused:
        fields["refused"] = sorted(costs.refused)
    if costs.refused_values:
        fields["refused_values"] = {
            name: {attribute: list(values) for attribute, values in sorted(refused.items())}
            for name, refused in sorted(costs.refused_values.items())}
    fields["types"] = {name: _type_fields(costs.types[name]) for name in sorted(costs.types)}
    return fields


def _type_fields(costs) -> dict:
    fields = {"cost": costs.cost}
    if costs.parts:
        fields["parts"] = [_part_fields(part) for part in costs.parts]
    if costs.reserve:
        fields["reserve"] = costs.reserve
    if costs.reserve_parts:
        fields["reserve_parts"] = [_part_fields(part) for part in costs.reserve_parts]
    if costs.unmeasured:
        fields["unmeasured"] = dict(sorted(costs.unmeasured.items()))
    if costs.temporary is not None:
        fields["temporary"] = {"attribute": costs.temporary.attribute,
                               "steps": [list(step) for step in costs.temporary.steps],
                               "together": costs.temporary.together}
    return fields


def _part_fields(part: Part) -> dict:
    """A part's fields, leaving out those at their defaults."""
    fields = {"attribute": part.attribute, "bytes": part.bytes, "units": part.units,
              "add": part.add, "round": part.round, "times": part.times,
              "fallback": part.fallback}
    return {name: value for name, value in fields.items()
            if value != getattr(Part(), name) or name == "bytes"}
