"""The memory probe's state for one series, and what its rounds build on
(memory_probe.py): what the compile measured and refused (SeriesProbe), the
cases and values each round makes from the series' base, and the halving
the rounds share (failing). Its tests run the probe against a stand-in
Editor (tests/test_memory_probe.py)."""
from dataclasses import dataclass, field

from nxwright.project.attribute_descriptions import describe
from nxwright.project.editor_limits import LEAST_SIDE
from nxwright.project.memory_table import TypeCosts
from nxwright.project.screen_models import model_named
from tools.editor.memory_cases import (SCOPE, TYPES, Case, Component, Project, bounded_text,
                                       defaults, is_buffer, most_value, placement,
                                       varied_values)

# The most pages a probe project holds: the Editor compiled 251, and
# refused 313, "Too many pages".
MOST_PAGES = 250
# How much a value moves from its base in the cases of its values: a run of
# small steps shows its rounding, and larger ones its slope.
GROWTHS = tuple(range(1, 13)) + (50, 100, 200)
# What every buffer grows by in the cases that grow a type's together.
TOGETHER = 100
PLACE = ("x", "y", "w", "h")
# The types whose temporary need the compile refuses, by the words it names
# them with: "the temporary use of QR code(-443)".
NEED_WORDS = {"QR code": "qr-code"}
# The first word of the keys of the cases that measure a temporary need.
NEED = "need"


class ProbeStopped(Exception):
    """Something the probe cannot go on from: the message says what."""


@dataclass
class CompiledProject:
    """A project the compile took: what it showed, and its pages as built."""
    project: Project
    shown: object
    pages: list


@dataclass(frozen=True)
class MeasuredNeed:
    """A temporary need measured on a page that leaves nothing of the
    screen's memory, so that the compile refuses it by the whole need, or
    takes it, needing none: the page as built, the need in bytes, and the
    project's pages and its count of `int`s beyond sys0 to sys2, which its
    global memory counts."""
    page: object
    need: int
    pages: list
    ints: int


@dataclass
class SeriesProbe:
    """Measures one series, on its model `model`, keeping what the compile
    refused: types, values of cases, and base values, which it replaces; and
    the values whose temporary need is more than their page leaves.

    A type whose local scope the series refuses is global alone: its cases
    are compiled each in a project of its own, whose global memory, past an
    empty project's, holds what it keeps there (`measured`)."""
    runner: object
    model: str
    owns: dict = field(default_factory=dict)          # {case key: own memory}
    cases: dict = field(default_factory=dict)         # {case key: Case, as measured}
    compiled: list = field(default_factory=list)      # [CompiledProject]
    refused_types: set = field(default_factory=set)
    refused_values: set = field(default_factory=set)  # {(type, attribute, value)}
    replaced: dict = field(default_factory=dict)      # {(type, attribute): (default, value)}
    base: dict = field(default_factory=dict)          # {type: {attribute: value}}
    memory: int = None
    needs: dict = field(default_factory=dict)         # {need case key: MeasuredNeed}
    need_refused: set = field(default_factory=set)    # {(type, attribute, value)}
    global_only: set = field(default_factory=set)     # {type}
    # The global memory of an empty project, and of each case compiled alone.
    empty_global: int = None
    alone_global: dict = field(default_factory=dict)  # {case key: global memory}

    def __post_init__(self):
        width, height = self.screen_size()
        for kind in TYPES:
            self.base[kind] = dict(placement(kind, width, height))
            if SCOPE in defaults(kind):
                self.base[kind][SCOPE] = 0

    def screen_size(self) -> tuple:
        model = model_named(self.model)
        return model.width, model.height

    def taken(self) -> list:
        return [kind for kind in TYPES if kind not in self.refused_types]

    def value(self, kind: str, attribute: str):
        """An attribute's value in the base of `kind`."""
        return self.base[kind].get(attribute, defaults(kind).get(attribute))

    def measure(self, make_cases, **settings) -> list:
        """Measures each case `make_cases()` gives that is not measured yet,
        making them again after each refusal, so that they take it into
        account: a project of the cases at a time, and a case of a type
        global alone in a project of its own. Returns what it compiled that
        the compile took."""
        took = []
        while True:
            cases = [case for case in make_cases() if case.key not in self.owns
                     and self.takes(case)]
            if not cases:
                return took
            alone = [case for case in cases if self.is_global_only(case)]
            together = [case for case in cases if case not in alone]
            before = self.progress()
            compiled = self.compile(tuple(together[:MOST_PAGES - 1]), **settings) \
                if together else self.compile((alone[0],), **settings)
            if compiled is not None:
                took.append(compiled)
            elif self.progress() == before:
                # Compiling it again would give the same refusal, as when the
                # empty page itself overflows.
                raise ProbeStopped("a compile on %s measured nothing new, and refused "
                                   "nothing the probe can leave out" % self.model)

    def is_global_only(self, case: Case) -> bool:
        """Whether `case` holds a component of a type global alone."""
        return any(component.kind in self.global_only for component in case.components)

    def measured(self, key: str) -> int:
        """What a case measured cost its page: its page's own memory, and,
        for a case compiled alone, what its project's global memory holds
        past an empty project's, which a type global alone keeps there."""
        global_part = self.alone_global[key] - self.empty_global if key in self.alone_global \
            else 0
        return self.owns[key] + global_part

    def progress(self) -> tuple:
        """What a compile adds to as it measures or refuses."""
        return (len(self.owns), len(self.refused_types), len(self.refused_values),
                len(self.replaced), len(self.needs), len(self.need_refused),
                len(self.global_only))

    def compile(self, cases: tuple, **settings):
        """Compiles one project of `cases`, keeping each page's own memory,
        and the temporary need of each page that measures one. Returns its
        CompiledProject, or None when the compile refused it, having taken
        the refusal into account."""
        project = Project(self.model, cases, self._base_items(cases), **settings)
        shown, pages = self.runner.compile(project)
        named = list(zip(project.page_names(), (Case("empty"),) + cases))
        for name, case in named:
            if name in shown.pages and case.key not in self.owns:
                self.owns[case.key] = shown.pages[name]
                self.cases[case.key] = case
        self._take_needs(named, pages, shown, project.ints)
        if not shown.succeeded:
            self._take_refusal(project, shown.refusal)
            return None
        self.memory = shown.memory
        if not cases and project.ints == 0:
            self.empty_global = shown.global_memory
        if len(cases) == 1 and self.is_global_only(cases[0]):
            self.alone_global.setdefault(cases[0].key, shown.global_memory)
        compiled = CompiledProject(project, shown, pages)
        self.compiled.append(compiled)
        return compiled

    def _take_needs(self, named: list, pages: list, shown, ints: int):
        """Keeps the temporary need of each page of `named`, [(page name,
        Case)], that measures one: none where the compile took it, and the
        bytes missing where it refused it so. Pages are taken in order, and
        those after a refusal are not reached."""
        built = {page.name: page for page in pages}
        refused_at = shown.refusal[1] if shown.refusal and shown.refusal[0] == "temporary" \
            else None
        if not shown.succeeded and refused_at is None:
            # Refused otherwise: what it reached of the needs is not known.
            return
        for name, case in named:
            if name == refused_at:
                if case.key.startswith(NEED):
                    self.needs[case.key] = MeasuredNeed(built[name], shown.refusal[3], pages,
                                                        ints)
                return
            if case.key.startswith(NEED):
                self.needs.setdefault(case.key, MeasuredNeed(built[name], 0, pages, ints))

    def _base_items(self, cases: tuple) -> tuple:
        kinds = sorted({component.kind for case in cases for component in case.components})
        return tuple((kind, tuple(sorted(self.base[kind].items()))) for kind in kinds)

    def takes(self, case: Case) -> bool:
        """Whether the series takes what `case` holds, as far as is known. A
        value whose temporary need its page cannot hold is left out of the
        cases that measure costs, not of those that measure needs."""
        refused = self.refused_values if case.key.startswith(NEED) else \
            self.refused_values | self.need_refused
        for component in case.components:
            if component.kind in self.refused_types:
                return False
            if any((component.kind, attribute, value) in refused
                   for attribute, value in component.values):
                return False
        return not any(("page", attribute, value) in self.refused_values
                       for attribute, value in case.page_values)

    def _take_refusal(self, project: Project, refusal: tuple):
        """Takes what a compile refused into account, or raises ProbeStopped."""
        if refusal is None or refusal[0] == "other":
            raise ProbeStopped("the compile of %s refused it: %s" % (project.name(), refusal))
        if refusal[0] == "overflow":
            return      # measured, and the cases after it are compiled again
        case = dict(zip(project.page_names(), (Case("empty"),) + project.cases))[refusal[1]]
        if refusal[0] == "temporary":
            self._take_need_refusal(case, refusal)
            return
        if refusal[2] == refusal[1]:
            # The page's own attribute.
            self.refused_values.add(("page", refusal[3], dict(case.page_values)[refusal[3]]))
            return
        component = case.components[int(refusal[2][1:])]
        if refusal[0] == "unsupported":
            self.refused_types.add(component.kind)
            return
        kind, attribute = component.kind, refusal[3]
        own = dict(component.values)
        if attribute in own:
            self.refused_values.add((kind, attribute, own[attribute]))
            return
        # The base itself: measured at the first other value the series takes.
        refused = self.value(kind, attribute)
        self.refused_values.add((kind, attribute, refused))
        if attribute == SCOPE and refused == 0:
            # Local scope refused: the type is measured at global scope alone.
            self.global_only.add(kind)
            self.base[kind][SCOPE] = 1
            return
        default, _ = self.replaced.get((kind, attribute), (refused, None))
        others = [value for value in varied_values(kind, attribute,
                                                   {**defaults(kind), attribute: default})
                  if (kind, attribute, value) not in self.refused_values]
        if not others:
            raise ProbeStopped("the compile refused every value of a %s's %s it was given"
                               % (kind, attribute))
        self.replaced[(kind, attribute)] = (default, others[0])
        self.base[kind][attribute] = others[0]

    def _take_need_refusal(self, case: Case, refusal: tuple):
        """Takes a refusal of a page whose temporary need is more than it
        leaves of the screen's memory: measured, where the page measures a
        need (_take_needs); else the one value its case changes is left out
        of the cases that measure costs. Raises ProbeStopped for a type the
        probe does not know by the compile's words, and for a case of more
        than one component or value, which the probe does not make so big."""
        if case.key.startswith(NEED):
            return
        kind = NEED_WORDS.get(refusal[2])
        if kind is None:
            raise ProbeStopped("the compile refused the temporary need of a %s, which the "
                               "probe does not know" % refusal[2])
        if len(case.components) != 1 or case.components[0].kind != kind or \
                len(case.components[0].values) != 1:
            raise ProbeStopped("the compile refused the temporary need of a %s on %s's page "
                               "%s" % (kind, self.model, case.key))
        (attribute, value), = case.components[0].values
        self.need_refused.add((kind, attribute, value))


def type_cases(probe: SeriesProbe, prefix: str = "type", scope: int = 0, kinds=None) -> list:
    """A page per type, with its base values, of local or global scope."""
    return [Case("%s %s" % (prefix, kind), (Component(kind, ((SCOPE, 1),) if scope else ()),))
            for kind in (kinds or probe.taken()) if scope == 0 or SCOPE in defaults(kind)]


def buffers_of(kind: str) -> list:
    return [attribute for attribute in defaults(kind) if is_buffer(attribute)]


def value_case(kind: str, attribute: str, value) -> Case:
    return Case("value %s %s %s" % (kind, attribute, value),
                (Component(kind, ((attribute, value),)),))


def grown_values(probe: SeriesProbe, kind: str, attribute: str) -> list:
    """The values of an attribute's cases: its other choices, or its base
    moved by each of GROWTHS, both ways, where the screen and its range
    allow. A buffer moves one way alone (buffer_way), and not below the
    text it bounds, which the build refuses past its buffer."""
    base = probe.value(kind, attribute)
    description = describe(kind, attribute)
    if description is not None and description.choices:
        return [choice for choice in sorted(description.choices) if choice != base]
    if is_buffer(attribute):
        values = [base + buffer_way(probe, kind, attribute) * growth for growth in GROWTHS]
        least = len(bounded_bytes(probe, kind, attribute))
    else:
        values = [base + growth for growth in GROWTHS] + [base - growth for growth in GROWTHS]
        least = LEAST_SIDE if attribute in ("w", "h") else 0
    width, height = probe.screen_size()
    most = {"x": width - 1, "w": width, "y": height - 1, "h": height}.get(attribute)
    return sorted(value for value in values
                  if least <= value <= most_value(kind, attribute)
                  and (most is None or value <= most))


def buffer_way(probe: SeriesProbe, kind: str, buffer: str) -> int:
    """Which way the cases move a buffer from its base: 1, growing it, or
    -1, shrinking it, where it cannot grow: past the most its bytes hold, or
    once the series refused it past its base, as an Intelligent screen
    refuses a data record's `path_m` past 255."""
    past = probe.value(kind, buffer) + 1
    return -1 if past > most_value(kind, buffer) or (kind, buffer, past) in probe.refused_values \
        else 1


def grown_together(probe: SeriesProbe, kind: str, buffer: str) -> int:
    """A buffer's value in the cases that change it beside the type's other
    attributes: TOGETHER from its base, the way its cases move it
    (buffer_way), but not below the text it bounds."""
    value = probe.value(kind, buffer) + buffer_way(probe, kind, buffer) * TOGETHER
    return max(value, len(bounded_bytes(probe, kind, buffer)))


def grown_buffers(probe: SeriesProbe, kind: str) -> tuple:
    """((buffer, value), ...): each buffer of `kind` at grown_together, but
    those at a value the series refused, or whose temporary need its page
    cannot hold."""
    refused = probe.refused_values | probe.need_refused
    return tuple((buffer, grown_together(probe, kind, buffer)) for buffer in buffers_of(kind)
                 if (kind, buffer, grown_together(probe, kind, buffer)) not in refused)


def bounded_bytes(probe: SeriesProbe, kind: str, buffer: str) -> bytes:
    """The text a buffer of `kind` bounds, with its base value, in bytes;
    empty for a buffer that bounds none, as `molloc`."""
    text = bounded_text(kind, buffer)
    return probe.value(kind, text).encode("utf-8") if text is not None else b""


def varied_case_values(probe: SeriesProbe, kind: str) -> dict:
    """The first value each attribute of `kind` may take in place of its
    base value, for those that have one. A value the series refused for the
    same attribute of any type is passed over: the compile names one refusal
    a run, and any other value shows as well whether the attribute counts."""
    base = {**defaults(kind), **probe.base[kind]}
    width, height = probe.screen_size()
    most = {"x": width - 1, "w": width, "y": height - 1, "h": height}
    refused = {(attribute, value) for _, attribute, value in probe.refused_values}
    varied = {}
    for attribute in defaults(kind):
        values = [value for value in varied_values(kind, attribute, base)
                  if (attribute, value) not in refused and value <= most.get(attribute, value)]
        if values:
            varied[attribute] = values[0]
    return varied


def varied_page_values(probe: SeriesProbe) -> dict:
    """The page's own attributes varied: not its place, nor its scope."""
    base = defaults("page")
    varied = {}
    for attribute in base:
        if attribute in PLACE:
            continue
        values = [value for value in varied_values("page", attribute, base)
                  if ("page", attribute, value) not in probe.refused_values]
        if values:
            varied[attribute] = values[0]
    return varied


def cost_of(costs: TypeCosts, values: dict) -> int:
    return costs.cost + sum(part.cost_in(values) for part in costs.parts)


def failing(items: list, holds) -> set:
    """The items for which `holds` fails, asked of a group at a time: of
    all of them, then of each half of a group that fails, down to single
    items. A group that fails while both its halves hold has items that
    count together, so all of them fail."""
    if not items or holds(items):
        return set()
    if len(items) == 1:
        return set(items)
    half = len(items) // 2
    found = failing(items[:half], holds) | failing(items[half:], holds)
    return found or set(items)


def global_of(probe: SeriesProbe, cases: tuple, base_global: int) -> int:
    """What a project of `cases` adds to global memory: its global memory,
    less an empty project's."""
    compiled = probe.compile(cases)
    if compiled is None:
        raise ProbeStopped("the compile refused cases it took before on %s: %s"
                           % (probe.model, [case.key for case in cases]))
    return compiled.shown.global_memory - base_global
