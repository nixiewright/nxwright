"""The guard that keeps whole projects out of the unit tests.

A unit test gives a function its own input, made in memory, and at most a
Project of the facts the function reads, which the shared helpers make
(tests/tft/unit_inputs.py). The guard reads the source of every .py file of
tests/tft/, helpers included, and fails when one could get a Project or a build
in another way:

- by importing the compile's project module (nxwright.tft.project), nxwright's build
  (nxwright.source.project_files), or the probe runner's _built, or its
  run_probes or editor_tft, which build for the Nextion Editor's tool, as a
  module, a name, or an alias; or the compile command's module, its main,
  its compile_folder, or its project_of_folder, which build, though its
  compile_project, which takes a Project, may be imported by name; or the
  decompiler's round trip (nxwright.tft.decompiling.round_trip), which builds the
  folder it compiles again;
- by reaching one of them as an attribute, as probe_runner._built(...);
- by importing a module of tests/tft/ that gets whole projects: one exempt, or
  one not converted yet.

It allows the probe runner's data, such as Probe and FIXTURES, and an import
under `if TYPE_CHECKING:`, which gives no Project when the tests run. The
shared helpers may import nxwright.tft.project, to make their Project of facts, but
nothing that builds, and they call neither Project.from_file nor
Project.from_bytes, which read a whole project from a stored file.
"""
import ast
from pathlib import Path
import unittest

_TESTS = Path(__file__).resolve().parent

# The modules that build whole projects by design: the sample of whole
# files, the match check on nxwright's example project, the whole compile,
# the compile command's options, the rescue command, the probe runner's own
# tests, as the runner builds projects for the Nextion Editor, the
# decompiler's round trips of whole files, and the helpers of whole builds
# those use.
EXEMPT = frozenset({"test_whole_files", "test_example_project", "test_compile",
                    "test_compile_options", "test_probe_runner", "test_rescue_command",
                    "test_round_trips", "whole_builds"})
# The shared helpers, which alone may make a Project.
HELPERS = "unit_inputs"
# The modules not converted yet, tests and helpers alike, which still get
# whole projects. Converting one takes it off.
NOT_CONVERTED = frozenset()

_ROUND_TRIP = "nxwright.tft.decompiling.round_trip"
_PROJECT_MODULES = ("nxwright.tft.project", "nxwright.source.project_files", _ROUND_TRIP)
# The compile command's module, which builds, though a name may be imported
# from it.
_COMPILE = "nxwright.tft.commands.compile"
# A module, then a name imported from it that gets a Project or a build.
_RUNNER = "tools.tft.probing.probe_runner"
_PROJECT_NAMES = {("nxwright.tft", "project"), ("nxwright.source", "project_files"),
                  (_RUNNER, "_built"), (_RUNNER, "run_probes"), (_RUNNER, "editor_tft"),
                  ("nxwright.tft.commands", "compile"), (_COMPILE, "main"), (_COMPILE, "compile_folder"),
                  (_COMPILE, "project_of_folder"), ("nxwright.tft.decompiling", "round_trip")}
# The attributes that reach one of them, whatever object they are taken from.
_PROJECT_ATTRIBUTES = ("_built", "run_probes", "editor_tft", "project_files", "compile_folder",
                       "project_of_folder", "round_trip")
# What reads a whole project from a stored file, which the helpers may not call.
_READERS = ("from_file", "from_bytes")


def whole_project_uses(source: str, module: str,
                       getting: frozenset = NOT_CONVERTED | EXEMPT) -> list:
    """Returns each way the source `source` of the module `module` of tests/tft/
    could get a Project or a build, as "line N: what", in line order: none
    for one that gets neither. `getting` gives the modules of tests/tft/ that
    get whole projects, which no other may import."""
    found = []
    helpers = module == HELPERS

    def add(node, what: str):
        found.append((node.lineno, "line %d: %s" % (node.lineno, what)))

    def gets_projects(name: str) -> bool:
        # Whether the dotted module `name` gets a Project or a build here.
        if helpers and name == "nxwright.tft.project":
            return False
        return name in _PROJECT_MODULES or _test_module(name) in getting

    def visit(node):
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            # Only its else branch runs.
            for child in node.orelse:
                visit(child)
            return
        if isinstance(node, ast.Import):
            for alias in node.names:
                if gets_projects(alias.name) or alias.name == _COMPILE:
                    add(node, "imports " + alias.name)
        elif isinstance(node, ast.ImportFrom):
            # A relative import is from tests/tft/, as `from .line_context import`.
            name = (("tests.tft." + node.module if node.module else "tests.tft") if node.level
                    else node.module)
            if gets_projects(name):
                add(node, "imports from " + name)
            for alias in node.names:
                if ((name, alias.name) in _PROJECT_NAMES
                        and not (helpers and (name, alias.name) == ("nxwright.tft", "project"))):
                    add(node, "imports %s from %s" % (alias.name, name))
                elif name == "tests.tft" and alias.name in getting:
                    add(node, "imports tests.tft." + alias.name)
        elif isinstance(node, ast.Attribute):
            if node.attr in _PROJECT_ATTRIBUTES:
                add(node, "reaches " + node.attr)
            elif (node.attr == "project" and isinstance(node.value, ast.Attribute)
                  and node.value.attr == "tft" and gets_projects("nxwright.tft.project")):
                add(node, "reaches nxwright.tft.project")
            elif helpers and node.attr in _READERS:
                add(node, "calls " + node.attr)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(ast.parse(source))
    return [what for _, what in sorted(found)]


def _is_type_checking(test) -> bool:
    """Whether an if's `test` is TYPE_CHECKING, or typing.TYPE_CHECKING."""
    return ((isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
            or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"))


def _test_module(name: str):
    """Returns the module of tests/tft/ that the dotted `name` imports, such
    as test_packaging for tests.tft.test_packaging, or None for one
    elsewhere."""
    parts = name.split(".")
    return parts[2] if len(parts) > 2 and parts[:2] == ["tests", "tft"] else None


class GuardTest(unittest.TestCase):

    def test_no_module_but_those_listed_gets_a_whole_project(self):
        found = {path.stem: whole_project_uses(path.read_text(encoding="utf-8"), path.stem)
                 for path in sorted(_TESTS.glob("*.py"))}
        unlisted = {name: uses for name, uses in found.items()
                    if uses and name not in NOT_CONVERTED | EXEMPT}
        self.assertEqual(unlisted, {})
        # A module that gets none now is converted, and comes off the list.
        idle = sorted(name for name in NOT_CONVERTED if not found.get(name))
        self.assertEqual(idle, [], "these get no whole project now, so take them off the list")


class FormsTest(unittest.TestCase):
    """The guard, on stand-in sources of each form the files of tests/tft/ use,
    or could use, to get a Project or a build."""

    def uses(self, source: str, module: str = "test_converted") -> list:
        return whole_project_uses(source, module)

    def test_a_project_imported(self):
        for source in ("from nxwright.tft.project import Project\n",
                       "from nxwright.tft.project import Project as Loaded\n",
                       "import nxwright.tft.project\n", "import nxwright.tft.project as loaded\n",
                       "from nxwright.tft import project\n", "from nxwright.tft import frame, project\n"):
            with self.subTest(source):
                self.assertTrue(self.uses(source))

    def test_a_build_imported(self):
        for source in ("from nxwright.source.project_files import build\n",
                       "from nxwright.source.project_files import build as made\n",
                       "from nxwright.source import project_files\n",
                       "import nxwright.source.project_files\n"):
            with self.subTest(source):
                self.assertTrue(self.uses(source))

    def test_the_runner_s_built(self):
        # As a name, beside the runner's data, or an alias; or reached
        # through the runner's module.
        for source in ("from tools.tft.probing.probe_runner import FIXTURES, Probe, _built\n",
                       "from tools.tft.probing.probe_runner import _built as built\n",
                       "from tools.tft.probing import probe_runner\n"
                       "def f(probe, work):\n    return probe_runner._built(probe, work)\n"):
            with self.subTest(source):
                self.assertTrue(self.uses(source))

    def test_what_the_runner_builds_for_the_editor(self):
        for source in ("from tools.tft.probing.probe_runner import Probe, editor_tft\n",
                       "from tools.tft.probing.probe_runner import run_probes\n",
                       "from tools.tft.probing import probe_runner\n"
                       "probe_runner.run_probes(probes, tool)\n"):
            with self.subTest(source):
                self.assertTrue(self.uses(source))

    def test_the_compile_command_s_build(self):
        # Its main, compile_folder, and project_of_folder build; its
        # compile_project takes a Project.
        for source in ("from nxwright.tft.commands.compile import compile_folder\n",
                       "from nxwright.tft.commands.compile import project_of_folder\n",
                       "from nxwright.tft.commands import compile\ncompile.project_of_folder(folder)\n",
                       "from nxwright.tft.commands.compile import main\n",
                       "from nxwright.tft.commands import compile\ncompile.main(arguments)\n",
                       "import nxwright.tft.commands.compile\n"):
            with self.subTest(source):
                self.assertTrue(self.uses(source))
        self.assertEqual(self.uses("from nxwright.tft.commands.compile import compile_project\n"), [])

    def test_the_round_trip(self):
        # The decompiler's round trip builds the folder it compiles again.
        for source in ("from nxwright.tft.decompiling.round_trip import compiled_again\n",
                       "from nxwright.tft.decompiling import round_trip\n",
                       "import nxwright.tft.decompiling.round_trip\n"):
            with self.subTest(source):
                self.assertTrue(self.uses(source))

    def test_a_project_reached_as_an_attribute(self):
        self.assertEqual(self.uses("import nxwright.tft\nproject = nxwright.tft.project.Project\n"),
                         ["line 2: reaches nxwright.tft.project"])

    def test_a_module_that_gets_whole_projects(self):
        # Imported at the top or within a function, as the sample imports
        # whole_builds' built_project; and an exempt module too.
        for source in ("from tests.tft.whole_builds import built_project\n",
                       "def f():\n    from tests.tft.whole_builds import built_project\n",
                       "from tests.tft.test_whole_files import WholeFileTest\n",
                       "import tests.tft.test_whole_files\n", "from tests.tft import test_compile\n",
                       "from .whole_builds import built_project\n",
                       "from . import test_compile\n"):
            with self.subTest(source):
                self.assertTrue(self.uses(source))
        # A module of tests/tft/ that gets none may be imported.
        self.assertEqual(self.uses("from tests.tft.unit_inputs import page, project_of\n"), [])

    def test_what_it_allows(self):
        for source in ("from tools.tft.probing.probe_runner import FIXTURES, Probe\n",
                       "from tools.tft.probing import probe_runner\nfolder = probe_runner.FIXTURES\n",
                       "from typing import TYPE_CHECKING\n"
                       "if TYPE_CHECKING:\n    from nxwright.tft.project import Project\n",
                       "import typing\n"
                       "if typing.TYPE_CHECKING:\n    from nxwright.tft.project import Project\n",
                       "from nxwright.tft import frame\nimport nxwright.tft\n"):
            with self.subTest(source):
                self.assertEqual(self.uses(source), [])
        # The else branch of `if TYPE_CHECKING:` runs.
        self.assertTrue(self.uses("if TYPE_CHECKING:\n    pass\n"
                                  "else:\n    from nxwright.tft.project import Project\n"))

    def test_the_shared_helpers(self):
        # They may import nxwright.tft.project, but read no stored project and
        # import no build.
        for source in ("from nxwright.tft.project import Project\n", "import nxwright.tft.project\n",
                       "from nxwright.tft import project\n"):
            with self.subTest(source):
                self.assertEqual(self.uses(source, HELPERS), [])
        for source in ("from nxwright.tft.project import Project\nProject.from_file(path)\n",
                       "from nxwright.tft.project import Project\nProject.from_bytes(data, 'x')\n",
                       "from nxwright.source.project_files import build\n",
                       "from tools.tft.probing.probe_runner import _built\n"):
            with self.subTest(source):
                self.assertTrue(self.uses(source, HELPERS))

    def test_each_use_is_given_by_its_line(self):
        self.assertEqual(self.uses("import unittest\n"
                                   "from tools.tft.probing.probe_runner import FIXTURES, _built\n"
                                   "from nxwright.tft.project import Project\n"),
                         ["line 2: imports _built from tools.tft.probing.probe_runner",
                          "line 3: imports from nxwright.tft.project"])


if __name__ == "__main__":
    unittest.main()
