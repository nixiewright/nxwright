"""The table of what the Nextion Editor's compile counts in memory, and of
what each series' compile refuses: memory_costs.toml, which
tools/editor/memory_probe.py measured from the Editor's own compile
(docs/format.md, The Nextion Editor's memory). page_memory.py counts a page's
memory from it, and source/series_components.py refuses what a series
refuses (check_series_components).

Per series of screens (screen_models.ScreenModel.series), the table holds
what page_memory.py's docstring says it counts: a page's bytes and a part
for its count of objects; global memory's bytes and each `int`'s; what a
component of global scope keeps on its page; and each type's cost, with a
part for each attribute that changes it.

A part is a rule over an attribute's value v: floor(bytes * v / units) +
add, rounded up to a multiple of `round`, times the value of the attribute
`times` names, where it names one. A waveform's width, times its channels,
is one. A part may name a `fallback`, an attribute whose value it reads
while its own is 0: a sliding text's `path_m`, the room for its lines,
reads its `txt_maxl` so (Part.cost_in).

A type that needs temporary memory besides, as a QR code, has it in steps
of an attribute's value (Steps). A need with no steps is one the probe
found but could not measure.
"""
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
import tomllib

from nxwright import NxwrightError

TABLE_FILE = Path(__file__).resolve().parent / "memory_costs.toml"


@dataclass(frozen=True)
class Part:
    """A rule over an attribute's value (the module's docstring). The part
    for a page's count of objects names no attribute."""
    attribute: str = ""
    bytes: int = 0
    units: int = 1
    add: int = 0
    round: int = 1
    times: str = None
    fallback: str = None

    def of(self, value: int, times: int = 1) -> int:
        """The part's bytes for `value`, `times` the value of the attribute
        `times` names."""
        counted = self.bytes * value // self.units + self.add
        return times * -(-counted // self.round) * self.round

    def cost_in(self, values: dict) -> int:
        """The part's bytes for a component's `values`, {attribute: value}:
        of its attribute's value, or its fallback's while that is 0, times
        the value of `times`. Every count of a component reads its parts so,
        so that none misses a fallback."""
        value = values[self.attribute]
        if value == 0 and self.fallback is not None:
            value = values[self.fallback]
        return self.of(value, values[self.times] if self.times else 1)


@dataclass(frozen=True)
class Steps:
    """A temporary need, as a QR code's, which steps with an attribute's
    value: `steps` holds (the most value of a step, its bytes), by
    increasing value. `together` says what two such components on a page
    need: "largest", the larger one's, or "sum"."""
    attribute: str
    steps: tuple
    together: str = "largest"

    def of(self, value: int):
        """The bytes needed at `value`, or None past the last step."""
        return next((need for most, need in self.steps if value <= most), None)


@dataclass(frozen=True)
class TypeCosts:
    """What a component of one type costs. `unmeasured` maps each attribute
    whose part was not measured to the value it was measured at. `temporary`
    is the memory it needs besides, beyond the page's total, as Steps, or
    None for none."""
    cost: int
    parts: tuple = ()
    reserve: int = 0
    reserve_parts: tuple = ()
    unmeasured: dict = field(default_factory=dict)
    temporary: Steps = None


@dataclass(frozen=True)
class SeriesCosts:
    """What a series' compile counts (the module's docstring). `refused`
    names the types its compile refuses, and `refused_values` the values it
    was seen to refuse, {type: {attribute: (value, ...)}}: those the probe
    tried, not every value it would refuse."""
    page: int
    objects: Part
    global_memory: int
    int_bytes: int
    global_component: int
    types: dict
    refused: frozenset = frozenset()
    refused_values: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryTable:
    """The table: the Editor's version it was measured on, each model's
    memory by its name, and each series' costs by its letter."""
    editor: str
    memory: dict
    series: dict


@cache
def memory_table() -> MemoryTable:
    """Returns the table nxwright ships, read once."""
    return read_memory_table(TABLE_FILE.read_text(encoding="utf-8"), TABLE_FILE.name)


def read_memory_table(text: str, source: str) -> MemoryTable:
    """Reads a table written as memory_costs.toml is. Raises NxwrightError,
    naming `source`, for one that is not."""
    try:
        data = tomllib.loads(text)
        return MemoryTable(data["editor"], dict(data["memory"]),
                           {letter: _series(costs) for letter, costs in data["series"].items()})
    except (tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as error:
        raise NxwrightError("%s is not a memory table: %s" % (source, error)) from None


def _series(costs: dict) -> SeriesCosts:
    return SeriesCosts(costs["page"], Part(**costs["objects"]), costs["global"], costs["int"],
                       costs["global_component"],
                       {name: _type(type_costs) for name, type_costs in costs["types"].items()},
                       frozenset(costs.get("refused", [])),
                       {name: {attribute: tuple(values) for attribute, values in refused.items()}
                        for name, refused in costs.get("refused_values", {}).items()})


def _type(costs: dict) -> TypeCosts:
    temporary = costs.get("temporary")
    if temporary is not None:
        temporary = Steps(temporary["attribute"], tuple(tuple(step) for step in
                                                        temporary["steps"]),
                          temporary.get("together", "largest"))
    return TypeCosts(costs["cost"], tuple(Part(**part) for part in costs.get("parts", [])),
                     costs.get("reserve", 0),
                     tuple(Part(**part) for part in costs.get("reserve_parts", [])),
                     dict(costs.get("unmeasured", {})), temporary)
