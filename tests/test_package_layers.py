"""The package's folders import only those below them:
`project/` at the bottom, `language/` and `source/` on it, `drawing/` on
those, `testing/` on that, and `language_server/` and `debug_adapter/` side
by side on top. The imports that once ran the other way stay gone."""
import ast
from pathlib import Path
import unittest

PACKAGE = Path(__file__).resolve().parent.parent / "nxwright"


def imported(path: Path) -> set:
    """The nxwright modules and packages `path` imports, by dotted name: what
    `from nxwright import language_server` names too, and a relative import
    read from `path`'s own package."""
    package = ["nxwright"] + list(path.relative_to(PACKAGE).parent.parts)
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            base = package[:len(package) - node.level + 1] if node.level else []
            module = ".".join(base + ([node.module] if node.module else []))
            names.add(module)
            names.update("%s.%s" % (module, alias.name) for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return {name for name in names if name.startswith("nxwright")}


class PackageLayersTest(unittest.TestCase):

    def assert_imports_none(self, folder: str, higher: str, files: list = None):
        """Asserts that no module of `folder`, or of `files` in it, imports
        anything of the package `higher`, which sits above it or beside it."""
        paths = [PACKAGE / folder / name for name in files] if files else \
            sorted((PACKAGE / folder).glob("*.py"))
        for path in paths:
            with self.subTest(module=path.name):
                self.assertEqual({name for name in imported(path)
                                  if name.startswith("nxwright." + higher)}, set())

    def test_project_imports_nothing_above_it(self):
        for higher in ("language", "source", "drawing", "testing", "language_server",
                       "debug_adapter"):
            self.assert_imports_none("project", higher)

    def test_source_imports_no_language_server(self):
        self.assert_imports_none("source", "language_server")

    def test_language_imports_no_source(self):
        self.assert_imports_none("language", "source")

    def test_the_drawing_sits_above_source_and_below_testing(self):
        for lower in ("language", "source"):
            self.assert_imports_none(lower, "drawing")
        for higher in ("testing", "language_server", "debug_adapter"):
            self.assert_imports_none("drawing", higher)

    def test_the_code_modules_import_one_way(self):
        # The line helpers sit lowest, then the checks, then the conversion
        # that runs them.
        self.assert_imports_none("language", "language.code_preprocessor",
                                 ["code_lines.py", "code_checks.py"])
        self.assert_imports_none("language", "language.code_checks", ["code_lines.py"])

    def test_the_debugger_imports_no_language_server(self):
        self.assert_imports_none("debug_adapter", "language_server")


if __name__ == "__main__":
    unittest.main()
