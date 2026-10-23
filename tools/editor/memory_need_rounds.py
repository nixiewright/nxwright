"""The memory probe's rounds of temporary needs, as a QR code's
(memory_probe.py): pages filled to the screen's memory (NeedPages), so that
the compile refuses one by its whole need, or takes it, needing none; the
one attribute a need follows; the edges of its steps, found by halving; and
what two of a type on a page need."""
from dataclasses import dataclass

from nxwright.project.memory_table import Part, Steps
from nxwright.source.page_source import MOST_OBJECTS
from tools.editor.memory_cases import (Case, Component, bounded_text, defaults, is_buffer,
                                       most_value)
from tools.editor.memory_global_rounds import reserve_at
from tools.editor.memory_series import (MOST_PAGES, NEED, ProbeStopped, SeriesProbe,
                                        bounded_bytes, buffers_of, cost_of, grown_values)

@dataclass
class NeedPages:
    """Makes the cases that measure temporary needs. Each holds what it
    measures and a text, its filler, so long that the page's total is the
    screen's memory, by the costs found so far: the compile then refuses
    the page by the whole need, or takes it, needing none. `cost` gives the
    cost of a case measured alone, by its key."""
    probe: SeriesProbe
    types: dict
    unmeasured: dict
    reserves: dict
    reserve_parts: dict
    base_global: int
    empty_own: int
    objects: Part
    cost: object

    def fillable(self, components: tuple) -> bool:
        """Whether a page of `components` can be filled: each one's cost is known."""
        return all(self._cost(component) is not None for component in components)

    def cases(self, specs: list) -> list:
        """The cases of `specs`, [(key, components)], each fillable, for one
        project, whose global memory each page's total holds: what every
        component reserves there. A filler reserves nothing, or none is made."""
        if self._reserve(Component("text")) or self.reserve_parts.get("text"):
            raise ProbeStopped("a text reserves global memory on %s, so its page's fillers "
                               "cannot be sized" % self.probe.model)
        if "txt_maxl" in self.unmeasured["text"] or \
                not any(part.attribute == "txt_maxl" for part in self.types["text"].parts):
            raise ProbeStopped("a text's txt_maxl part is not known on %s, so no page can be "
                               "filled" % self.probe.model)
        held = [component for _, components in specs for component in components]
        global_memory = self.base_global + sum(map(self._reserve, held))
        return [Case(key, components + self._fillers(key, components, global_memory))
                for key, components in specs]

    def _fillers(self, key: str, components: tuple, global_memory: int) -> tuple:
        """The texts whose `txt_maxl` make the page of `components` and them
        hold, with `global_memory`, all of the screen's memory: as few as
        may, each of the largest `txt_maxl` the series may take but the last
        (_largest_filler), which takes the rest."""
        base = {**defaults("text"), **self.probe.base["text"]}

        def costs(txt_maxl: int) -> int:
            return cost_of(self.types["text"], {**base, "txt_maxl": txt_maxl})
        largest = self._largest_filler()
        on_page = self.empty_own - self.objects.of(1) + sum(map(self._on_page, components))
        # A page holds at most MOST_OBJECTS objects, itself among them.
        for count in range(1, MOST_OBJECTS - len(components)):
            room = self.probe.memory - global_memory - on_page - \
                self.objects.of(len(components) + 1 + count) - (count - 1) * costs(largest)
            if room < costs(0):
                raise ProbeStopped("the page %s holds more than the screen's memory on %s"
                                   % (key, self.probe.model))
            if room > costs(largest):
                continue
            # The last text's txt_maxl, by halving: a text costs more as it grows.
            low, high = 0, largest
            while low < high:
                middle = (low + high + 1) // 2
                low, high = (middle, high) if costs(middle) <= room else (low, middle - 1)
            if costs(low) != room:
                raise ProbeStopped("no text fills the page %s to the screen's memory on %s, "
                                   "%d bytes being left" % (key, self.probe.model,
                                                            room - costs(low)))
            return (Component("text", (("txt_maxl", largest),)),) * (count - 1) + \
                (Component("text", (("txt_maxl", low),)),)
        raise ProbeStopped("the page %s needs more texts to fill than a page holds on %s"
                           % (key, self.probe.model))

    def _largest_filler(self) -> int:
        """The largest `txt_maxl` a filler takes: the most its bytes hold, or,
        once the series refused one, half the least it refused, so that a
        value it takes is reached by halving."""
        refused = [value for kind, attribute, value in self.probe.refused_values
                   if (kind, attribute) == ("text", "txt_maxl")]
        return min(refused) // 2 if refused else most_value("text", "txt_maxl")

    def _cost(self, component: Component):
        """A component's cost: of the case that measured it alone, else from
        its type's parts; None where one of its values is unmeasured."""
        for measured_key, case in self.probe.cases.items():
            if case.components == (component,) and not case.page_values and \
                    not measured_key.startswith(NEED):
                return self.cost(measured_key)
        values = {**defaults(component.kind), **self.probe.base[component.kind],
                  **dict(component.values)}
        if any(values[attribute] != measured_at
               for attribute, measured_at in self.unmeasured[component.kind].items()):
            return None
        return cost_of(self.types[component.kind], values)

    def _on_page(self, component: Component) -> int:
        """What a component keeps on its page: its cost, but for a type
        global alone, which keeps there what its page measured alone."""
        if component.kind not in self.probe.global_only:
            return self._cost(component)
        step = self.objects.of(2) - self.objects.of(1)
        return self.probe.owns["type %s" % component.kind] - self.empty_own - step

    def _reserve(self, component: Component) -> int:
        """What a component keeps in global memory: what its type reserves
        there, or, for a type global alone, its cost past its page's part."""
        if component.kind in self.probe.global_only:
            return self._cost(component) - self._on_page(component)
        values = {**defaults(component.kind), **self.probe.base[component.kind],
                  **dict(component.values)}
        return reserve_at(self.probe, component.kind, self.reserves, self.reserve_parts, values)


def measure_needs(probe: SeriesProbe, pages: NeedPages, specs: list) -> dict:
    """Measures the temporary need of each of `specs`, [(key, components)],
    a project at a time, each compile measuring the pages up to the first it
    refuses. Returns {key: need}, None for a page the series refuses, as one
    of a value out of range, or that cannot be filled, as the cost of a
    value unmeasured is not known."""
    fillable = [(key, components) for key, components in specs if pages.fillable(components)]
    while True:
        pending = [(key, components) for key, components in fillable
                   if key not in probe.needs and probe.takes(Case(key, components))]
        if not pending:
            return {key: probe.needs[key].need if key in probe.needs else None
                    for key, _ in specs}
        before = probe.progress()
        probe.compile(tuple(pages.cases(pending[:MOST_PAGES - 1])))
        if probe.progress() == before:
            raise ProbeStopped("a compile of pages measuring temporary needs on %s measured "
                               "none, and refused nothing the probe can leave out"
                               % probe.model)


def need_key(kind: str, *words) -> str:
    return " ".join((NEED, kind) + tuple(str(word) for word in words))


def temporary_needs(probe: SeriesProbe, pages: NeedPages, notes: list) -> dict:
    """{type: Steps}, the temporary need of each type that has one, from a
    page of each type with its base values; then, for those that need
    memory, by the attribute it follows (_need_steps)."""
    kinds = [kind for kind in probe.taken() if "type %s" % kind in probe.owns]
    needs = measure_needs(probe, pages, [(need_key(kind), (Component(kind),)) for kind in kinds])
    return {kind: _need_steps(probe, pages, kind, needs[need_key(kind)], notes)
            for kind in kinds if needs[need_key(kind)]}


def _need_steps(probe: SeriesProbe, pages: NeedPages, kind: str, need: int,
                notes: list) -> Steps:
    """A type's temporary need, `need` with its base values, as Steps of the
    one buffer attribute it moves with, at its other attributes' base
    values. Those that move it are left unmeasured away from them, as for
    the type's costs. The steps' edges are found by halving the values
    between two measured whose needs differ, a need being taken to grow
    with the attribute's value; then two of the type on a page show whether
    the larger need counts, or the two together. Returns Steps without
    steps, so that no page of the type is checked, for a need that moves
    with no buffer, with several, or not as steps do."""
    _unmeasure_need_movers(probe, pages, kind, need, notes)
    attribute, known = _need_buffer(probe, pages, kind, need, notes)
    if known is None or not _measure_step_edges(probe, pages, kind, attribute, known, notes):
        return Steps(attribute, ())
    ordered = sorted(known)
    # Each step ends at the last value of its need: the last at the largest measured.
    steps = tuple((value, known[value]) for value, after in zip(ordered, ordered[1:] + [None])
                  if after is None or known[after] != known[value])
    key = need_key(kind, "two")
    two = measure_needs(probe, pages, [(key, (Component(kind), Component(kind)))])[key]
    together = {need: "largest", 2 * need: "sum"}.get(two)
    if together is None:
        notes.append("two %ss on a page need %d, where one needs %d: not measured"
                     % (kind, two, need))
        return Steps(attribute, ())
    return Steps(attribute, steps, together)


def _unmeasure_need_movers(probe: SeriesProbe, pages: NeedPages, kind: str, need: int,
                           notes: list):
    """Leaves unmeasured, away from its base value, each attribute of `kind`
    but its buffers that moves its temporary need, `need` with its base
    values: its attributes varied all at once, as for its cost, then each
    alone, where that moved the need."""
    base = {**defaults(kind), **probe.base[kind]}
    unmeasured = pages.unmeasured[kind]
    varied = probe.cases.get("varied %s" % kind)
    key = need_key(kind, "varied")
    if varied is None or measure_needs(probe, pages, [(key, varied.components)])[key] == need:
        return
    alone = {need_key(kind, "varied", attribute): (attribute, value)
             for attribute, value in varied.components[0].values if not is_buffer(attribute)}
    measured = measure_needs(probe, pages, [(key, (Component(kind, (item,)),))
                                            for key, item in alone.items()])
    for key, (attribute, _) in alone.items():
        if measured[key] is None:
            notes.append("a %s's temporary need with its %s changed could not be measured, "
                         "its cost not known: not measured away from %r"
                         % (kind, attribute, base[attribute]))
            unmeasured[attribute] = base[attribute]
        elif measured[key] != need:
            notes.append("a %s's temporary need changes with its %s: not measured away from %r"
                         % (kind, attribute, base[attribute]))
            unmeasured[attribute] = base[attribute]


def _need_buffer(probe: SeriesProbe, pages: NeedPages, kind: str, need: int,
                 notes: list) -> tuple:
    """Returns (the one buffer of `kind` its temporary need moves with, the
    need at each value measured, {value: need}), from each buffer's values
    from 0, the others at their base values. The second is None where a
    need could not be measured, or moves with no buffer, or with several."""
    base = {**defaults(kind), **probe.base[kind]}
    points = {}
    for buffer in buffers_of(kind):
        values = sorted({0, *grown_values(probe, kind, buffer)} - {base[buffer]})
        measured = _buffer_needs(probe, pages, kind, buffer, values)
        if None in measured.values():
            notes.append("a %s's temporary need by its %s could not be measured, its cost not "
                         "known: not measured" % (kind, buffer))
            return buffer, None
        points[buffer] = {**measured, base[buffer]: need}
    moving = [buffer for buffer, needs in points.items() if set(needs.values()) != {need}]
    if len(moving) != 1:
        notes.append("a %s's temporary need moves with %s: not measured"
                     % (kind, " and ".join(moving) or "none of its buffers"))
        return (moving[0] if moving else ""), None
    return moving[0], points[moving[0]]


def _measure_step_edges(probe: SeriesProbe, pages: NeedPages, kind: str, attribute: str,
                        known: dict, notes: list) -> bool:
    """Adds to `known`, the need by the value of `attribute`, the values
    that show where each step ends: by halving between two values whose
    needs differ, and between the largest value the series took and the
    least it refused above that, where its range ends. Returns False where
    the need does not grow with the value, or could not be measured."""
    while True:
        ordered = sorted(known)
        if any(known[low] > known[high] for low, high in zip(ordered, ordered[1:])):
            notes.append("a %s's temporary need does not grow with its %s: not measured"
                         % (kind, attribute))
            return False
        middles = [(low + high) // 2 for low, high in zip(ordered, ordered[1:])
                   if known[low] != known[high] and high > low + 1]
        refused = [value for refused_kind, refused_attribute, value in probe.refused_values
                   if (refused_kind, refused_attribute) == (kind, attribute)
                   and value > ordered[-1]]
        end = [(ordered[-1] + min(refused)) // 2] if refused and \
            min(refused) > ordered[-1] + 1 else []
        if not middles and not end:
            return True
        measured = _buffer_needs(probe, pages, kind, attribute, middles + end)
        if None in measured.values():
            notes.append("a %s's temporary need by its %s could not be measured between its "
                         "values, its cost not known: not measured" % (kind, attribute))
            return False
        if any(middle not in measured for middle in middles):
            notes.append("a %s's %s is refused between values the series takes: its temporary "
                         "need is not measured" % (kind, attribute))
            return False
        known.update(measured)


def _buffer_needs(probe: SeriesProbe, pages: NeedPages, kind: str, buffer: str,
                  values: list) -> dict:
    """{value: need} of a type with its buffer `buffer` at each of `values`
    the series takes; None for one whose page cannot be filled."""
    specs = {value: (need_key(kind, buffer, value), (_with_buffer(probe, kind, buffer, value),))
             for value in values}
    measured = measure_needs(probe, pages, list(specs.values()))
    return {value: measured[key] for value, (key, components) in specs.items()
            if measured[key] is not None or probe.takes(Case(key, components))}


def _with_buffer(probe: SeriesProbe, kind: str, buffer: str, value: int) -> Component:
    """A component of `kind` with its buffer `buffer` at `value`, and the
    text the buffer bounds cut to its first `value` bytes where it is
    longer, as the build refuses a text past its buffer."""
    values = ((buffer, value),)
    stored = bounded_bytes(probe, kind, buffer)
    if len(stored) > value:
        values += ((bounded_text(kind, buffer), stored[:value].decode("utf-8", "ignore")),)
    return Component(kind, values)
