"""The checks of a line of code for what the Nextion Editor refuses as it
compiles. preprocess runs check_line on each line (code_preprocessor.py),
and each check raises NxwrightError naming the line.

Given the names of the page's objects and of every page's components, the
checks find each reference to something that does not exist (see
ObjectNames). They refuse an assignment to an attribute code cannot change
(attribute_descriptions.code_cannot_change). Given program.nx's int
variables, they refuse code naming sys0, sys1, or sys2 that program.nx
does not declare (editor_language.EDITOR_PROGRAM_VARIABLES). Given the
folder's macros, they refuse a `call` of a macro the folder lacks
(macros_source.py). Given the folder's screen model, they refuse a command
or a system variable the model's series lacks (series_lacks). With the
names of the objects as well, they refuse an assignment the series refuses
(editor_limits.code_cannot_change_on_series).

Also here are the Nextion Editor's refusal words, such as INVALID_COMMAND,
and the tables of commands' arguments, such as COMMAND_PARAMETERS and
DATA_RECORD_ARGUMENTS, which the test machine reads too.
"""
from dataclasses import dataclass
import re

from nxwright import NxwrightError
from nxwright.language.code_lines import (ARGUMENT, ASSIGNMENT, ELSE, LABEL, OWN_ATTRIBUTE,
                                          OWN_FORM, STRING, chain_parts, command_arguments,
                                          command_word, compact, first_word, goto_label,
                                          holds_own_attribute, is_declaration, minus_is_sign)
from nxwright.project.attribute_descriptions import code_cannot_change, describe, type_has
from nxwright.project.editor_language import (EDITOR_COLOURS, EDITOR_COMMANDS,
                                              EDITOR_PROGRAM_VARIABLES,
                                              EDITOR_SYSTEM_VARIABLES, NO_COMMAND_WHEN_ALONE,
                                              NO_NUMERIC_FORM, REFUSED_AS_A_NAME,
                                              SERIES_LACKED_COMMANDS, SERIES_LACKED_VARIABLES,
                                              UNDECLARED_PROGRAM_VARIABLE)
from nxwright.project.editor_limits import (ATTRIBUTES_CODE_CANNOT_CHANGE_ON_SERIES,
                                            code_cannot_change_on_series)
from nxwright.project.screen_models import ScreenModel

_BLOCK_HEAD = re.compile(r"(if|while|for)\s*\(")
# A line assigning to an object's attribute, in Editor syntax: the object,
# or a page and its object, then the attribute, then the assignment.
_ASSIGNED_ATTRIBUTE = re.compile(r"([A-Za-z_]\w*)\.([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?"
                                 r"(?:\+\+|--|[-+*/%&|^]?=(?!=))")
# A tab after `int`, which the Editor reads as part of the name, refusing
# the declaration. (Worked out from the Editor 3.1.73.)
_TAB_AFTER_INT = re.compile(r"int\t")
# sys0, sys1, or sys2 named outside a string: not part of a longer name, and
# neither an attribute nor a component of that name, as in `sys0.txt`.
_PROGRAM_VARIABLE = re.compile(r"(?<![\w.])(%s)(?![\w.])" % "|".join(EDITOR_PROGRAM_VARIABLES))
# A name in code, not part of a longer name, nor an attribute after a dot.
_BARE_NAME = re.compile(r"(?<![\w.])[A-Za-z_]\w*")
# A name alone: as _BARE_NAME, and neither a component or a page before a
# dot, nor the array b before "[".
_NAME_ALONE = re.compile(r"(?<![\w.\]])([A-Za-z_]\w*)(?![\w.\[])")
_KEYWORDS = frozenset({"if", "else", "while", "for"})
# The kinds of word series_lacks finds, as the Editor's refusals name them:
# "Do not support such instruction for this series device".
LACKED_INSTRUCTION, LACKED_VARIABLE = "instruction", "variable"
# The Editor's words for a first word that is no command of its own
# (first_word_refusal).
INVALID_COMMAND, INVALID_VARIABLES = "Invalid command", "Invalid Variables"
INVALID_ARGUMENT_COUNT = "Invalid number of arguments"
# "name.attribute" or "page.name.attribute", not part of a longer chain such
# as "b[3].txt", whose component is chosen at run time.
_DOTTED = re.compile(r"(?<![\w.\]])([A-Za-z_]\w*)\.([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?")
# Commands whose first argument names a component of the page. A component's
# ID is accepted there too, and is not checked.
_NAMING_COMMANDS = "vis|tsw|ref|click"
_NAMING_COMMAND = re.compile(r"(%s) ([A-Za-z_]\w*)(?=,|$)" % _NAMING_COMMANDS)
# Such a command's first argument given by a name, a dotted one too: a
# component's, which a macro may not give, or a variable's or value's,
# holding the component's ID.
_NAME_IN_COMMAND = re.compile(r"(%s) ([A-Za-z_][\w.]*)(?=,|$)" % _NAMING_COMMANDS)
# A hexadecimal constant, its digits after "0x", or "0X", which the Editor
# treats alike. The Editor wants them in pairs, a byte each, and refuses hex
# as an int's starting value (the vendor's instruction set, rule 1.8).
# Compiled in the Editor, it also refused a constant past 32 bits, and a
# sign on one after =, ==, and *.
_HEX = re.compile(r"(?<![\w.])0[xX]([0-9A-Fa-f]*)(?![\w.])")
# A line the Editor reads as a label, whatever its characters.
_LABEL_LIKE = re.compile(r"(\S+):")
# What goes in each place of a data record's methods' arguments: a text or
# a number. As it compiled, the Editor refused a call with too few or too
# many, a text where a number goes, and texts joined; it compiled a number
# where a text goes, and the screen then did nothing.
DATA_RECORD_ARGUMENTS = {"insert": (str,), "delete": (int, int), "up": (str, int),
                         "clear": ()}
# A call of one of those methods: its component's name, the method, and its arguments.
DATA_RECORD_CALL = re.compile(r"([A-Za-z_]\w*)\.(insert|delete|up|clear)\((.*)\)$")
# How many arguments each of a file stream's methods takes. The Nextion
# Editor 3.1.73's compile refused any other number, "Invalid number of
# arguments".
FILE_STREAM_ARGUMENTS = {"open": 1, "read": 3, "write": 3, "close": 0, "find": 1}
# A call of one of those methods: its component's name, the method, and its arguments.
_FILE_STREAM_CALL = re.compile(r"([A-Za-z_]\w*)\.(open|read|write|close|find)\((.*)\)$")
# Where a drawing command's arguments give a picture's ID, and xstr its
# font's, counted from 0 (the vendor's instruction set).
PICTURE_ARGUMENTS = {"pic": 2, "picq": 4, "xpic": 6}
XSTR_FONT_ARGUMENT = 4
# How many parameters each command takes, for those whose number is fixed
# (the vendor's instruction set). The Editor's compile refused another
# number, as `cls 1,2` and `fill 0,0,10`, saying "Invalid number of
# arguments", and its simulator answered such a typed line 0x1E. A command
# it does not list takes any number.
COMMAND_PARAMETERS = {
    "vis": 2, "tsw": 2, "ref": 1, "click": 2, "move": 7,
    "cls": 1, "pic": 3, "picq": 5, "xpic": 7, "xstr": 11, "fill": 5, "line": 5, "draw": 5,
    "cir": 4, "cirs": 4,
    "get": 1, "print": 1, "prints": 2, "sendme": 0,
    "wepo": 2, "repo": 2, "rept": 2, "cfgpio": 3, "randset": 2, "add": 3, "cle": 2,
    "addt": 3, "wept": 2, "ucopy": 4, "udelete": 1,
    # The Editor refused two on the series that take it, and compiled one.
    "beep": 1,
    # Undocumented, as each compiled with one number of arguments, and no
    # other from 0 to 12, on every series that takes it; draw_h and setbrush
    # to 16. lcd_dev's hex values are spaced, as printh's bytes.
    "lcd_dev": 1, "getpassw": 0, "lcd_refx": 0, "lhmi_cle": 0, "showqq": 0, "getv": 1,
    "init": 1, "setbaudz": 1, "pa_q": 2, "whmi_cle": 2, "fstr": 3, "nstr": 3, "rfpt": 3,
    "strsize": 3, "wfpt": 3, "pa_txt": 4, "timerset": 4, "zstr": 5, "comok": 7, "draw3d": 7,
    "qrcode": 8, "draw_h": 13, "setbrush": 15,
    "covx": 4, "cov": 3, "substr": 4, "spstr": 4, "strlen": 2, "btlen": 2,
    "newdir": 1, "deldir": 1, "delfile": 1, "refile": 2, "redir": 2, "newfile": 2,
    "findfile": 2, "finddir": 2, "rdfile": 4, "twfile": 2,
    # The Editor compiled each with two, and refused none, one, and three.
    "crcrest": 2, "crcputs": 2, "crcputu": 2,
    # The Editor compiled each alone, and refused each given one argument.
    "rest": 0, "touch_j": 0, "code_c": 0,
}
# One operand alone: a string, a number, or a name, which may be dotted.
_ONE_OPERAND = re.compile(r'"(?:\\.|[^"\\])*"|-?\w+(?:\[[^\]]*\])?(?:\.\w+(?:\[[^\]]*\])?)*')
# The commands whose first argument is one operand alone. The Editor
# refused arithmetic there as it compiled ("Invalid Variables"), as in
# `get n0.val+1`, and texts joined, as in `print "a"+t0.txt`. It took
# arithmetic in covx's length and form, and in newfile's size.
ONE_OPERAND_FIRST = ("get", "print", "prints", "covx")
# The escapes the screen reads inside a quoted text, each with what the
# screen stores for it: `\r` a carriage return and a line feed, as the
# Editor's simulator showed. The Editor's compile refused any other, `\n`,
# `\t`, `\q`, and `\a` among them, in an assignment, a `print`, a
# condition, and a file's path ("Improper use of escape characters"). The
# test machine reads them here too.
SCREEN_ESCAPES = {"r": "\r\n", '"': '"', "\\": "\\"}
# A name in code: an object's or a variable's, with its page and attribute.
_NAME = r"[A-Za-z_]\w*(?:\[[^\]]*\])?(?:\.[A-Za-z_]\w*(?:\[[^\]]*\])?)*"
# An assignment, simple or compound: its target, its operator, and its value.
_ASSIGNMENT_LINE = re.compile(r"(%s)(<<=|>>=|[-+*/%%&|^]?=)(?!=)(.+)" % _NAME)
# An operand of a value, and the operator joining one to the next.
_VALUE_OPERAND = re.compile(r'"(?:\\.|[^"\\])*"|-?0[xX][0-9A-Fa-f]+|-?\d+|%s' % _NAME)
_VALUE_OPERATOR = re.compile(r"<<|>>|[-+*/%&|^]")
_NUMBER_WRITTEN = re.compile(r"-?(?:0[xX][0-9A-Fa-f]+|\d+)")
# The two kinds of value the Editor's code has. Of the attributes, those
# its compile was seen to tell: a `txt` takes a text, and a `val`, a `pco`,
# or a `font` a number. Every other attribute is of no known kind here.
_TEXT, _NUMBER = "text", "number"
_ATTRIBUTE_KINDS = {"txt": _TEXT, "val": _NUMBER, "pco": _NUMBER, "font": _NUMBER}


@dataclass(frozen=True)
class ObjectNames:
    """The names a page's code may refer to. `own` holds the page's objects:
    the page itself and its components, generated variables included.
    `pages` holds each page's objects, by page name, each with its type as
    page files name it ("data-record"): {name: type}. A page's objects are
    None when they are unknown, as while its file is half typed. References
    to that page are then not checked. `page` is this page's name. A data
    record's calls, and assignments to attributes code cannot change, are
    checked by the types.

    A macro's code belongs to no page: its `page` is None, and `own` is
    empty. `reachable` then holds each page's components of global scope, by
    page name, which alone a macro reaches, with its page's name, because
    the Editor compiles macros apart from every page (macros_source.py).

    `absent_attributes` holds the attributes each page's components lack by
    their page file's values (editor_limits.lacked_attributes), {page name:
    {name: {attribute: why}}}: a variable holding a text has no `val`. A
    component it does not name is not checked."""
    own: frozenset
    pages: dict
    page: str
    reachable: dict = None
    absent_attributes: dict = None


def check_line(code: str, objects: ObjectNames, variables: frozenset, macros: frozenset,
                screen: ScreenModel, number: int, program_pages: dict = None):
    """Raises NxwrightError for a line's code part, its resources' names
    resolved, that the Editor refuses as it compiles, as
    code_preprocessor.preprocess says. `program_pages`, for a line of
    program.nx, holds each page's objects, by page name."""
    if _TAB_AFTER_INT.match(code):
        raise NxwrightError("a tab after int: the Nextion Editor takes int and a space only, and "
                            "refuses this declaration (\"Invalid Variables\")", line=number,
                            fix={"kind": "tab-after-int", "text": "int\t", "new": "int "})
    _check_hex(code, number)
    if is_declaration(code):
        return
    if code.endswith("{") and code != "{":
        code = code[:-1].rstrip()
        if not (_BLOCK_HEAD.match(code) or ELSE.match(code)):
            raise NxwrightError("\"{\" can only end an if, while, for, or else line",
                                line=number)
    code = compact(code)
    _check_value_and_head(code, number)
    if objects is not None:
        if objects.page is None:
            _check_macro_references(code, objects, number)
        else:
            _check_references(code, objects, number)
        _check_data_record_call(code, objects, number)
        _check_file_stream_call(code, objects, number)
        _check_assigned_attribute(code, objects, number)
    if program_pages is not None:
        _check_program_names(code, program_pages, number)
    # Before the number of arguments, as the Editor named the series
    # first for `beep 100,2` on a screen whose series lacks beep.
    if screen is not None:
        _check_series(code, screen, number)
        if objects is not None:
            _check_series_assignment(code, objects, screen, number)
    # A word that is no command has no number of arguments to count.
    _check_first_word(code, number)
    _check_parameter_count(code, number)
    _check_first_argument(code, number)
    _check_xstr_text(code, number)
    if variables is not None:
        _check_program_variables(code, variables, number)
        _check_names_alone(code, objects, variables, number)
    if macros is not None:
        _check_call(code, macros, number)
    _check_escapes(code, number)
    _check_condition_texts(code, number)
    # A name a component's type lacks, or one its values leave out, first,
    # as the Editor names it.
    if objects is not None:
        _check_type_names(code, objects, number)
        _check_absent_attributes(code, objects, number)
    _check_assignment_kinds(code, variables, number)


def _check_value_and_head(code: str, number: int):
    """Raises NxwrightError for an assignment whose value does not read as
    operands joined by operators (code_lines.chain_parts), for an if, an
    else if, a while, or a for whose head does not end with ")", and for a
    for whose head holds a text with a semicolon. The test runner reads a
    value the same way. A label, and a value still holding the form
    '&name&', are left to their own checks: check_labels, and
    check_without_owner where no event's object replaced the form."""
    if _LABEL_LIKE.fullmatch(code):
        return
    head, otherwise = _BLOCK_HEAD.match(code), ELSE.match(code)
    if head or (otherwise and otherwise[2]):
        if not code.endswith(")"):
            words = "SYNTAX ERROR:for" if head and head[1] == "for" \
                else 'SYNTAX ERROR:must end with ")"'
            raise NxwrightError("%s: the Nextion Editor wants the head to end with \")\" (\"%s\")"
                                % (code, words), line=number)
        # The Editor refused a text holding a semicolon in any part of a
        # for's head, and compiled one in a while's or an if's condition.
        if head and head[1] == "for" and any(";" in text for text in STRING.findall(code)):
            raise NxwrightError("%s: the Nextion Editor refuses a text that contains a semicolon "
                                "in a for's head (\"SYNTAX ERROR:for\")" % code, line=number)
        return
    assignment = ASSIGNMENT.match(code)
    if assignment is None or holds_own_attribute(assignment[3]):
        return
    if not assignment[3]:
        raise NxwrightError("%s: the Nextion Editor refuses an assignment without a value "
                            "(\"%s\")" % (code, INVALID_COMMAND), line=number)
    if chain_parts(assignment[3]) is None:
        raise NxwrightError("%s: the Nextion Editor refuses this value, which is not operands "
                            "joined by operators (\"%s\")" % (code, INVALID_VARIABLES),
                            line=number)


def check_own_forms(code: str, number: int):
    """Raises NxwrightError for a form '&...&' outside the line's quoted
    texts whose name, its spaces dropped, is no attribute's (code_lines.OWN_FORM)."""
    for part in STRING.split(code)[::2]:
        for form in OWN_FORM.finditer(part):
            if not OWN_ATTRIBUTE.fullmatch("'&%s&'" % re.sub(r"\s", "", form[1])):
                raise NxwrightError("%s: the Nextion Editor reads no attribute in %s "
                                    "(\"Invalid Variables\")" % (code, form[0]), line=number)


def check_without_owner(code: str, number: int):
    """Raises NxwrightError for code belonging to no event that uses the
    form '&name&' outside a quoted text, which the Editor refused in
    program.s and in a macro ("Invalid Variables"). In a quoted text it
    stays as written, as the Editor's simulator sent it from both."""
    if holds_own_attribute(code):
        raise NxwrightError("%s: the form '&name&' stands for an attribute of the object whose "
                            "event holds the line, and this line has no such object (\"%s\")"
                            % (code, INVALID_VARIABLES), line=number)


def _check_references(code: str, objects: ObjectNames, number: int):
    """Raises NxwrightError when a line names a component or page that does
    not exist. Another page's components are named with the page first."""
    command = _NAMING_COMMAND.match(code)
    if command and command[2] not in objects.own:
        raise NxwrightError("%s names %s, which is not on this page"
                            % (command[1], command[2]), line=number)
    for part in STRING.split(code)[::2]:
        for first, second, third in _DOTTED.findall(part):
            if first in objects.pages and third:
                known = objects.pages[first]
                if known is not None and second not in known:
                    raise NxwrightError("page %s has no component %s"
                                        % (first, second), line=number)
            elif first not in objects.own and first not in objects.pages:
                raise NxwrightError("%s is neither on this page nor a page"
                                    % first, line=number)


def _check_macro_references(code: str, objects: ObjectNames, number: int):
    """Raises NxwrightError when a macro's line names a component other than
    as the Editor compiled it in a macro: with its page's name, and of global
    scope (ObjectNames.reachable). The Editor refused `t1.txt`, `t0.txt`, and
    `page0.t0.txt`, t0 of local scope, saying "Invalid Variables".

    A command naming a component, as `vis`, `tsw`, `ref`, and `click` do,
    takes its ID in a macro, not its name. The Editor refused `vis t0,0` and
    `click page0.b0,1`, b0 of global scope, saying "Invalid Component ID",
    and compiled `vis 1,0`, `vis sys0,0`, and `vis page0.n0.val,0`. A page's
    own attribute, `page0.x`, is left to the Editor, as no probe tried it."""
    command = _NAME_IN_COMMAND.match(code)
    if command and _is_component_name(command[2], objects):
        raise NxwrightError("%s %s: in a macro, a command takes a component's number, or a "
                            "variable that contains it. The Nextion Editor refuses its name "
                            "there" % (command[1], command[2]), line=number)
    for part in STRING.split(code)[::2]:
        for first, second, third in _DOTTED.findall(part):
            if first not in objects.pages:
                raise NxwrightError("%s: a macro names a component with its page's name, as "
                                    "page.%s, and of global scope" % (first, first), line=number)
            known, reachable = objects.pages[first], objects.reachable.get(first)
            if not third or known is None:
                continue
            if second not in known:
                raise NxwrightError("page %s has no component %s" % (first, second), line=number)
            if reachable is not None and second not in reachable:
                raise NxwrightError("%s.%s: a macro cannot reach a component of local scope"
                                    % (first, second), line=number)


def _check_program_names(code: str, pages: dict, number: int):
    """Raises NxwrightError when a line of program.nx gives a command that
    names a component, as vis, tsw, ref, and click do, the name of a page,
    or of a component, alone or with its page's name. `pages` holds each
    page's objects, by page name, as ObjectNames.pages does. program.s
    belongs to no page: the Editor refused `vis page0,0`, `ref page1`,
    `vis t0,0`, `tsw t0,1`, `click t0,1`, and `vis page0.t0,0` there,
    saying "Invalid Component ID", and compiled `vis 1,0` and
    `vis sys0,0`."""
    command = _NAME_IN_COMMAND.match(code)
    if command is None:
        return
    page, dot, component = command[2].partition(".")
    if dot:
        known = pages.get(page)
        named = "." not in component and known is not None and component in known
    else:
        named = page in pages or any(known is not None and page in known
                                     for known in pages.values())
    if named:
        raise NxwrightError("%s: program.nx belongs to no page, so %s takes a component's "
                            "number, or a variable that contains it. The Nextion Editor "
                            "refuses a page's or a component's name there (\"Invalid "
                            "Component ID\")" % (code, command[1]), line=number)


def _is_component_name(name: str, objects: ObjectNames) -> bool:
    """Whether `name` names a component, as `page.component` or bare, the
    name of a component some page has. A page whose names are unknown names
    none."""
    if "." in name:
        page, _, component = name.partition(".")
        known = objects.pages.get(page)
        return known is not None and component in known and component != page
    return any(known is not None and name in known and name != page
               for page, known in objects.pages.items())


def _check_call(code: str, macros: frozenset, number: int):
    """Raises NxwrightError for a `call` naming a macro the folder lacks,
    which the Editor refused to compile ("the macro is invalid"). Names are
    told apart by case."""
    if command_word(code) == "call":
        name = code[len("call "):]
        if name not in macros:
            raise NxwrightError("%s: the folder has no macro %s" % (code, name), line=number)


def _check_data_record_call(code: str, objects: ObjectNames, number: int):
    """Raises NxwrightError for a call of a data record of the page that the
    Editor refuses as it compiles (DATA_RECORD_ARGUMENTS). A text is a
    string, or a `txt`, which is a text on every type. Other attributes are
    left to the Editor: one stored as text may be a number in code, as a
    scrolling text's `dir`."""
    call = DATA_RECORD_CALL.fullmatch(code)
    if call is None or (objects.pages.get(objects.page) or {}).get(call[1]) != "data-record":
        return
    name = "%s.%s" % (call[1], call[2])
    arguments = ARGUMENT.findall(call[3])
    places = DATA_RECORD_ARGUMENTS[call[2]]
    if len(arguments) != len(places):
        raise NxwrightError(method_count_refusal(name, len(places)), line=number)
    for place, (argument, kind) in enumerate(zip(arguments, places), 1):
        if kind is str and not _ONE_OPERAND.fullmatch(argument):
            raise NxwrightError("argument %d of %s is one text or number, as the Nextion Editor "
                                "compiles it, not %s" % (place, name, argument), line=number)
        if kind is int and any(operand.startswith('"') or operand.endswith(".txt")
                               for operand in _ONE_OPERAND.findall(argument)):
            raise NxwrightError("argument %d of %s is a number, not a text, as the Nextion Editor "
                                "compiles it: %s" % (place, name, argument), line=number)


def _check_file_stream_call(code: str, objects: ObjectNames, number: int):
    """Raises NxwrightError for a call of a file stream of the page given
    another number of arguments than its method takes, which the Nextion
    Editor refuses as it compiles (FILE_STREAM_ARGUMENTS)."""
    call = _FILE_STREAM_CALL.fullmatch(code)
    if call is None or (objects.pages.get(objects.page) or {}).get(call[1]) != "file-stream":
        return
    count = FILE_STREAM_ARGUMENTS[call[2]]
    if len(ARGUMENT.findall(call[3])) != count:
        raise NxwrightError(method_count_refusal("%s.%s" % (call[1], call[2]), count),
                            line=number)


def _check_first_argument(code: str, number: int):
    """Raises NxwrightError for a command of ONE_OPERAND_FIRST whose first
    argument is arithmetic, which the Editor refuses as it compiles."""
    word = command_word(code)
    if word not in ONE_OPERAND_FIRST:
        return
    first = ARGUMENT.match(code[len(word):].strip())
    if first is not None and not is_one_operand(first[0]):
        raise NxwrightError("%s: the Nextion Editor takes one text or number as the first "
                            "argument of %s, not arithmetic or texts joined" % (code, word),
                            line=number)


def is_one_operand(text: str) -> bool:
    """Whether `text` is one operand alone: a text, a number, or a name,
    which may be dotted, as the Editor takes where it refuses arithmetic
    and texts joined (_ONE_OPERAND)."""
    return _ONE_OPERAND.fullmatch(text.strip()) is not None


def _check_xstr_text(code: str, number: int):
    """Raises NxwrightError for an xstr whose text, its last argument, is
    more than one operand, as texts joined or arithmetic. The Editor
    refused `"a"+"b"`, `t0.txt+"b"`, `"a"+t0.txt+"c"`, `sys0+1`, and
    `n0.val*2` there as it compiled ("Invalid Variables"), and compiled one
    operand alone, as a text, a txt, a number, or a variable. An xstr of
    another number of arguments is refused by _check_parameter_count."""
    if command_word(code) != "xstr":
        return
    arguments = command_arguments(code[len("xstr"):].strip())
    if len(arguments) == COMMAND_PARAMETERS["xstr"] and not is_one_operand(arguments[-1]):
        raise NxwrightError("%s: the text of xstr must be one operand: a text, a txt, a "
                            "number, or a variable. The Nextion Editor refuses texts "
                            "joined or arithmetic there (\"%s\")" % (code, INVALID_VARIABLES),
                            line=number)


def _check_first_word(code: str, number: int):
    """Raises NxwrightError for a line whose first word is no command of the
    Editor's, with the words the Editor refuses it with as it compiles
    (first_word_refusal)."""
    refusal = first_word_refusal(code)
    if refusal is None:
        return
    word = first_word(code)
    fix = None
    if refusal == INVALID_VARIABLES and word.lower() in EDITOR_COMMANDS:
        problem = ("the Nextion Editor's commands are written in small letters, as %s, and it "
                   "refuses %s"
                   % (word.lower(), word))
        fix = {"kind": "small-letters", "text": word, "new": word.lower()}
    else:
        problem = "the Nextion Editor knows no command %s, and refuses it" % word
    raise NxwrightError("%s: %s (\"%s\")" % (code, problem, refusal), line=number, fix=fix)


def _check_parameter_count(code: str, number: int):
    """Raises NxwrightError for a command of COMMAND_PARAMETERS given another
    number of arguments than it takes, counted as command_arguments counts
    them. A command written alone is given none: the Editor refused each
    that takes some, but add for no command (NO_COMMAND_WHEN_ALONE). A
    command the table lacks takes any number, but one of no numeric form
    takes some (NO_NUMERIC_FORM)."""
    word = first_word(code)
    if code == word and word in NO_NUMERIC_FORM:
        raise NxwrightError("%s: the Nextion Editor refuses %s written alone, without its "
                            "arguments (\"%s\")" % (code, word, INVALID_ARGUMENT_COUNT),
                            line=number)
    wanted = COMMAND_PARAMETERS.get(word)
    if wanted is None or len(command_arguments(code[len(word):].strip())) == wanted:
        return
    words = INVALID_COMMAND if code == word and word in NO_COMMAND_WHEN_ALONE \
        else INVALID_ARGUMENT_COUNT
    raise NxwrightError("%s: %s takes %d, and the Nextion Editor refuses to compile another "
                        "number (\"%s\")" % (code, word, wanted, words), line=number)


def series_lacks(code: str, series: str):
    """Returns what the line of Editor code `code` uses that a screen of the
    series `series`, such as "K", lacks, which the Editor's compile refuses
    there (editor_language.SERIES_LACKED_COMMANDS and SERIES_LACKED_VARIABLES):
    (LACKED_INSTRUCTION, its command), or (LACKED_VARIABLE, a system
    variable it names outside its quoted texts); None when it uses
    neither."""
    word = command_word(code)
    if word in SERIES_LACKED_COMMANDS[series]:
        return LACKED_INSTRUCTION, word
    for part in STRING.split(code)[::2]:
        for name in _BARE_NAME.findall(part):
            if name in SERIES_LACKED_VARIABLES[series]:
                return LACKED_VARIABLE, name
    return None


def _check_series(code: str, screen: ScreenModel, number: int):
    """Raises NxwrightError for a line using a command or a system variable
    that the series of `screen`, the folder's screen model, lacks, which
    the Editor refuses to compile (series_lacks)."""
    lacked = series_lacks(code, screen.series)
    if lacked is not None:
        kind, word = lacked
        raise NxwrightError("%s: the %s lacks %s, and the Nextion Editor refuses to compile it "
                            "for its series (\"Do not support such %s for this series device\")"
                            % (code, screen.name, word, kind), line=number)


def _check_escapes(code: str, number: int):
    """Raises NxwrightError for an escape inside a quoted text of a line's
    code that the screen does not read (SCREEN_ESCAPES), which the Editor
    refuses as it compiles. The escapes are read in pairs from the left,
    so `"a\\\\nb"` holds an escaped backslash, then letters. A line's comment
    is apart from its code (split_line), as the compile skips it."""
    for text in STRING.findall(code):
        for escape in re.finditer(r"\\(.)", text[1:-1]):
            if escape[1] not in SCREEN_ESCAPES:
                raise NxwrightError("%s: the screen does not read the escape \\%s, and the "
                                    "Nextion Editor refuses to compile it (\"Improper use of "
                                    "escape characters\")"
                                    % (code, escape[1]), line=number)


def _check_condition_texts(code: str, number: int):
    """Raises NxwrightError for a quoted text that ends in an escaped
    backslash, as in `"a\\\\"`, inside a condition: the head of an if, an
    else if, or a while, or the middle part of a for's head. The Editor
    refused each as it compiled ("SYNTAX ERROR"). It compiled the same text
    in a for's first and last parts, and outside a head."""
    head, otherwise = _BLOCK_HEAD.match(code), ELSE.match(code)
    if not (head or (otherwise and otherwise[2])):
        return
    in_for = head is not None and head[1] == "for"
    # A for's parts are apart at the semicolons outside its texts.
    semicolons, after = 0, 0
    for text in STRING.finditer(code):
        semicolons += code.count(";", after, text.start())
        after = text.end()
        if ends_in_escaped_backslash(text[0]) and (not in_for or semicolons == 1):
            raise NxwrightError("%s: the Nextion Editor refuses a text that ends in an escaped "
                                "backslash in a condition (\"SYNTAX ERROR\")" % code,
                                line=number)


def ends_in_escaped_backslash(text: str) -> bool:
    """Whether the quoted text `text`, its quotes included, ends in an
    escaped backslash: its last escape, read in pairs from the left, is
    `\\\\` right before its closing quote, as in `"a\\\\"`. The Editor refused
    such a text in a condition (_check_condition_texts)."""
    escapes = list(re.finditer(r"\\(.)", text[1:-1]))
    return bool(escapes) and escapes[-1][1] == "\\" and escapes[-1].end() == len(text) - 2


def _value_kind(operand: str, variables) -> str:
    """Returns the kind of an operand, _TEXT or _NUMBER, or None when it is
    of no known kind: a text is a quoted text or a `txt`; a number is a
    number written out, a `val`, a `pco`, or a `font` (_ATTRIBUTE_KINDS), a
    system variable, or one of program.nx's `int` variables, `variables`.
    An attribute reached through the screen's arrays, as `b[1].val`, is of
    no known kind."""
    if operand.startswith('"'):
        return _TEXT
    if _NUMBER_WRITTEN.fullmatch(operand):
        return _NUMBER
    if "[" in operand:
        return None
    if "." in operand:
        return _ATTRIBUTE_KINDS.get(operand.rpartition(".")[2])
    if (operand in EDITOR_SYSTEM_VARIABLES or operand in EDITOR_PROGRAM_VARIABLES
            or operand in (variables or ())):
        return _NUMBER
    return None


def _value_terms(value: str):
    """Returns a value's operands, each with the operator before it, None
    for the first: [(operator, operand)]. None when the value is not
    operands joined by operators, as a call's."""
    terms, position, operator = [], 0, None
    while True:
        operand = _VALUE_OPERAND.match(value, position)
        if operand is None:
            return None
        terms.append((operator, operand[0]))
        position = operand.end()
        if position == len(value):
            return terms
        sign = _VALUE_OPERATOR.match(value, position)
        if sign is None:
            return None
        operator, position = sign[0], sign.end()


def _check_assignment_kinds(code: str, variables, number: int):
    """Raises NxwrightError for an assignment the Editor refuses as it
    compiles for the kinds of its values (_value_kind), where they are known.
    One operand of the other kind given to the target: "Assignment operation
    failed". Then, as the Editor computes from left to right, a compound
    assignment's target being the first operand: a text in a number's
    value, a number joined by `+` to a text, or an operator other than `+`
    and `-` on a text: "Invalid variable operation". A text's `-` with a
    number, which removes characters, is taken. A condition is no
    assignment, and is not checked."""
    assignment = _ASSIGNMENT_LINE.fullmatch(code)
    if assignment is None:
        return
    target, operator, value = assignment.groups()
    wanted, terms = _value_kind(target, variables), _value_terms(value)
    if wanted is None or terms is None:
        return
    kinds = [(joining, _value_kind(operand, variables)) for joining, operand in terms]
    if operator == "=" and len(kinds) == 1:
        if kinds[0][1] not in (None, wanted):
            raise NxwrightError("%s: the Nextion Editor refuses to compile a %s given to a %s "
                                "(\"Assignment operation failed\")"
                                % (code, kinds[0][1], wanted), line=number)
        return
    if operator != "=":
        kinds = [(None, wanted), (operator[:-1], kinds[0][1])] + kinds[1:]
    mixed = ("%s: the Nextion Editor refuses to compile a text and a number joined so "
             "(\"Invalid variable operation\")" % code)
    if wanted == _NUMBER:
        if any(kind == _TEXT for _, kind in kinds):
            raise NxwrightError(mixed, line=number)
        return
    left = kinds[0][1]
    for joining, right in kinds[1:]:
        if joining == "+":
            if {left, right} == {_TEXT, _NUMBER}:
                raise NxwrightError(mixed, line=number)
            left = _TEXT if _TEXT in (left, right) else None
        elif joining == "-":
            # A number removes characters; a text taken from a text was not
            # tried in the Editor, and is taken.
            left = left if right == _NUMBER else None
        elif _TEXT in (left, right):
            raise NxwrightError("%s: the Nextion Editor refuses %s on a text (\"Invalid variable "
                                "operation\")" % (code, joining), line=number)
        else:
            left = None


def _check_absent_attributes(code: str, objects: ObjectNames, number: int):
    """Raises NxwrightError for an attribute a component lacks by its page
    file's values (ObjectNames.absent_attributes), assigned or read, which
    the Editor refuses as it compiles ("Invalid Variables"): a variable's
    `val` while it holds a text, for one. A component reached through the
    screen's arrays is not checked."""
    if not objects.absent_attributes:
        return
    for page, name, attribute in _named_attributes(code, objects):
        why = ((objects.absent_attributes.get(page) or {}).get(name) or {}).get(attribute)
        if why is not None:
            raise NxwrightError("%s: %s %s, so it has no %s, and the Nextion Editor refuses to "
                                "compile it (\"Invalid Variables\")"
                                % (code, name, why, attribute), line=number)


def _check_type_names(code: str, objects: ObjectNames, number: int):
    """Raises NxwrightError for a name, read or assigned, that the type of
    the component it follows does not have (attribute_descriptions.type_has),
    which the Editor refuses as it compiles ("Invalid Variables"): a
    number's `vall`, or its `txt`. A component of a page whose objects are
    unknown, and a component named through its page without an attribute,
    as `first.t0`, are left to the Editor."""
    for page, name, attribute in _named_attributes(code, objects):
        objects_of_page = objects.pages.get(page) or {}
        type_name = objects_of_page.get(name)
        if type_name is None or type_has(type_name, attribute):
            continue
        if type_name == "page" and attribute in objects_of_page:
            continue        # a component named through its page
        if type_name == "page" or page == objects.page:
            who = name
        else:
            who = "%s's %s" % (page, name)
        # "an xfloat" too, said with a vowel ("ex-float").
        article = "an" if type_name[0] in "aeioux" else "a"
        raise NxwrightError("%s: %s is %s %s, which has no %s, and the Nextion Editor refuses to "
                            "compile it (\"Invalid Variables\")"
                            % (code, who, article, type_name, attribute), line=number)


def _named_attributes(code: str, objects: ObjectNames):
    """Yields (page, component, name) for each name the line gives after a
    component, outside its quoted texts: `t0.val`, when `t0` is an object
    of the page, the page itself among them; and `second.t1.val`, whatever
    its names, which the caller looks up. A component reached through the
    screen's arrays, as `b[1].val`, is not yielded."""
    for part in STRING.split(code)[::2]:
        for match in _DOTTED.finditer(part):
            first, second, third = match.groups()
            if third is not None:
                yield first, second, third
            elif objects.page is not None and first in objects.own:
                yield objects.page, first, second


def method_count_refusal(name: str, count: int) -> str:
    """Returns the refusal of a call of a component's method `name`, as
    `d0.insert` or `fs0.read`, given other than the `count` arguments it
    takes."""
    words = {0: "no arguments", 1: "1 argument"}.get(count, "%d arguments" % count)
    return "%s takes %s, as the Nextion Editor compiles it" % (name, words)


def _check_assigned_attribute(code: str, objects: ObjectNames, number: int):
    """Raises NxwrightError for a line assigning to an attribute code cannot
    change, of the page's own object or of another page's, which the Editor
    refused to compile ("Assignment operation failed"); or to a method,
    which code calls, as `d0.insert("a^b")`, and the Editor refused to
    compile assigned ("Invalid Variables"). The message names the page, as
    a line of a file several pages include may be refused for one alone. A
    name it cannot tell the type of, and one the type does not have, are
    left to other checks."""
    assigned = _assigned_attribute(code, objects)
    if assigned is None:
        return
    type_name, attribute, owner = assigned
    if not type_has(type_name, attribute):
        return
    described = describe(type_name, attribute)
    if described is not None and described.method:
        raise NxwrightError("%s: %s is a method of %s, which code calls, and the Nextion Editor "
                            "refuses to compile an assignment to it (\"Invalid Variables\")"
                            % (code, attribute, owner), line=number)
    if code_cannot_change(type_name, attribute):
        raise NxwrightError("%s: the Nextion Editor refuses to assign to %s of %s, which code "
                            "cannot change" % (code, attribute, owner), line=number)


def _check_series_assignment(code: str, objects: ObjectNames, screen: ScreenModel, number: int):
    """Raises NxwrightError for a line assigning to an attribute that code
    can change on other series, and not on the series of `screen`
    (code_cannot_change_on_series), which the Editor refused to compile
    ("Assignment operation failed"). A name the type does not have is left
    to _check_type_names, and one it cannot tell the type of to the
    Editor."""
    if screen.series not in ATTRIBUTES_CODE_CANNOT_CHANGE_ON_SERIES:
        return
    assigned = _assigned_attribute(code, objects)
    if assigned is None:
        return
    type_name, attribute, owner = assigned
    if (code_cannot_change_on_series(type_name, attribute, screen.series)
            and type_has(type_name, attribute)):
        raise NxwrightError("%s: on the %s, the Nextion Editor refuses to assign to %s of %s, "
                            "which code cannot change on its series (\"Assignment operation "
                            "failed\")"
                            % (code, screen.name, attribute, owner), line=number)


def _assigned_attribute(code: str, objects: ObjectNames):
    """Returns (type name, attribute, owner) for a line assigning to an
    attribute of the page's own object or of another page's, or None for
    another line and for an object it cannot tell the type of. The owner
    names the object for a refusal, with its page, as a line of a file
    several pages include may be refused for one alone."""
    assigned = _ASSIGNED_ATTRIBUTE.match(code)
    if assigned is None:
        return None
    first, second, third = assigned.groups()
    if third is not None:
        page, name, attribute = first, second, third
    elif first in objects.own:
        page, name, attribute = objects.page, first, second
    else:
        page, name, attribute = first, first, second
    type_name = (objects.pages.get(page) or {}).get(name)
    if type_name is None:
        return None
    owner = "the page %s" % name if type_name == "page" else "%s's %s %s" % (page, type_name,
                                                                              name)
    return type_name, attribute, owner


def _check_program_variables(code: str, variables: frozenset, number: int):
    """Raises NxwrightError for a line naming sys0, sys1, or sys2 outside its
    strings when `variables`, program.nx's int variables, lack it, which
    the Editor refused to compile ("Invalid Variables")."""
    for part in STRING.split(code)[::2]:
        for name in _PROGRAM_VARIABLE.findall(part):
            if name not in variables:
                raise NxwrightError(UNDECLARED_PROGRAM_VARIABLE % name, line=number,
                                    fix={"kind": "declare", "variable": name})


def _check_names_alone(code: str, objects: ObjectNames, variables: frozenset, number: int):
    """Raises NxwrightError for a name alone in a value, a condition, an
    index, or the first argument of a command of ONE_OPERAND_FIRST, that is
    no int of program.nx (`variables`), no system variable, and no colour.
    The Editor refused each such name as it compiled ("Invalid Variables:"
    and the name). Its colours'
    names it took in capitals only. A component's or a page's name alone it
    refused too."""
    word = command_word(code)
    otherwise = ELSE.match(code)
    if word in ONE_OPERAND_FIRST:
        checked = command_arguments(code[len(word) + 1:])[:1]
    elif _BLOCK_HEAD.match(code) or (otherwise and otherwise[2]) or ASSIGNMENT.match(code):
        checked = [code]
    else:
        return
    known = (EDITOR_SYSTEM_VARIABLES | frozenset(EDITOR_COLOURS) | variables
             | frozenset(EDITOR_PROGRAM_VARIABLES) | _KEYWORDS)
    for text in checked:
        for part in STRING.split(text)[::2]:
            for name in _NAME_ALONE.findall(part):
                if name not in known:
                    raise NxwrightError(_name_alone_refusal(code, name, objects, known),
                                        line=number)


def _name_alone_refusal(code: str, name: str, objects: ObjectNames, known: frozenset) -> str:
    """The words of _check_names_alone's refusal of `name`."""
    words = "the Nextion Editor knows no %s: a name alone is an int of program.nx, a system " \
            "variable, or a colour" % name
    if objects is not None and (name in objects.own or name in objects.pages):
        kind = "page" if name in objects.pages else "component"
        words = ("%s names a %s, which the Nextion Editor refuses alone: name one of its "
                 "attributes" % (name, kind))
    else:
        written = next((other for other in sorted(known - _KEYWORDS)
                        if other.lower() == name.lower()), None)
        if written is not None:
            words = "the Nextion Editor knows no %s, though it knows %s" % (name, written)
    return "%s: %s (\"%s\")" % (code, words, INVALID_VARIABLES)


def _check_hex(code: str, number: int):
    """Raises NxwrightError for a hex constant outside strings that the
    Editor refuses: one whose digits are not in pairs, one past 32 bits,
    one with a sign, or any in an int's starting value."""
    # Each string becomes an empty one, so that its text is not read as code
    # and it still ends an operand.
    bare = STRING.sub('""', code)
    for match in _HEX.finditer(bare):
        digits = match[1]
        if is_declaration(code):
            raise NxwrightError("an int's starting value cannot be hex, as %s is"
                                % match[0], line=number)
        if not digits or len(digits) % 2:
            # A 0 before the digits keeps the value. A bare 0x holds none, and
            # one past 32 bits is refused padded too, so neither gets the fix.
            fix = None if not digits or int(digits, 16) > 0xFFFFFFFF else {
                "kind": "hex-pairs", "text": match[0], "new": match[0][:2] + "0" + digits}
            raise NxwrightError("%s: the Nextion Editor wants hex digits in pairs, a byte each"
                                % match[0], line=number, fix=fix)
        before = bare[:match.start()].rstrip()
        if before.endswith("-") and minus_is_sign(before[:-1]):
            # The decimal number keeps the value, where 32 bits hold it.
            value = -int(digits, 16)
            fix = None if value < -0x80000000 else {
                "kind": "hex-sign", "text": "-" + match[0], "new": str(value)}
            raise NxwrightError("-%s: the Nextion Editor refuses a sign on a hex constant"
                                % match[0], line=number, fix=fix)
        if int(digits, 16) > 0xFFFFFFFF:
            raise NxwrightError("%s: the Nextion Editor refuses a hex constant past 32 bits"
                                % match[0], line=number)


def check_labels(lines: list):
    """Raises NxwrightError for a goto whose label the event's `lines`, as
    (line number, code), lack, and for a label twice among them, whatever
    block it is in. The Editor refused both as it compiled ("nofind mark",
    "repeated mark"), and for a label of characters it refused ("the make
    is invalid")."""
    labels = set()
    for number, code in lines:
        if _LABEL_LIKE.fullmatch(code) and code[0] in "{}":
            # The Editor compiled {a:, }a:, {:, and }: as labels, but
            # nxwright's readers of blocks take a line starting with a brace
            # for one of a block's.
            raise NxwrightError("%s: a label cannot start with { or } in nxwright, which reads "
                                "such a line as a block's brace, though the Nextion Editor "
                                "takes it" % code[:-1], line=number)
        if _LABEL_LIKE.fullmatch(code) and not LABEL.fullmatch(code):
            raise NxwrightError("%s: the Nextion Editor refuses this label (\"the make is "
                                "invalid\"): a label cannot start with a digit, or hold "
                                "+ - * / %% = , . [ ] & ' \\ or \"" % code[:-1], line=number)
    for number, code in lines:
        label = LABEL.fullmatch(code)
        if label and label[1] in labels:
            raise NxwrightError("%s: the Nextion Editor refuses a label twice in one event"
                                % label[1], line=number)
        if label:
            labels.add(label[1])
    for number, code in lines:
        label = goto_label(code)
        if label is not None and label not in labels:
            raise NxwrightError("%s: the Nextion Editor finds no label %s in this event"
                                % (code, label), line=number)


def first_word_refusal(code: str):
    """Returns the words the Editor refuses a line's code part with, as it
    compiles, when its first word (first_word) is no command of the
    Editor's (EDITOR_COMMANDS); None when it is one, or the line has none.
    A word holding a capital letter, and movelayer, it reads as a name,
    INVALID_VARIABLES. Any other is INVALID_COMMAND."""
    word = first_word(code)
    if word is None or word in EDITOR_COMMANDS:
        return None
    if word in REFUSED_AS_A_NAME or word != word.lower():
        return INVALID_VARIABLES
    return INVALID_COMMAND
