"""Measures what the Nextion Editor's compile counts in memory, on each series
of screens, and writes the table nxwright reads,
nxwright/project/memory_costs.toml (nxwright/project/memory_table.py says
what it holds).

    python tools/editor/memory_probe.py [folder] [--series T,K,P,E,F]

Run it with the tool's own Python, from nxwright's folder. It builds probe
projects with nxwright, a page per case (memory_cases.py), opens and
compiles each in the dedicated Editor (editor.py's open and compile), and
reads what each page cost (memory_fit.py). A series' probe, and what its
rounds share, is memory_series.py; the rounds are memory_type_rounds.py,
memory_global_rounds.py, and memory_need_rounds.py. Per series, on one of
its models:
- each type's cost, with its defaults, and pages of 2 to 12 hotspots, for
  the page's part for each object;
- each type with every other attribute changed; where its cost changed,
  each attribute alone; then the values of each that changed it. One that
  reads another while it is 0 (memory_cases.FALLBACKS) is fitted from its
  other values, and its part taken out of the other's costs;
- each buffer attribute grown, value by value, or shrunk where it cannot
  grow, and all of a type's together; and where two attributes do not add
  up, the two together;
- each type's temporary need, as a QR code's, on pages filled to the
  screen's memory (NeedPages), by the attribute it follows, in steps;
- global memory: its base, each `int`, what each type reserves there, and
  what a component of each type takes there when of global scope, each
  with its buffers grown too, as a buffer may be held there;
- pages of mixed types, with event code, whose costs must add up;
- each type that has a `key`, of global scope, bound to the keypad, whose
  page its project holds: whether a keyboard's binding changes any cost.
And each model's memory, from an empty project; the types again on a
second model of one series; and the types again in utf-8, the screen
turned. A type the compile refuses on a series is recorded so, as is
each value it refuses, and a default it refuses is measured at the first
other value it takes: a type the series takes of global scope alone is
measured so (SeriesProbe), and one it takes of local scope alone keeps
its global scope unmeasured.

Last, it checks the table against every page and project it compiled, as
page_memory.py computes them from the pages as built, and writes the
series that agree in full. It says what it could not measure, and each
time `open` restarted the Editor. With --series, the series not measured
keep what the table holds.

Each project and its compile stay in `folder`, by default
tools/editor/build/memory, which git ignores, so that a run that stopped
goes on where it was. It deletes nothing but the one sound file it writes
for a project, once the project holds the sound (memory_cases.py). It
holds the dedicated Editor for its run, as memory-probe-<its process ID>
(editor.py hold), so that no one else's command lands between its open
and compile, and stops at once when another holds it.
"""
import argparse
import os
from dataclasses import dataclass, replace
from pathlib import Path
import subprocess
import sys

# Run as a script, so the folder above tools/ is put first on the import path.
NXWRIGHT_FOLDER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NXWRIGHT_FOLDER))

from nxwright import NxwrightError  # noqa: E402
from nxwright.project.container import HmiContainer  # noqa: E402
from nxwright.project.memory_table import (TABLE_FILE, Part, SeriesCosts,  # noqa: E402
                                           TypeCosts, memory_table)
from nxwright.project.page_block import parse_page  # noqa: E402
from nxwright.project.page_memory import Unmeasured, global_memory, page_memory  # noqa: E402
from nxwright.project.screen_models import MODELS, model_named  # noqa: E402
from tools.editor.memory_cases import (SCOPE, Case, Component, Project,  # noqa: E402
                                       build_project, defaults)
from tools.editor.memory_fit import read_compile, table_text  # noqa: E402
from tools.editor.memory_global_rounds import (measure_global_scope,  # noqa: E402
                                               measure_reserve_parts, measure_reserves)
from tools.editor.memory_need_rounds import NeedPages, need_key, temporary_needs  # noqa: E402
from tools.editor.memory_series import (PLACE, CompiledProject, ProbeStopped,  # noqa: E402
                                        SeriesProbe, type_cases, varied_page_values)
from tools.editor.memory_type_rounds import (first_cases, measure_types,  # noqa: E402
                                             objects_part)

EDITOR = Path(__file__).resolve().parent / "editor.py"
EDITOR_VERSION = "3.1.73"
# The holder whose hold keeps the dedicated Editor this run's, and for how
# long each of its commands renews it, in minutes: the longest a hold lasts.
HOLDER = "memory-probe-%d" % os.getpid()
HOLD_MINUTES = 60
# The model each series is measured on, and a second model of one series,
# measured again, as costs are taken to be the series'.
MEASURED_ON = {"T": "NX4832T035", "K": "NX4832K035", "P": "NX8048P050", "E": "NX4848E040",
               "F": "NX4832F035"}
SECOND_MODEL = "NX3224T024"
# The ints program.nx declares: sys0 to sys2, and those the project that
# shows an int's cost adds.
BASE_INTS, MORE_INTS = 3, 4
# Event code on the mixed pages, which must cost no memory.
MIXED_CODE = "on <page>.load:\n  sys0 = sys0 + 1\n  sys1 = 2\n"
# The keyboard the round of keyboards binds its components to, by its kind
# (keyboard_adding.add_keyboard) and by its `key`: the numeric keypad.
KEYPAD, KEYPAD_KEY = "keypad", 2


class EditorRunner:
    """Compiles probe projects in the dedicated Editor, keeping each one's
    compile in its folder, where a later run finds it. Used as a context, it
    holds the dedicated Editor for the run (editor.py hold), so that no one
    else's command lands between its open and compile, and gives it back
    after."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.restarts = []

    def __enter__(self):
        self._command("hold", HOLDER, "--minutes", str(HOLD_MINUTES), held=False)
        return self

    def __exit__(self, *_):
        try:
            self._command("release", HOLDER, held=False)
        except ProbeStopped as error:
            print("The hold %s was not released: %s" % (HOLDER, error), file=sys.stderr)

    def compile(self, project: Project) -> tuple:
        """Returns (what the compile showed, as a memory_fit.Compiled; the
        project's pages as built)."""
        place = self.folder / project.name()
        place.mkdir(parents=True, exist_ok=True)
        kept = place / "compile.txt"
        try:
            built = build_project(project, place)
        except NxwrightError as error:
            raise ProbeStopped("nxwright did not build %s: %s" % (place, error)) from None
        pages = [parse_page(block) for block in
                 HmiContainer.from_file(built).blocks_with_extension("pa").values()]
        if kept.exists():
            return read_compile(kept.read_text(encoding="utf-8")), pages
        opened = self._command("open", str(built))
        if "Closed the dedicated Editor" in opened:
            self.restarts.append(opened.splitlines()[0])
        copy = opened.splitlines()[-1].removeprefix("Opened ")
        first, _, output = self._command("compile").partition("\n")
        if first != "Compiled %s" % copy:
            # The hold keeps anyone else's open out, so this is not expected.
            raise ProbeStopped("the compile of %s named another project: %s" % (built, first))
        kept.write_text(output, encoding="utf-8")
        return read_compile(output), pages

    def _command(self, *command, held: bool = True) -> str:
        """Runs one command of editor.py, as the hold's holder unless
        `held` is False, and returns what it printed. Raises ProbeStopped
        when it stops, another holding the Editor among the reasons."""
        given = list(command) + (["--as", HOLDER] if held else [])
        done = subprocess.run([sys.executable, str(EDITOR)] + given, cwd=NXWRIGHT_FOLDER,
                              capture_output=True, text=True, encoding="utf-8")
        if done.returncode != 0:
            raise ProbeStopped("editor.py %s: %s" % (command[0], done.stderr.strip()))
        return done.stdout.strip()


@dataclass
class SeriesResult:
    """A series' costs, as measured, and what the probe found on the way."""
    costs: SeriesCosts
    notes: list


def measure_series(probe: SeriesProbe) -> SeriesResult:
    """Measures a series (the module's docstring) and fits its costs."""
    notes = []
    empty = probe.compile((), ints=0)
    with_ints = probe.compile((), ints=MORE_INTS)
    if empty is None or with_ints is None:
        raise ProbeStopped("an empty project did not compile on %s" % probe.model)
    base_global = empty.shown.global_memory
    int_bytes = (with_ints.shown.global_memory - base_global) // MORE_INTS
    # The types alone first, so that their project's global memory shows
    # what they reserve there.
    probe.measure(lambda: type_cases(probe))
    probe.measure(lambda: first_cases(probe))
    objects, _ = objects_part(probe)
    step = objects.of(2) - objects.of(1)
    empty_own = probe.owns["empty"]

    def cost(key: str) -> int:
        return probe.measured(key) - empty_own - step
    types, unmeasured = measure_types(probe, cost, notes)
    reserves = measure_reserves(probe, base_global, notes)
    reserve_parts = measure_reserve_parts(probe, reserves, base_global, notes, unmeasured)
    needs = temporary_needs(probe, NeedPages(probe, types, unmeasured, reserves, reserve_parts,
                                             base_global, empty_own, objects, cost), notes)
    global_component, scoped = measure_global_scope(probe, types, reserves, reserve_parts,
                                             base_global, step, empty_own, set(needs), notes)
    probe.measure(lambda: mixed_cases(probe, base_global + sum(reserves.values()), objects))
    page_costly = _page_costly(probe, empty_own)
    if page_costly:
        # The table holds a page's cost as one number, the same for every page.
        raise ProbeStopped("the page's own %s change its cost on %s, which the table cannot "
                           "hold" % (", ".join(sorted(page_costly)), probe.model))
    types = {kind: _table_type(probe, kind, types[kind], unmeasured[kind], kind in scoped,
                               reserves.get(kind, 0), reserve_parts.get(kind, ()),
                               needs.get(kind))
             for kind in probe.taken()}
    costs = SeriesCosts(empty_own - objects.of(1), objects, base_global - BASE_INTS * int_bytes,
                        int_bytes, global_component, types, frozenset(probe.refused_types),
                        _refused_values(probe))
    costs = _with_keyboards_measured(probe, costs, notes)
    return SeriesResult(costs, notes + _refusal_notes(probe))


def _with_keyboards_measured(probe: SeriesProbe, costs: SeriesCosts, notes: list) -> SeriesCosts:
    """Returns the costs with `key` measured, the keyboard a component is
    bound to, for each type that has one and whose global scope the costs
    measure, as a keyboard binds only a component of global scope. One
    project holds a page of each such type bound to the keypad, and the
    keypad's page. `key` only names the keyboard page it opens, a page
    counted as any other, so it is taken to change no cost at any value if
    that binding changes none. Where the compile counts otherwise, or holds
    what the costs do not measure, the costs stay as they are, `key`
    unmeasured away from 255, and a note says so."""
    kinds = [kind for kind in probe.taken() if "key" in defaults(kind)
             and costs.types[kind].unmeasured.get(SCOPE) != 0]
    if not kinds:
        return costs
    compiled = probe.compile(tuple(
        Case("keyboard %s" % kind, (Component(kind, ((SCOPE, 1), ("key", KEYPAD_KEY))),))
        for kind in kinds), keyboards=(KEYPAD,))
    if compiled is None:
        raise ProbeStopped("the compile refused components bound to the keypad on %s"
                           % probe.model)
    measured = replace(costs, types={
        kind: replace(type_costs, unmeasured={attribute: value for attribute, value
                                              in type_costs.unmeasured.items()
                                              if attribute != "key"})
        if kind in kinds else type_costs for kind, type_costs in costs.types.items()})
    try:
        # Every page counted, the keypad's among them, else nothing is shown.
        global_memory(measured, compiled.pages, BASE_INTS + compiled.project.ints)
    except Unmeasured as unmeasured:
        notes.append("the keypad's project holds what the costs do not measure on %s, %s: key "
                     "is not measured away from 255" % (probe.model, unmeasured))
        return costs
    if _disagreements(measured, compiled):
        notes.append("a component bound to the keypad changes what the compile counts on %s: "
                     "key is not measured away from 255" % probe.model)
        return costs
    return measured


def _table_type(probe: SeriesProbe, kind: str, costs: TypeCosts, unmeasured: dict,
                scoped: bool, reserve: int, reserve_parts: tuple, need) -> TypeCosts:
    """A type's costs as the table holds them. Its scope is unmeasured away
    from the one it was measured at, unless `scoped`, its global scope
    measured. What it reserves in global memory, `reserve` with its base
    values, is kept as a fixed part and its buffers' parts. `need` is its
    temporary need, as Steps, or None."""
    kept = dict(unmeasured)
    if kind in probe.global_only:
        kept[SCOPE] = 1
    elif not scoped and SCOPE in defaults(kind):
        kept[SCOPE] = 0
    base = {**defaults(kind), **probe.base[kind]}
    # The table keeps the fixed part; page_memory adds the buffers' own.
    fixed = reserve - sum(part.cost_in(base) for part in reserve_parts)
    return TypeCosts(costs.cost, costs.parts, fixed, reserve_parts, kept, need)


def _refused_values(probe: SeriesProbe) -> dict:
    """The values the compile refused, as SeriesCosts holds them: {type:
    {attribute: (value, ...)}}."""
    refused = {}
    for kind, attribute, value in probe.refused_values:
        refused.setdefault(kind, {}).setdefault(attribute, set()).add(value)
    return {kind: {attribute: tuple(sorted(values)) for attribute, values in attributes.items()}
            for kind, attributes in refused.items()}


def _refusal_notes(probe: SeriesProbe) -> list:
    """The report's lines on what the compile refused, and how the probe
    measured around it."""
    notes = ["a %s's %s %d needs more temporary memory than its page leaves: its cost is not "
             "measured there" % refused for refused in sorted(probe.need_refused)]
    notes += ["the compile refused a %s's %s %r, nxwright's default; measured at %r"
              % (kind, attribute, default, value)
              for (kind, attribute), (default, value) in sorted(probe.replaced.items())]
    notes += ["the compile refused a %s of local scope: measured at global scope" % kind
              for kind in sorted(probe.global_only)]
    if probe.refused_types:
        notes.append("the compile refused these types: %s"
                     % ", ".join(sorted(probe.refused_types)))
    return notes


def mixed_cases(probe: SeriesProbe, global_memory: int, objects: Part) -> list:
    """Pages of several types each, with event code, as many as fit the
    screen's memory, so that their costs must add up. `global_memory` is
    their project's: its base, and what each type reserves there. A type
    global alone is left out: the most of its cost is the project's, not
    its page's."""
    # Each cost below is from a page of one component, and counts the part
    # for its object as on a page of two objects. Room is kept for the part
    # of a page holding every type, which is more than all of them miss.
    room = probe.memory - global_memory - probe.owns["empty"] - \
        objects.of(len(probe.taken()) + 1)
    cases, page, used, page_need = [], [], 0, 0
    for kind in probe.taken():
        if kind in probe.global_only:
            continue
        cost = probe.owns["type %s" % kind] - probe.owns["empty"]
        # What is left of a page must hold the largest temporary need on it.
        measured = probe.needs.get(need_key(kind))
        need = measured.need if measured else 0
        if cost + need > room:
            continue
        if used + cost + max(page_need, need) > room:
            cases.append(page)
            page, used, page_need = [], 0, 0
        page.append(Component(kind))
        used += cost
        page_need = max(page_need, need)
    cases.append(page)
    return [Case("mixed %d" % number, tuple(components), (), MIXED_CODE)
            for number, components in enumerate(cases) if components]


def _page_costly(probe: SeriesProbe, empty_own: int) -> list:
    """The page's own attributes whose values changed its cost: each alone,
    once all varied together changed it."""
    probe.measure(lambda: [Case("varied page %s" % attribute, (), ((attribute, value),))
                           for attribute, value in varied_page_values(probe).items()]
                  if probe.owns.get("varied page", empty_own) != empty_own else [])
    return [key.split()[2] for key in probe.owns
            if key.startswith("varied page ") and probe.owns[key] != empty_own]


def check_series(probe: SeriesProbe, costs: SeriesCosts) -> list:
    """Checks the costs against every page and project the probe compiled,
    as page_memory computes them from the pages as built. Returns what
    disagrees, as lines to report."""
    disagreements = []
    for compiled in probe.compiled:
        disagreements += _disagreements(costs, compiled)
    for key, measured in probe.needs.items():
        # Each page measuring a need filled the screen's memory, as counted.
        try:
            counted = page_memory(costs, measured.page)
            total = global_memory(costs, measured.pages, BASE_INTS + measured.ints) + counted.own
        except Unmeasured:
            continue
        if total != probe.memory or counted.temporary != measured.need:
            disagreements.append("%s: needed %d filling the memory, counted %d leaving %d" % (
                key, measured.need, counted.temporary, probe.memory - total))
    return disagreements


def _disagreements(costs: SeriesCosts, compiled: CompiledProject) -> list:
    """Returns what disagrees between the costs and a project compiled, as
    lines to report: its global memory, and each page's own memory and
    temporary need, as page_memory computes them from the pages as built.
    What the costs do not measure is passed over (Unmeasured)."""
    found = []
    ints = BASE_INTS + compiled.project.ints
    pages = {page.name: page for page in compiled.pages}
    try:
        counted = global_memory(costs, compiled.pages, ints)
    except Unmeasured:
        counted = None
    if counted is not None and counted != compiled.shown.global_memory:
        found.append("%s: global memory %d, counted %d" % (
            compiled.project.name(), compiled.shown.global_memory, counted))
    for name, own in compiled.shown.pages.items():
        try:
            counted = page_memory(costs, pages[name])
        except Unmeasured:
            continue
        if counted.own != own:
            found.append("%s, %s: %d, counted %d" % (compiled.project.name(), name, own,
                                                     counted.own))
        left = compiled.shown.memory - compiled.shown.global_memory - own
        if counted.temporary > left:
            found.append("%s, %s: compiled leaving %d, counted to need %d" % (
                compiled.project.name(), name, left, counted.temporary))
    return found


def models_memory(runner, letters: list, notes: list) -> dict:
    """Each model's memory, of the series measured, from an empty project."""
    memory = {}
    for model in MODELS:
        if model.series in letters:
            probe = SeriesProbe(runner, model.name)
            compiled = probe.compile(())
            if compiled is None:
                notes.append("an empty project did not compile on %s" % model.name)
                continue
            memory[model.name] = compiled.shown.memory
    return memory


def main(arguments: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder", nargs="?", type=Path,
                        default=NXWRIGHT_FOLDER / "tools" / "editor" / "build" / "memory")
    parser.add_argument("--series", default=",".join(MEASURED_ON),
                        help="the series to measure, as T,P; the others keep the table's")
    options = parser.parse_args(arguments)
    letters = [letter for letter in options.series.split(",") if letter]
    if any(letter not in MEASURED_ON for letter in letters):
        parser.error("--series takes %s" % ", ".join(MEASURED_ON))
    try:
        with EditorRunner(options.folder.resolve()) as runner:
            series, memory, notes = probe_all(runner, letters)
    except ProbeStopped as error:
        print("Stopped: %s" % error, file=sys.stderr)
        return 1
    if TABLE_FILE.exists():
        kept = memory_table()
        series = {**{letter: costs for letter, costs in kept.series.items()
                     if letter not in letters}, **series}
        memory = {**{name: bytes_ for name, bytes_ in kept.memory.items()
                     if model_named(name).series not in letters}, **memory}
    TABLE_FILE.write_text(table_text(EDITOR_VERSION, memory, series), encoding="utf-8",
                          newline="\n")
    for line in notes + ["open restarted the Editor: %s" % line for line in runner.restarts]:
        print(line)
    print("Wrote %s" % TABLE_FILE)
    return 0


def probe_all(runner, letters: list) -> tuple:
    """Measures each series of `letters`. Returns (each series' costs that
    agree with every page it compiled, each model's memory, the notes)."""
    series, notes = {}, []
    for letter in letters:
        probe = SeriesProbe(runner, MEASURED_ON[letter])
        result = measure_series(probe)
        probe.measure(lambda: type_cases(probe, "turned"), encoding="utf-8", rotation=90)
        disagreements = check_series(probe, result.costs)
        if letter == model_named(SECOND_MODEL).series:
            disagreements += _second_model(runner, probe, result.costs)
        notes += ["%s: %s" % (letter, note) for note in result.notes]
        if disagreements:
            notes += ["%s: not written, as the costs disagree: %s" % (letter, line)
                      for line in disagreements]
        else:
            series[letter] = result.costs
    return series, models_memory(runner, letters, notes), notes


def _second_model(runner, probe: SeriesProbe, costs: SeriesCosts) -> list:
    """The types again on the series' second model: each must cost alike."""
    second = SeriesProbe(runner, SECOND_MODEL)
    second.refused_types = set(probe.refused_types)
    second.base = {kind: {**values, **{attribute: probe.base[kind][attribute]
                                       for attribute in PLACE if attribute in values}}
                   for kind, values in second.base.items()}
    for (kind, attribute), (_, value) in probe.replaced.items():
        second.base[kind][attribute] = value
    second.global_only = set(probe.global_only)
    for kind in second.global_only:
        second.base[kind][SCOPE] = 1
    second.compile((), ints=0)
    second.measure(lambda: type_cases(second))
    return check_series(second, costs)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
