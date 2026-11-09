"""Defines: named values that app.toml's [defines] table declares with their
defaults (docs/source-folder.md). nxlang code uses each as a constant of
program.nx. A key of app.toml or of a page file can take a define's value
through a placeholder, which is the define's name between two %, as in
`bco = "%BCOLOR%"`. Every reader of the values fills placeholders in
(filled), and the commands that rewrite the files keep them.

`build` and `compile` take new values from the command line, with
`--define NAME=VALUE`, and a simulation from its launch configuration's
`defines`. A build reads app.toml in many places, so rather than pass the
new values to each one, the command sets them in a context variable for as
long as it runs (overriding_defines), and parse_app applies them each time
it reads app.toml. A context variable belongs to one thread, so a
simulation, which reads the folder on two, sets the values on each.
Outside these, every reader gets the defaults.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import re

from nxwright import NxwrightError

# A define's name: letters, digits, and _, not starting with a digit, the
# same rule as for nxlang's constants.
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# A placeholder: a define's name between two %, as a key's whole value.
_PLACEHOLDER = re.compile(r"%(" + _NAME.pattern + r")%")

# The --define option of `build` and `compile`, as argparse takes it.
DEFINE_OPTION = {"action": "append", "default": [], "metavar": "NAME=VALUE",
                 "help": "give app.toml's define NAME the value VALUE for this build "
                         "(repeat for each define)"}

# Where new values come from, so that their messages can say so: the
# command line's --define, or a simulation's launch configuration.
COMMAND_LINE = "--define"
LAUNCH_CONFIGURATION = "launch configuration"

# The new values that the running command or simulation was given, {name:
# the value as text}, with where they come from.
_OVERRIDES = ContextVar("define_overrides", default=({}, COMMAND_LINE))


def define_arguments(arguments: list) -> dict:
    """Returns {name: value as text} from the `--define` arguments, each
    "NAME=VALUE". Raises NxwrightError for an argument without "=", and for
    a name given twice."""
    overrides = {}
    for argument in arguments:
        name, equals, value = argument.partition("=")
        if not equals:
            raise NxwrightError("--define %s: give a value, as in --define %s=VALUE"
                                % (argument, argument))
        if name in overrides:
            raise NxwrightError("--define %s: given twice" % name)
        overrides[name] = value
    return overrides


def launch_defines(given) -> dict:
    """Returns {name: value as text} from a launch configuration's
    `defines`, an object such as {"LIMIT": 40, "TITLE": "Lab"}. A value is a
    whole number or a text, as in app.toml. Raises NxwrightError for any
    other form."""
    if not isinstance(given, dict):
        raise NxwrightError("the launch configuration's defines must be an object, as in "
                            '"defines": {"LIMIT": 40}')
    overrides = {}
    for name, value in given.items():
        # JSON's true is Python's True, which is an int: only real numbers count.
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise NxwrightError("the launch configuration's defines: %s must be a whole number "
                                "or a text" % name)
        overrides[name] = str(value)
    return overrides


def is_define_name(name: str) -> bool:
    """Whether `name` can name a define."""
    return bool(_NAME.fullmatch(name))


@contextmanager
def overriding_defines(overrides: dict, source: str = COMMAND_LINE):
    """Within the `with` block, app.toml's defines take the new values
    `overrides`, {name: value as text}, wherever app.toml is read on this
    thread. `source`, COMMAND_LINE or LAUNCH_CONFIGURATION, is where they
    come from, so that a message about one of them can say so."""
    token = _OVERRIDES.set((dict(overrides), source))
    try:
        yield
    finally:
        _OVERRIDES.reset(token)


def checked_defines(table) -> dict:
    """Returns the defines of app.toml's [defines] table `table` as {name:
    int or str}, with the new values of the running command applied.
    `table` is None when app.toml has no [defines] table. Raises
    NxwrightError for a name or a value the table cannot have, for a new
    value whose name the table does not declare, and for a new value of the
    wrong type."""
    if table is None:
        table = {}
    if not isinstance(table, dict):
        raise NxwrightError("app.toml: defines must be a table, as in [defines]")
    defines = {}
    for name, value in table.items():
        if not is_define_name(name):
            raise NxwrightError("app.toml: invalid define name: %s. Use letters, digits, and "
                                "_, and do not start with a digit" % name)
        # TOML's true is Python's True, which is an int: only real numbers count.
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise NxwrightError("app.toml: the define %s must be a whole number or a text"
                                % name)
        defines[name] = value
    overrides, source = _OVERRIDES.get()
    for name, text in overrides.items():
        if name not in defines:
            declared = ", ".join(sorted(defines)) or "none"
            raise NxwrightError("%s: app.toml's [defines] does not declare %s (it declares %s)"
                                % (_given(source, name), name, declared))
        defines[name] = _typed(name, text, defines[name], source)
    return defines


def placeholder_name(value):
    """Returns the define's name when `value` is a placeholder, a text of
    the form "%NAME%", and None otherwise."""
    found = _PLACEHOLDER.fullmatch(value) if isinstance(value, str) else None
    return found[1] if found else None


def filled(table: dict, defines: dict, fixed_keys: tuple, where: str) -> dict:
    """Returns the TOML table `table`, from app.toml or a page file, with
    each value that is a placeholder replaced by its define's value, from
    `defines`. `where`, such as "app.toml", starts each message. Without
    defines, a placeholder stays plain text, so that folders written before
    defines keep their meaning.
    Raises NxwrightError for a placeholder in one of `fixed_keys`, the keys
    that identify a file or a table, and for one whose name `defines`
    does not have."""
    if not defines:
        return table
    result = {}
    for key, value in table.items():
        name = placeholder_name(value)
        if name is not None:
            if key in fixed_keys:
                raise NxwrightError("%s: %s is %s, but %s cannot take a define's value"
                                    % (where, key, value, key))
            if name not in defines:
                raise NxwrightError("%s: %s is %s, and app.toml's [defines] does not declare %s"
                                    % (where, key, value, name))
            value = defines[name]
        result[key] = value
    return result


def _typed(name: str, text: str, default, source: str):
    """Returns the value `text` given for the define `name`, of the type of
    its `default`: a whole number for a number, and the text as it is for
    a text. `source` is where the value comes from (overriding_defines)."""
    if isinstance(default, str):
        return text
    # int() raises ValueError for a text of thousands of digits, so a value is
    # limited to 100 digits.
    if not re.fullmatch(r"-?[0-9]{1,100}", text):
        raise NxwrightError("%s: %s is a number, so its value must be a whole number, such as "
                            "30 or -5" % (_given(source, name, text), name))
    return int(text)


def _given(source: str, name: str, text: str = None) -> str:
    """Returns the start of a message about the define `name`, and its new
    value `text` if given, in the words of its `source`: "--define
    LIMIT=abc", or "the launch configuration's defines give LIMIT the value
    abc". Without `text`, the launch configuration's start leaves out the
    name, which the message then gives."""
    if source == COMMAND_LINE:
        return "--define %s" % (name if text is None else "%s=%s" % (name, text))
    if text is None:
        return "the launch configuration's defines"
    return "the launch configuration's defines give %s the value %s" % (name, text)
