"""The memory probe's rounds of global memory (memory_probe.py): what each
type reserves there, with its base values and with its buffers grown; and
what a component of global scope keeps on its page and in global memory,
the types halved until those that do not cost as the others do are found."""
from tools.editor.memory_cases import SCOPE, Case, Component, defaults
from tools.editor.memory_fit import fit_part
from tools.editor.memory_series import (ProbeStopped, SeriesProbe, buffers_of, cost_of, failing,
                                        global_of, grown_buffers, grown_together, grown_values,
                                        type_cases)

def measure_reserves(probe: SeriesProbe, base_global: int, notes: list) -> dict:
    """What each type reserves in global memory, whatever its scope, with
    its base values, found by halving the types until each group reserves
    nothing or is one type."""
    found = {}

    def halve(kinds: list, total: int):
        if total == 0:
            return
        if len(kinds) == 1:
            found[kinds[0]] = total
            return
        first, second = kinds[:len(kinds) // 2], kinds[len(kinds) // 2:]
        first_total = global_of(probe, tuple(type_cases(probe, "reserve " + " ".join(first),
                                                          0, first)), base_global)
        halve(first, first_total)
        halve(second, total - first_total)
    types = next(compiled for compiled in probe.compiled
                 if compiled.project.cases and compiled.project.cases[0].key.startswith("type "))
    kinds = [case.components[0].kind for case in types.project.cases]
    # A type global alone keeps what it reserves in its cost (SeriesProbe).
    for kind in sorted(set(probe.taken()) - set(kinds) - probe.global_only):
        # Measured as it overflowed the screen alone: nothing else fits beside it.
        notes.append("a %s fills the screen's memory alone; what it reserves in global "
                     "memory was not measured, and is taken as none" % kind)
    halve(kinds, types.shown.global_memory - base_global)
    for kind, reserve in found.items():
        notes.append("a %s reserves %d bytes of global memory, whatever its scope"
                     % (kind, reserve))
    return found


def measure_reserve_parts(probe: SeriesProbe, reserves: dict, base_global: int, notes: list,
                   unmeasured: dict) -> dict:
    """{type: (Part, ...)}, the part of each buffer whose value changes what
    its type reserves in global memory, as a buffer held there may: the
    buffers grown, a case each, are halved until those that change it are
    found, then each is measured value by value. A buffer whose reserve no
    rule fits is not measured away from its base."""
    def reserve_case(kind: str, buffer: str, value: int) -> Case:
        return Case("reserve %s %s %d" % (kind, buffer, value),
                    (Component(kind, ((buffer, value),)),))

    def grown(item: tuple) -> Case:
        kind, buffer = item
        return reserve_case(kind, buffer, grown_together(probe, kind, buffer))

    def holds(items: list) -> bool:
        return global_of(probe, tuple(grown(item) for item in items), base_global) == sum(
            reserves.get(kind, 0) for kind, _ in items)
    parts = {}
    # A value whose temporary need its page cannot hold is left out, and so is
    # a type global alone, whose buffers' parts its cost holds.
    buffers = [(kind, buffer) for kind in probe.taken() if kind not in probe.global_only
               for buffer in buffers_of(kind) if probe.takes(grown((kind, buffer)))]
    for kind, buffer in sorted(failing(buffers, holds)):
        base = probe.value(kind, buffer)
        values = {base: reserves.get(kind, 0)}
        values.update({value: global_of(probe, (reserve_case(kind, buffer, value),),
                                         base_global)
                       for value in grown_values(probe, kind, buffer)
                       if probe.takes(reserve_case(kind, buffer, value))})
        fitted = fit_part(buffer, values)
        if fitted is None:
            notes.append("no rule fits what a %s reserves in global memory by its %s: %s"
                         % (kind, buffer, values))
            unmeasured[kind][buffer] = base
            continue
        parts.setdefault(kind, []).append(fitted[0])
        notes.append("what a %s reserves in global memory grows with its %s" % (kind, buffer))
    return {kind: tuple(found) for kind, found in parts.items()}


def reserve_at(probe: SeriesProbe, kind: str, reserves: dict, reserve_parts: dict,
                values: dict) -> int:
    """What a component of `kind` reserves in global memory with `values`:
    what it reserves with its base values, its buffers' parts moved from
    their base values to those."""
    base = {**defaults(kind), **probe.base[kind]}
    return reserves.get(kind, 0) + sum(part.cost_in(values) - part.cost_in(base)
                                       for part in reserve_parts.get(kind, ()))


def measure_global_scope(probe: SeriesProbe, types: dict, reserves: dict, reserve_parts: dict,
                  base_global: int, step: int, empty_own: int, needing: set,
                  notes: list) -> tuple:
    """Returns (what a component of global scope keeps on its page, the
    types whose global scope costs as the table says: that on its page, the
    rest of its cost in global memory, with its base values and its buffers
    grown). The types are halved until those that do not are found. A type
    of `needing`, which needs temporary memory, is measured in a project of
    its own: the global memory the others add would leave its page too
    little."""
    # A type global alone has no other scope to measure apart.
    kinds = [kind for kind in probe.taken()
             if SCOPE in defaults(kind) and kind not in probe.global_only]

    def scoped_cases(group: list) -> tuple:
        name = "global %s:" % "+".join(group)
        cases = []
        for kind in group:
            cases.append(Case("%s %s" % (name, kind), (Component(kind, ((SCOPE, 1),)),)))
            grown = grown_buffers(probe, kind)
            if grown:
                cases.append(Case("%s %s grown" % (name, kind),
                                  (Component(kind, ((SCOPE, 1),) + grown),)))
        return tuple(cases)
    together = [kind for kind in kinds if kind not in needing]
    kept = {}
    for group in ([together] if together else []) + [[kind] for kind in kinds if kind in needing]:
        compiled = _scoped_compile(probe, group, scoped_cases)
        if compiled is None:
            continue
        for page_name, case in zip(compiled.project.page_names()[1:], compiled.project.cases):
            kind = case.components[0].kind
            kept.setdefault(kind, set()).add(compiled.shown.pages[page_name] - empty_own - step)
    for kind in sorted(kind for kind in kinds if kind not in kept):
        notes.append("the compile refused a %s of global scope: measured at local scope alone"
                     % kind)
    if not kept:
        # page_memory counts what a type global alone keeps on its page so.
        raise ProbeStopped("the compile took no component of global scope on %s, so what one "
                           "keeps on its page is not known" % probe.model)
    global_component = min(min(values) for values in kept.values())
    candidates = [kind for kind in kinds if kept.get(kind) == {global_component}]

    def holds(group: list) -> bool:
        expected = 0
        for case in scoped_cases(group):
            kind = case.components[0].kind
            values = {**defaults(kind), **probe.base[kind], **dict(case.components[0].values)}
            expected += cost_of(types[kind], values) - global_component + reserve_at(
                probe, kind, reserves, reserve_parts, values)
        return global_of(probe, scoped_cases(group), base_global) == expected
    scoped = set(candidates) - failing([kind for kind in candidates if kind not in needing], holds)
    scoped -= {kind for kind in candidates if kind in needing and not holds([kind])}
    # A type the compile refused at global scope is noted so already.
    for kind in sorted(set(kept) - scoped):
        notes.append("a %s of global scope does not cost as others do: not measured"
                     % kind)
    return global_component, scoped


def _scoped_compile(probe: SeriesProbe, group: list, scoped_cases):
    """Compiles the types of `group` at global scope, `scoped_cases(group)`,
    again without each type whose global scope the compile refuses, until
    it takes them. Returns the CompiledProject, or None when it refused
    every one."""
    while True:
        group = [kind for kind in group if (kind, SCOPE, 1) not in probe.refused_values]
        if not group:
            return None
        before = probe.progress()
        compiled = probe.compile(scoped_cases(group))
        if compiled is not None:
            return compiled
        if probe.progress() == before:
            raise ProbeStopped("the compile refused the types of global scope on %s, and "
                               "nothing the probe can leave out: %s"
                               % (probe.model, ", ".join(group)))
