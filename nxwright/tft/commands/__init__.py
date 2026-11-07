"""The nxwright commands that work on TFT files, one module each: compile,
decompile, upload, ports, rescue, tft-read, tft-listing, and tft-compare.

Each module has a docstring, whose first line is the command's help, and
main(arguments: list) -> int, which runs the command on the arguments that
follow its name, and returns its exit code. nxwright's command line hands
them their arguments as they are (cli.py), so each parses its own.
"""
import ast
import importlib.util


def command_summary(module: str) -> str:
    """Returns the first line of the docstring of the command module `module`,
    such as "compile". The module's source is read, not imported, so that
    listing the commands imports none of what they need."""
    spec = importlib.util.find_spec("%s.%s" % (__name__, module))
    with open(spec.origin, encoding="utf-8") as source:
        docstring = ast.get_docstring(ast.parse(source.read())) or ""
    return docstring.split("\n", 1)[0]
