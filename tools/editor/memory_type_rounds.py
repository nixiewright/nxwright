"""The memory probe's rounds measuring each type's cost (memory_probe.py):
the page's part for each object; each type with its other attributes
varied, then each attribute alone where that changed its cost; the values
of each attribute that does, and of each buffer; two attributes together
where they do not add up; and a buffer counted under another attribute's
value. A rule is fitted to the costs of each (memory_fit.py)."""
from dataclasses import replace
from itertools import combinations

from nxwright.project.attribute_descriptions import describe
from nxwright.project.memory_table import TypeCosts
from tools.editor.memory_cases import FALLBACKS, KEPT, SCOPE, Case, Component, defaults, is_buffer
from tools.editor.memory_fit import fit_objects, fit_part, fit_times
from tools.editor.memory_series import (ProbeStopped, SeriesProbe, buffers_of, cost_of,
                                        grown_buffers, grown_together, grown_values,
                                        value_case, varied_case_values, varied_page_values)

# The counts of hotspots on the pages that show the part for each object.
OBJECT_COUNTS = range(2, 13)


def first_cases(probe: SeriesProbe) -> list:
    """The objects, each type varied, and each buffer grown."""
    cases = [Case("objects %d" % count, (Component("hotspot"),) * count)
             for count in OBJECT_COUNTS]
    for kind in probe.taken():
        varied = varied_case_values(probe, kind)
        if varied:
            cases.append(Case("varied %s" % kind, (Component(kind, tuple(varied.items())),)))
        for attribute in buffers_of(kind):
            cases += [value_case(kind, attribute, value)
                      for value in grown_values(probe, kind, attribute)]
        grown = grown_buffers(probe, kind)
        if len(grown) > 1:
            cases.append(Case("together %s" % kind, (Component(kind, grown),)))
    varied = varied_page_values(probe)
    if varied:
        cases.append(Case("varied page", (), tuple(varied.items())))
    return cases


def measure_types(probe: SeriesProbe, cost, notes: list) -> tuple:
    """Returns ({type: TypeCosts}, {type: {attribute: the value it was
    measured at}}): each type's cost and its attributes' parts, from the
    rounds of each attribute alone, of each one's values, of two together,
    and of a buffer under another attribute's value; and the attributes
    whose part is not known. `cost` gives a case's cost by its key."""
    probe.measure(lambda: split_cases(probe))
    probe.measure(lambda: value_cases(probe))
    types, unmeasured = {}, {}
    for kind in probe.taken():
        types[kind], unmeasured[kind] = _type_costs(probe, kind, cost, notes)
    probe.measure(lambda: pair_cases(probe, types))
    for kind in probe.taken():
        types[kind] = _paired(probe, kind, types[kind], cost, notes)
    probe.measure(lambda: interaction_cases(probe, types))
    for kind in probe.taken():
        types[kind] = _interacted(probe, kind, types[kind], cost, notes, unmeasured[kind])
    return types, unmeasured


def objects_part(probe: SeriesProbe) -> tuple:
    owns = {0: probe.owns["empty"], 1: probe.owns["type hotspot"]}
    owns.update({count: probe.owns["objects %d" % count] for count in OBJECT_COUNTS
                 if "objects %d" % count in probe.owns})
    fitted = fit_objects(owns)
    if fitted is None:
        raise ProbeStopped("no rule fits the pages of hotspots: %s" % owns)
    return fitted


def split_cases(probe: SeriesProbe) -> list:
    """Each attribute alone, of each type whose cost changed with all varied."""
    cases = []
    for kind in probe.taken():
        key = "varied %s" % kind
        if key not in probe.owns or probe.measured(key) == probe.measured("type %s" % kind):
            continue
        for attribute, value in probe.cases[key].components[0].values:
            cases.append(Case("varied %s %s" % (kind, attribute),
                              (Component(kind, ((attribute, value),)),)))
    return cases


def costly(probe: SeriesProbe, kind: str) -> list:
    """The attributes of `kind` whose value changed its cost: its buffers
    that did, and those whose case alone changed it."""
    alone = probe.measured("type %s" % kind)

    def changed(key: str) -> bool:
        return key in probe.owns and probe.measured(key) != alone
    found = [attribute for attribute in buffers_of(kind)
             if any(changed(value_case(kind, attribute, value).key)
                    for value in grown_values(probe, kind, attribute))]
    found += [attribute for attribute in defaults(kind)
              if changed("varied %s %s" % (kind, attribute))]
    return found


def value_cases(probe: SeriesProbe) -> list:
    """The values of each number, not a buffer, whose case changed its type's
    cost. A text that does is not measured (_type_costs)."""
    return [value_case(kind, attribute, value)
            for kind in probe.taken() for attribute in costly(probe, kind)
            if not is_buffer(attribute) and isinstance(probe.value(kind, attribute), int)
            for value in grown_values(probe, kind, attribute)]


def interaction_cases(probe: SeriesProbe, types: dict) -> list:
    """Each buffer grown with each other costly attribute changed, as a
    variable's `sta` changed: a buffer may count only under another's value,
    as a variable's `txt_maxl` counts once it holds text. Where that does not
    add up, the buffer's values with the other changed."""
    cases = []
    for kind in probe.taken():
        for attribute, value in _changed_costly(probe, kind):
            for buffer in buffers_of(kind):
                if buffer == attribute:
                    continue
                case = _with_case(kind, attribute, value, buffer,
                                  grown_together(probe, kind, buffer))
                cases.append(case)
                if case.key in probe.owns and not _adds_up_with(probe, kind, types[kind],
                                                               case):
                    cases += [_with_case(kind, attribute, value, buffer, other)
                              for other in grown_values(probe, kind, buffer)]
    return cases


def _changed_costly(probe: SeriesProbe, kind: str) -> list:
    """The costly numbers of `kind` that are not buffers, each with the
    value its case alone was measured at."""
    found = []
    for attribute in costly(probe, kind):
        case = probe.cases.get("varied %s %s" % (kind, attribute))
        if case is not None and not is_buffer(attribute) and \
                isinstance(probe.value(kind, attribute), int):
            found.append((attribute, dict(case.components[0].values)[attribute]))
    return found


def _with_case(kind: str, attribute: str, value: int, buffer: str, grown: int) -> Case:
    return Case("with %s %s %d %s %d" % (kind, attribute, value, buffer, grown),
                (Component(kind, ((attribute, value), (buffer, grown))),))


def _adds_up_with(probe: SeriesProbe, kind: str, costs: TypeCosts, case: Case) -> bool:
    """Whether a case of two attributes changed costs what the type's parts
    say it does."""
    base = {**defaults(kind), **probe.base[kind]}
    values = {**base, **dict(case.components[0].values)}
    return probe.measured(case.key) - probe.measured("type %s" % kind) == \
        cost_of(costs, values) - cost_of(costs, base)


def _interacted(probe: SeriesProbe, kind: str, costs: TypeCosts, cost, notes: list,
                unmeasured: dict) -> TypeCosts:
    """The type's costs, where a buffer counts only under another
    attribute's value: the buffer's part times that attribute, where that
    fits, as a variable's `txt_maxl` part counts times its `sta`. Where it
    does not, the other attribute is not measured away from its base."""
    parts = list(costs.parts)
    for attribute, value in _changed_costly(probe, kind):
        for buffer in buffers_of(kind):
            key = _with_case(kind, attribute, value, buffer,
                             grown_together(probe, kind, buffer)).key
            if buffer == attribute or key not in probe.owns or _adds_up_with(
                    probe, kind, TypeCosts(costs.cost, tuple(parts)), probe.cases[key]):
                continue
            points = {(grown, value): cost(_with_case(kind, attribute, value, buffer, grown).key)
                      for grown in grown_values(probe, kind, buffer)
                      if _with_case(kind, attribute, value, buffer, grown).key in probe.owns}
            by_part = {part.attribute: part for part in parts}
            fitted = fit_part(buffer, {grown: point for (grown, _), point in points.items()})
            times = None
            if fitted is not None and value == 1 and attribute in by_part:
                times = fit_times(fitted[0], by_part[attribute], probe.value(kind, buffer),
                                  points)
            if times is None:
                notes.append("a %s's %s does not add up with its %s %d: its %s is not "
                             "measured away from %r" % (kind, buffer, attribute, value,
                                                        attribute, probe.value(kind, attribute)))
                unmeasured[attribute] = probe.value(kind, attribute)
                continue
            parts = [part for part in parts if part.attribute not in (attribute, buffer)]
            parts += list(times[0])
    return _with_fixed(probe, kind, tuple(parts), cost)


def _type_costs(probe: SeriesProbe, kind: str, cost, notes: list) -> tuple:
    """Returns (TypeCosts, unmeasured) for `kind`: its cost and each costly
    attribute's part, fitted alone; and the attributes whose part is not
    known, with the values they were measured at.

    An attribute with a fallback (FALLBACKS) is fitted first, from its
    values but 0, where it reads the fallback. The fallback's own cases
    were measured with that attribute at its base, 0, reading them, so its
    part comes out of their costs before the fallback's part is fitted."""
    parts, unmeasured = [], {}
    for attribute in sorted(costly(probe, kind),
                            key=lambda attribute: (kind, attribute) not in FALLBACKS):
        if not isinstance(probe.value(kind, attribute), int):
            notes.append("a %s's %s, kept as text, changes its cost: not measured"
                         % (kind, attribute))
            unmeasured[attribute] = probe.value(kind, attribute)
            continue
        fallback = FALLBACKS.get((kind, attribute))
        base = probe.value(kind, attribute)
        values = {} if fallback is not None and base == 0 else {base: cost("type %s" % kind)}
        values.update({value: cost(value_case(kind, attribute, value).key)
                       for value in grown_values(probe, kind, attribute)
                       if value_case(kind, attribute, value).key in probe.owns})
        for reading in parts:
            if reading.fallback == attribute and probe.value(kind, reading.attribute) == 0:
                values = {value: point - reading.of(value) for value, point in values.items()}
        description = describe(kind, attribute)
        # A choice takes only its choices, which are all measured, but those refused.
        fitted = fit_part(attribute, values,
                          sorted(values) if description and description.choices else None)
        if fitted is None:
            notes.append("no rule fits a %s's costs by its %s: %s" % (kind, attribute, values))
            unmeasured[attribute] = probe.value(kind, attribute)
        elif fitted[0].bytes:
            parts.append(replace(fitted[0], fallback=fallback))
    for buffer in buffers_of(kind):
        # A buffer measured at its base alone is not known to cost nothing.
        if not any(value_case(kind, buffer, value).key in probe.owns
                   for value in grown_values(probe, kind, buffer)):
            notes.append("a %s's %s was measured at %r alone: not measured away from it"
                         % (kind, buffer, probe.value(kind, buffer)))
            unmeasured[buffer] = probe.value(kind, buffer)
    varied = probe.cases.get("varied %s" % kind)
    varied_attributes = {attribute for attribute, _ in varied.components[0].values} \
        if varied else set()
    for attribute, value in defaults(kind).items():
        if attribute in KEPT - {SCOPE} or (attribute not in varied_attributes
                                           and not is_buffer(attribute)
                                           and attribute != SCOPE):
            unmeasured.setdefault(attribute, probe.value(kind, attribute))
    return _with_fixed(probe, kind, tuple(parts), cost), unmeasured


def _with_fixed(probe: SeriesProbe, kind: str, parts: tuple, cost) -> TypeCosts:
    """The type's costs, its fixed part what its cost with its base values
    leaves of its parts'."""
    values = {**defaults(kind), **probe.base[kind]}
    fixed = cost("type %s" % kind) - sum(part.cost_in(values) for part in parts)
    return TypeCosts(fixed, parts)


def pair_cases(probe: SeriesProbe, types: dict) -> list:
    """For each type with costly attributes whose costs, grown together, do
    not add up, or which were not grown together: each two of them together,
    at three values each."""
    cases = []
    for kind, costs in types.items():
        attributes = [part.attribute for part in costs.parts]
        if len(attributes) < 2 or _adds_up(probe, kind, costs):
            continue
        for first, second in combinations(attributes, 2):
            for first_value in _three(probe, kind, first):
                for second_value in _three(probe, kind, second):
                    cases.append(Case("pair %s %s %s %s %s" % (kind, first, first_value, second,
                                                              second_value),
                                      (Component(kind, ((first, first_value),
                                                        (second, second_value))),)))
    return cases


def _adds_up(probe: SeriesProbe, kind: str, costs: TypeCosts) -> bool:
    """Whether a type's case of its buffers grown together costs what its
    parts add up to; False when there is no such case, or it holds other
    costly attributes."""
    key = "together %s" % kind
    if key not in probe.owns:
        return False
    values = {**defaults(kind), **probe.base[kind], **dict(probe.cases[key].components[0].values)}
    if any(part.attribute not in dict(probe.cases[key].components[0].values)
           for part in costs.parts):
        return False
    return probe.measured(key) - probe.measured("type %s" % kind) == \
        cost_of(costs, values) - cost_of(
            costs, {**defaults(kind), **probe.base[kind]})


def _three(probe: SeriesProbe, kind: str, attribute: str) -> list:
    """Three of an attribute's measured values: its first, middle, and last."""
    values = [value for value in grown_values(probe, kind, attribute)
              if value_case(kind, attribute, value).key in probe.owns]
    return sorted({values[0], values[len(values) // 2], values[-1]}) if values else []


def _paired(probe: SeriesProbe, kind: str, costs: TypeCosts, cost, notes: list) -> TypeCosts:
    """The type's costs, where its pairs did not add up, with one part times
    another, as a waveform's channels its width's, where that fits."""
    pairs = {}
    for key in probe.owns:
        words = key.split()
        if words[0] == "pair" and words[1] == kind:
            pairs.setdefault((words[2], words[4]), {})[(int(words[3]), int(words[5]))] = \
                cost(key)
    if not pairs:
        return costs
    base = {**defaults(kind), **probe.base[kind]}
    parts = list(costs.parts)
    for (first, second), points in pairs.items():
        if all(cost_of(TypeCosts(costs.cost, tuple(parts)),
                        {**base, first: first_value, second: second_value}) == point
               for (first_value, second_value), point in points.items()):
            continue
        by_part = {part.attribute: part for part in parts}
        fitted = None
        for one, other in ((first, second), (second, first)):
            ordered = {(values if one == first else values[::-1]): point
                       for values, point in points.items()}
            fitted = fit_times(by_part[one], by_part[other], base[one], ordered)
            if fitted is not None:
                parts = [part for part in parts if part.attribute not in (one, other)]
                parts += list(fitted[0])
                break
        if fitted is None:
            notes.append("a %s's %s and %s do not add up, nor one times the other"
                         % (kind, first, second))
            return TypeCosts(costs.cost, ())
    return _with_fixed(probe, kind, tuple(parts), cost)
