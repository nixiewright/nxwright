"""The memory the Editor's compile counts for each page, from the table the
memory probe measured from the Editor's own compile (memory_table.py,
docs/format.md, The Nextion Editor's memory).

A page's total is the project's global memory and the page's own. The
compile refuses a page whose total passes the screen's memory. Per series of
screens (screen_models.ScreenModel.series):
- a page's own memory is the series' `page` bytes, a part for its count of
  objects, the page among them, and each component's cost, or, for a
  component of global scope, `global_component` bytes;
- a component's cost is its type's `cost`, and a part for each attribute
  that changes it, such as a text's `txt_maxl` (memory_table.Part);
- global memory is the series' `global` bytes, `int` bytes for each `int`
  of program.s, the rest of each global component's cost, and what each
  component's type reserves there, whatever its scope.

Some types also need temporary memory, beyond the page's total, which what
the total leaves of the screen's memory must hold: a QR code needs more as
its `txt_maxl` passes each of the steps the table gives (memory_table.Steps).

The table holds only what the compile showed. A type it lacks, and an
attribute whose part it did not measure, set away from the value it was
measured at, make a component's memory unknown (Unmeasured), rather than
guessed. page_memory and global_memory, which the memory probe compares
with the compile, raise it. A value longer than the attribute bounding it,
where the compile takes one (editor_limits.check_page_limits), costs what
its bound costs, as the compile counted it.

project_memory then does what the compile does with the pages' memory: it
refuses each page whose total passes the screen's memory, and each whose
total leaves less of it than its components' temporary need. It counts the
pages as measure_page gives them, a component whose memory is unknown as
nothing but its place among its page's objects. No component takes less, so
global memory and each page's total are then lower bounds, and a page they
refuse, the compile refuses too. A screen model the table lacks leaves
nothing counted.
"""
from dataclasses import dataclass, field

from nxwright.project.memory_table import SeriesCosts, Steps, memory_table
from nxwright.project.object_types import TYPE_NAMES
from nxwright.project.page_block import PageBlock, PageObject
from nxwright.project.screen_models import ScreenModel

# The scope attribute: 1 for a component of global scope.
_SCOPE = "vscope"


class Unmeasured(Exception):
    """A page's memory is not known: it holds a type or an attribute the
    table did not measure. `where` names the component, as "page0.st0", or
    is None for the screen model itself; `what` says what was not
    measured. The message is both."""

    def __init__(self, what: str, where: str = None):
        super().__init__("%s: %s" % (where, what) if where else what)
        self.what, self.where = what, where


@dataclass(frozen=True)
class PageMemory:
    """A page's own memory, what its components add to global memory, and
    the temporary memory they need besides, which what the page's total
    leaves of the screen's must hold; `needing` names the components whose
    need that is. `unmeasured` holds the Unmeasured of each component
    counted as nothing (measure_page), which makes the rest lower bounds."""
    own: int
    global_part: int
    temporary: int = 0
    needing: tuple = ()
    unmeasured: tuple = ()


@dataclass(frozen=True)
class ProjectMemory:
    """A project's memory, on a screen of the model `model`, of `memory`
    bytes: its global memory; each page's total, {page name: bytes}, in the
    project's order; and `refusals`, ((page name, why), ...), the pages the
    Editor's compile refuses, in order. `unmeasured` is (the page, or None
    for the screen itself, and the first Unmeasured there) when the table
    did not measure all. For the screen, nothing is counted. For a page,
    its components the table lacks count as nothing, so the global memory,
    the totals, and the refusals' numbers are lower bounds."""
    model: str
    memory: int = None
    global_memory: int = None
    totals: dict = field(default_factory=dict)
    refusals: tuple = ()
    unmeasured: tuple = None

    @property
    def warning(self):
        """What the check says of what it did not count, or None when it
        counted all."""
        if self.unmeasured is None:
            return None
        unmeasured = self.unmeasured[1]
        if unmeasured.where is None:
            return "memory not checked: %s" % unmeasured
        return "memory counted without %s, as %s" % (unmeasured.where, unmeasured.what)


@dataclass(frozen=True)
class _ComponentMemory:
    """What one component counts: its bytes on its page, what it adds to
    global memory, and its temporary need, as (Steps, bytes, its name), or
    None for none."""
    own: int
    global_part: int
    need: tuple = None


def page_memory(costs: SeriesCosts, page: PageBlock) -> PageMemory:
    """Returns the memory of a page as built. Raises Unmeasured for a page
    holding a type or an attribute the table did not measure."""
    counted = _components_memory(costs, page)
    for component in counted:
        if isinstance(component, Unmeasured):
            raise component
    return _page_total(costs, page, counted)


def _components_memory(costs: SeriesCosts, page: PageBlock) -> list:
    """Returns each component of `page`, in order, as its _ComponentMemory,
    or as the Unmeasured saying what the table did not measure of it."""
    counted = []
    for page_object in page.objects[1:]:
        try:
            counted.append(_component_memory(costs, page, page_object))
        except Unmeasured as unmeasured:
            counted.append(unmeasured)
    return counted


def _component_memory(costs: SeriesCosts, page: PageBlock,
                      page_object: PageObject) -> _ComponentMemory:
    """Returns what a component counts. Raises Unmeasured."""
    type_costs, values = _measured(costs, page, page_object)
    cost = type_costs.cost + _parts(type_costs.parts, values)
    global_part = type_costs.reserve + _parts(type_costs.reserve_parts, values)
    if values.get(_SCOPE) == 1:
        own = costs.global_component
        global_part += cost - costs.global_component
    else:
        own = cost
    need = None
    if type_costs.temporary is not None:
        need = (type_costs.temporary, _need(type_costs.temporary, values, page, page_object),
                _name(page_object))
    return _ComponentMemory(own, global_part, need)


def _page_total(costs: SeriesCosts, page: PageBlock, counted: list) -> PageMemory:
    """Returns the PageMemory of `page` from what its components count,
    `counted` (_components_memory). Each Unmeasured among them counts as
    nothing but its place among the page's objects."""
    measured = [component for component in counted if not isinstance(component, Unmeasured)]
    own = costs.page + costs.objects.of(len(page.objects))
    own += sum(component.own for component in measured)
    global_part = sum(component.global_part for component in measured)
    needs = [component.need for component in measured if component.need is not None]
    return PageMemory(own, global_part, *_together(needs),
                      unmeasured=tuple(component for component in counted
                                       if isinstance(component, Unmeasured)))


def _need(steps: Steps, values: dict, page: PageBlock, page_object: PageObject) -> int:
    need = steps.of(values[steps.attribute])
    if need is None:
        raise Unmeasured("the temporary memory needed at a %s of %d was not measured"
                         % (steps.attribute, values[steps.attribute]),
                         _where(page, page_object))
    return need


def _together(needs: list) -> tuple:
    """Returns (what a page's components need together, the names of those
    whose need it is), from `needs`, [(Steps, need, name)]: the larger of
    two, or their sum, as their Steps say; the larger for types that differ
    (assumed)."""
    if not needs:
        return 0, ()
    if len({steps for steps, _, _ in needs}) == 1 and needs[0][0].together == "sum":
        return sum(need for _, need, _ in needs), tuple(name for _, _, name in needs)
    _, need, name = max(needs, key=lambda found: found[1])
    return need, (name,)


def global_memory(costs: SeriesCosts, pages: list, ints: int) -> int:
    """Returns a project's global memory, from its pages as built and the
    count of `int`s its program.s declares. Raises Unmeasured as
    page_memory does."""
    return _global_bytes(costs, [page_memory(costs, page) for page in pages], ints)


def _global_bytes(costs: SeriesCosts, pages: list, ints: int) -> int:
    """Global memory, from each page's PageMemory and the count of `int`s."""
    return costs.global_memory + costs.int_bytes * ints + sum(page.global_part
                                                              for page in pages)


def measure_page(model: ScreenModel, page: PageBlock):
    """Returns the PageMemory of `page`, as built, on a screen of `model`,
    its components the table did not measure counted as nothing
    (_page_total); or, for a model the table lacks, the Unmeasured saying
    so, for project_memory to report."""
    try:
        costs = _series_costs(model)
    except Unmeasured as unmeasured:
        return unmeasured
    return _page_total(costs, page, _components_memory(costs, page))


def project_memory(model: ScreenModel, pages: dict, ints: int) -> ProjectMemory:
    """Returns the memory of a project on a screen of `model` (the module's
    docstring). `pages` gives each page, in the project's order, by its
    name: what measure_page returned for it. `ints` counts the `int`s its
    program.s declares, sys0 to sys2 among them, as built."""
    try:
        costs = _series_costs(model)
    except Unmeasured as unmeasured:
        return ProjectMemory(model.name, unmeasured=(None, unmeasured))
    memory = memory_table().memory[model.name]
    left_out = next(((name, page.unmeasured[0]) for name, page in pages.items()
                     if page.unmeasured), None)
    global_bytes = _global_bytes(costs, pages.values(), ints)
    totals, refusals = {}, []
    for name, page in pages.items():
        totals[name] = global_bytes + page.own
        why = _refusal(model.name, memory, global_bytes, page, left_out is not None)
        if why is not None:
            refusals.append((name, why))
    return ProjectMemory(model.name, memory, global_bytes, totals, tuple(refusals), left_out)


def _refusal(model: str, memory: int, global_bytes: int, page: PageMemory, bounds: bool):
    """Why the Editor's compile refuses a page of PageMemory `page`, on a
    screen of the model `model` and its `memory`, with `global_bytes` of
    global memory; None when it takes it. With `bounds`, the counts are
    lower bounds, and the numbers are said as such."""
    at_least, at_most = ("at least ", "at most ") if bounds else ("", "")
    total = global_bytes + page.own
    if total > memory:
        return ("its memory, %s%d + %d = %d bytes, passes the %s's %d, and the Nextion Editor's "
                "compile refuses it (\"Memory overflow\")"
                % (at_least, global_bytes, page.own, total, model, memory))
    if page.temporary > memory - total:
        return ("%s %s %s%d bytes of temporary memory, where the page leaves %s%d of the %s's %d: "
                "%s%d missing, and the Nextion Editor's compile refuses it (\"The remaining "
                "memory is not enough\")" % (" and ".join(page.needing),
                                             "needs" if len(page.needing) == 1 else "need",
                                             at_least, page.temporary, at_most, memory - total,
                                             model, memory, at_least,
                                             page.temporary - (memory - total)))
    return None


def _series_costs(model: ScreenModel) -> SeriesCosts:
    """The costs of the series of `model`. Raises Unmeasured for a model
    the table does not hold."""
    costs = memory_table().series.get(model.series)
    if costs is None or model.name not in memory_table().memory:
        raise Unmeasured("the memory of an %s was not measured" % model.name)
    return costs


def _measured(costs: SeriesCosts, page: PageBlock, page_object: PageObject) -> tuple:
    """Returns (the TypeCosts, the values of the numbers it reads) of a
    component, or raises Unmeasured."""
    where = _where(page, page_object)
    number = int.from_bytes(page_object.attribute("type") or b"", "little")
    type_name = TYPE_NAMES.get(number, "type %d" % number)
    type_costs = costs.types.get(type_name)
    if type_costs is None:
        raise Unmeasured("the memory of a %s was not measured" % type_name, where)
    every_part = type_costs.parts + type_costs.reserve_parts
    read = {part.attribute for part in every_part}
    read |= {part.times for part in every_part if part.times}
    read |= {part.fallback for part in every_part if part.fallback}
    if type_costs.temporary is not None:
        if not type_costs.temporary.steps:
            raise Unmeasured("the temporary memory a %s needs was not measured" % type_name,
                             where)
        read.add(type_costs.temporary.attribute)
    values = {}
    for attribute in read | {_SCOPE}:
        stored = page_object.attribute(attribute)
        if stored is None:
            if attribute == _SCOPE:
                continue
            raise Unmeasured("the %s has no %s" % (type_name, attribute), where)
        values[attribute] = int.from_bytes(stored, "little")
    for attribute, measured_at in type_costs.unmeasured.items():
        stored = page_object.attribute(attribute)
        if stored is not None and _value(stored, measured_at) != measured_at:
            raise Unmeasured("the memory of a %s whose %s is not %r was not measured"
                             % (type_name, attribute, measured_at), where)
    return type_costs, values


def _name(page_object: PageObject) -> str:
    return (page_object.attribute("objname") or b"").decode("latin-1")


def _where(page: PageBlock, page_object: PageObject) -> str:
    """A component as Unmeasured names it: "page0.st0"."""
    return "%s.%s" % (page.name, _name(page_object))


def _parts(parts: tuple, values: dict) -> int:
    return sum(part.cost_in(values) for part in parts)


def _value(stored: bytes, like):
    """An attribute's stored bytes as the kind of value `like` is: a text,
    for a string attribute, or a number."""
    return stored.decode("latin-1") if isinstance(like, str) else int.from_bytes(stored, "little")
