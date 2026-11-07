"""check probes against the Nextion Editor's TFT files, and keep their fixtures

  python -m tools.tft.probe run <module> [--again [<probe> ...] | --only <probe> ...]
  python -m tools.tft.probe run --fixtures
  python -m tools.tft.probe run --all
  python -m tools.tft.probe keep <module> --version <x.y.z>
  python -m tools.tft.probe cut <module> ...
  python -m tools.tft.probe research <series> <lines-file>
  python -m tools.tft.probe drop <probe>
  python -m tools.tft.probe bases [<series> ...]

run checks the probes the module tools.tft.probing.<module> lists in its PROBES,
such as `first_probes`, in the agent's own Nextion Editor
(tools/tft/probing/probe_runner.py). It needs NXWRIGHT_EDITOR_NAME, and the
Editor tool's Python, from nxwright's folder:

  tools\\editor\\build\\venv\\Scripts\\python.exe -m tools.tft.probe run first_probes

It holds the Editor for its run, so a hold of your own on it must be
released first (editor.py release). It skips the probes already matched,
but for those --again lists, or all of them when --again lists none. With
--only, it checks the probes listed alone, even if already matched.

With --fixtures, run checks every probe that keeps fixtures, of every
module, and with --all every probe that compares with nxwright's compile,
each even if already matched. Each ends with the probes that did not
match, and those that could not run, by module. The modules of the older
Nextion Editors are left out, as their probes compare nothing: keep keeps
their files instead.

A probe that cannot run is listed apart, with why, and the run goes on. A
probe cannot run when the Nextion Editor refuses its project, or when the
Editor's folder lacks a firmware file the probe needs. run exits with 1
when a probe does not match or could not run, and with 2 when the run
cannot go on.

The probes package nxwright's file with the firmware of the Nextion Editor
they drive (probing/packaging_probes.py, probe_firmware). To check another
release, such as a new one unpacked from its zip, NXWRIGHT_EDITOR names its
program, and NXWRIGHT_EDITOR_NAME a dedicated Editor of its own. tools/tft/README.md
gives the steps for a new release.

research has the Nextion Editor compile the lines of a file, one a line, in
page0's Touch Release event on the base folder of a series, beside the
text t0, the numbers n0 and n1, the timer tm0, and the waveform s0
(tools/tft/probing/research.py). It prints each block the Nextion Editor
writes for them, with its place, and records and keeps nothing. It needs
what run needs, and exits with 2 when nxwright's build or the Nextion
Editor refuses the lines, printing why.

cut writes each probe's pieces.json, where each piece of its fixtures lies,
such as one object's memory, and where each of its components lies, for
the probes the modules list that keep
fixtures, without the Nextion Editor (probe_runner.cut_probes), as when a
kind of piece is added. It first checks that nxwright's output for each is
still its fixtures, and that its pieces put back together give each of its
fixtures, and writes nothing for a probe whose checks fail. It exits with 1
when one fails.

keep has an older Nextion Editor write the TFT file of each probe the module
lists, and keeps the file's pieces as the probe's fixtures, comparing them
with nothing, as nxwright writes no file of that version
(probe_runner.kept_from_the_editor). NXWRIGHT_EDITOR names that Editor's
program, and NXWRIGHT_EDITOR_NAME a dedicated Editor of its own, apart from
the agent's 1.68.2 one. A file of another version than --version gives is
refused, and so is a probe that keeps no fixtures. It exits with 2 when it
cannot go on.

drop deletes the Nextion Editor's file kept for a probe that did not match.

bases writes the base folders in probes/, by series letter, all of them by
default. A folder already there is refused: they are made again only when
nxwright changes what `nxwright new` writes.
"""
import argparse
import importlib
from pathlib import Path
import pkgutil
import sys

from tools.tft import probing
from tools.tft.probing.probe_runner import (BASE_MODELS, EditorTool, ProbeError, ProbeMismatch,
                                        cut_probes, drop, kept_from_the_editor,
                                        make_base_folders, run_probes)
from tools.tft.probing.research import event_blocks
from nxwright import NxwrightError


def main(arguments: list) -> int:
    """Runs `tools.tft.probe` on `arguments`, and returns its exit code."""
    parser = argparse.ArgumentParser(prog="python -m tools.tft.probe",
                                     description=__doc__.split("\n", 1)[0])
    actions = parser.add_subparsers(dest="action", required=True)
    running = actions.add_parser("run", help="check the probes a module lists, or those of "
                                 "every module")
    running.add_argument("module", nargs="?", help="the module of tools.tft.probing whose PROBES "
                         "to check, such as first_probes")
    choosing = running.add_mutually_exclusive_group()
    choosing.add_argument("--fixtures", action="store_true",
                          help="check every probe that keeps fixtures, of every module")
    choosing.add_argument("--all", action="store_true",
                          help="check every probe that compares with nxwright's compile, of every "
                          "module")
    choosing.add_argument("--again", nargs="*", metavar="PROBE",
                          help="check these probes, or all of them when none is given, "
                          "even if already matched")
    choosing.add_argument("--only", nargs="+", metavar="PROBE",
                          help="check these probes alone, even if already matched")
    keeping = actions.add_parser("keep", help="keep an older Nextion Editor's files of the "
                                 "probes a module lists as their fixtures")
    keeping.add_argument("module", help="the module of tools.tft.probing whose PROBES to keep")
    keeping.add_argument("--version", required=True, type=_version,
                         help="the older Nextion Editor's version, such as 1.63.3")
    cutting = actions.add_parser("cut", help="write where each piece of the probes' "
                                 "fixtures lies")
    cutting.add_argument("modules", nargs="+", metavar="module",
                         help="the modules of tools.tft.probing whose PROBES to cut")
    studying = actions.add_parser("research", help="print the blocks the Nextion Editor "
                                  "writes for lines of code in an event")
    studying.add_argument("series", choices=sorted(BASE_MODELS),
                          help="the series' letter, whose base folder the lines go on")
    studying.add_argument("lines", type=Path, help="a file of the lines, one a line")
    dropping = actions.add_parser("drop", help="delete the file kept for a probe that "
                                  "did not match")
    dropping.add_argument("probe")
    making = actions.add_parser("bases", help="write the base folders in probes/")
    making.add_argument("series", nargs="*", choices=sorted(BASE_MODELS),
                        help="the series' letters (default: all)")
    options = parser.parse_args(arguments)
    if options.action == "run" and (options.module is None) != (options.all or options.fixtures):
        running.error("give a module, or else --fixtures or --all, which take every module")
    try:
        if options.action == "drop":
            print("Deleted the file kept for %s" % options.probe if drop(options.probe)
                  else "No file is kept for %s" % options.probe)
            return 0
        if options.action == "bases":
            for warning in make_base_folders(options.series or None):
                print("probe: warning: %s" % warning, file=sys.stderr)
            print("Wrote the base folders of %s" % ", ".join(options.series or BASE_MODELS))
            return 0
        if options.action == "research":
            _research(options.series, options.lines)
            return 0
        if options.action == "cut":
            return _cut(options.modules)
        if options.action == "keep":
            probes = _probes_of(options.module)
            with EditorTool() as tool:
                kept_from_the_editor(probes, tool, options.version)
            print("%d kept" % len(probes))
            return 0
        if options.all or options.fixtures:
            return _run_every_module(with_fixtures_only=options.fixtures)
        probes = _probes_of(options.module)
        again = set()
        if options.only is not None:
            again = set(options.only)
            unknown = sorted(again - {probe.name for probe in probes})
            if unknown:
                raise ProbeError("%s lists no probe named %s"
                                 % (options.module, ", ".join(unknown)))
            probes = [probe for probe in probes if probe.name in again]
        elif options.again is not None:
            again = set(options.again) or {probe.name for probe in probes}
        with EditorTool() as tool:
            result = run_probes(probes, tool, again)
    # nxwright's own refusals, as of a probe's change or a base folder, are
    # the run's to report too.
    except (ProbeError, ProbeMismatch, NxwrightError) as error:
        print("probe: %s" % error, file=sys.stderr)
        return 2
    print("%s%s" % (_counts([result]), "".join(
        "; %s: %s" % (what, ", ".join(names)) for what, names in (
            ("not matching", result.failed), ("could not run", result.could_not_run)) if names)))
    return 1 if result.failed or result.could_not_run else 0


def _run_every_module(with_fixtures_only: bool) -> int:
    """Checks every probe of compared_modules(), each even if already
    matched, then prints how many matched, and the probes that did not match
    and that could not run, by module. Returns the exit code: 1 when one did
    not match or could not run."""
    modules = compared_modules(with_fixtures_only)
    results = {}
    with EditorTool() as tool:
        for module, probes in modules:
            results[module] = run_probes(probes, tool, {probe.name for probe in probes})
    lines = [_counts(results.values())]
    failed = {module: result.failed for module, result in results.items() if result.failed}
    if failed:
        lines += ["", "Not matching, by module:"]
        lines += ["  %s: %s" % (module, ", ".join(names)) for module, names in failed.items()]
    # A reason may run over several lines, such as the messages closed after
    # the Editor refused a project, which stay under their probe's line.
    unrunnable = [(module, name, why.replace("\n", "\n    ")) for module, result in results.items()
                  for name, why in result.could_not_run.items()]
    if unrunnable:
        lines += ["", "Could not run, by module:"]
        lines += ["  %s: %s, %s" % each for each in unrunnable]
    print("\n".join(lines))
    return 1 if failed or unrunnable else 0


def _counts(results) -> str:
    """Returns how many probes the RunResults `results` matched, skipped,
    did not match, and could not run."""
    results = list(results)
    counts = [sum(len(getattr(result, part)) for result in results)
              for part in ("matched", "skipped", "failed", "could_not_run")]
    return ("%d matched, %d skipped as already matched, %d not matching, %d could not run"
            % tuple(counts))


def compared_modules(with_fixtures_only: bool = False) -> list:
    """Returns (module's name, its probes) for each module of tools.tft.probing
    whose name ends in "_probes" and whose probes compare with nxwright's
    compile, in the order of their names. The older Nextion Editors' modules
    are left out: their probes compare nothing. With `with_fixtures_only`,
    only the probes that keep fixtures are given, and a module without any
    is left out."""
    found = []
    for module in sorted(info.name for info in pkgutil.iter_modules(probing.__path__)
                         if info.name.endswith("_probes")):
        # component_probes and release_probes help other modules make their
        # probes, and list none of their own.
        probes = getattr(importlib.import_module("tools.tft.probing." + module), "PROBES", ())
        taken = [probe for probe in probes if probe.ours is not None
                 and (probe.fixtures is not None or not with_fixtures_only)]
        if taken:
            found.append((module, taken))
    return found


def _version(text: str) -> tuple:
    """Returns the Nextion Editor's version `text`, such as "1.63.3", as
    (1, 63, 3). Raises argparse.ArgumentTypeError for another form."""
    parts = text.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise argparse.ArgumentTypeError("a version is three numbers, such as 1.63.3: %s" % text)
    return tuple(int(part) for part in parts)


def _research(series: str, file: Path):
    """Prints each block the Nextion Editor writes for the lines of `file`,
    with its place (research.event_blocks). Raises ProbeError when the file
    cannot be read or holds no line, before the Editor is started."""
    try:
        # utf-8-sig, as Windows' tools may start a file with a byte-order mark.
        text = file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise ProbeError("the file of lines %s cannot be read: %s" % (file, error)) from None
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ProbeError("the file of lines %s holds no line" % file)
    with EditorTool() as tool:
        for place, block in event_blocks(series, lines, tool):
            print("%5d %s" % (place, block.hex(" ")))


def _cut(modules: list) -> int:
    """Cuts the probes of each module of `modules` (cut_probes), and returns
    the exit code: 1 when a probe's checks failed."""
    probes = [probe for module in modules for probe in _probes_of(module)]
    result = cut_probes(probes)
    print("%d cut, %d not cut%s" % (len(result.cut), len(result.failed),
                                    ": " + ", ".join(result.failed) if result.failed else ""))
    return 1 if result.failed else 0


def _probes_of(module: str) -> list:
    """Returns the PROBES of the module tools.tft.probing.`module`. Raises
    ProbeError when there is no such module, or it has none."""
    name = "tools.tft.probing." + module
    try:
        found = importlib.import_module(name)
    except ModuleNotFoundError as error:
        # Only the module asked for, or a package it would be in: one it
        # imports that is missing is a fault of its own, which its traceback
        # shows.
        if error.name != name and not name.startswith("%s." % error.name):
            raise
        raise ProbeError("there is no module %s" % name) from None
    if not hasattr(found, "PROBES"):
        raise ProbeError("%s lists no PROBES" % name)
    return found.PROBES


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
