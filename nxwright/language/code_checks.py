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
(editor_limits.code_cannot_change_on_series). Given each page's objects,
for a line of program.nx, they refuse an int whose name or starting value
the Nextion Editor refuses, and check_program_declarations refuses an int declared
twice or after other code. In an event or a macro, they refuse any int.

Also here are the Nextion Editor's refusal words, such as INVALID_COMMAND,
and the tables of commands' arguments, such as COMMAND_PARAMETERS and
DATA_RECORD_ARGUMENTS, which the test machine reads too.
"""
from dataclasses import dataclass
import re

from nxwright import NxwrightError
from nxwright.language.code_lines import (ARGUMENT, ASSIGNMENT, ELSE, LABEL, OWN_ATTRIBUTE,
                                          OWN_FORM, STRING, chain_parts, command_arguments,
                                          command_word, compact, declared_int_names,
                                          declared_ints, first_word, goto_label,
                                          holds_own_attribute, is_declaration,
                                          malformed_int_part, minus_is_sign)
from nxwright.project.attribute_descriptions import code_cannot_change, describe, type_has
from nxwright.project.editor_language import (EDITOR_COLOURS, EDITOR_COMMANDS,
                                              EDITOR_PROGRAM_VARIABLES,
                                              EDITOR_SYSTEM_VARIABLES, NO_COMMAND_WHEN_ALONE,
                                              REFUSED_AS_A_NAME,
                                              SERIES_LACKED_COMMANDS, SERIES_LACKED_VARIABLES,
                                              UNDECLARED_PROGRAM_VARIABLE)
from nxwright.project.editor_limits import (ATTRIBUTES_CODE_CANNOT_CHANGE_ON_SERIES,
                                            LONGEST_LINES, code_cannot_change_on_series)
from nxwright.project.screen_arithmetic import int32
from nxwright.project.screen_models import ScreenModel

_BLOCK_HEAD = re.compile(r"(if|while|for)\s*\(")
# The operators that join the comparisons of a condition, and the operators
# that compare two values.
_JOIN = re.compile(r"&&|\|\|")
_COMPARISON_OPERATOR = re.compile(r"==|!=|<=|>=|<|>")
# The Nextion Editor turns each comparison into a line `i <left>,<right>,1,0`.
# This is how many bytes that line adds to the two sides.
_COMPARISON_LINE_EXTRA = len("i ,,1,0")
# A message shows at most this many characters of a long comparison.
_SHOWN_COMPARISON = 40
# A line assigning to an object's attribute, in Editor syntax: the object,
# or a page and its object, then the attribute, then the assignment.
_ASSIGNED_ATTRIBUTE = re.compile(r"([A-Za-z_]\w*)\.([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?"
                                 r"(?:\+\+|--|[-+*/%&|^]?=(?!=))")
# A tab after `int`, which the Editor reads as part of the name, refusing
# the declaration. (Worked out from the Editor 1.68.2.)
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
INVALID_COMPONENT_ID, INVALID_PAGE_ID = "Invalid Component ID", "Invalid Page ID"
INVALID_VARIABLE_OPERATION = "Invalid variable operation"
# As a command, one of these words can only be nxlang. `return` and `default:`
# are left out because the Nextion Editor has a `return` command, and reads
# `default:` as a label.
_NXLANG_WORDS = frozenset({"var", "const", "function", "switch", "case", "break", "continue"})
# "name.attribute" or "page.name.attribute", not part of a longer chain such
# as "b[3].txt", whose component is chosen at run time.
_DOTTED = re.compile(r"(?<![\w.\]])([A-Za-z_]\w*)\.([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?")
# Commands whose first argument names a component of the page. A component's
# ID is accepted there too, and is not checked.
_NAMING_COMMANDS = "vis|tsw|ref|click"
# Each command that takes a component, with the places of the arguments
# that give one, counted from 0: vis's first, cfgpio's third, and both of
# setlayer's. A component is given by its name, by its ID, or by a variable
# that contains the ID.
COMPONENT_PLACES = {"vis": (0,), "tsw": (0,), "click": (0,), "ref": (0,), "move": (0,),
                    "cfgpio": (2,), "setlayer": (0, 1)}
# A component's txt, as t0.txt, page0.t0.txt, or b[1].txt.
_TXT = re.compile(r"[\w.\[\]]*\.txt")
# A component reached through the screen's arrays: b[i], the current page's
# component of ID i, or p[n].b[i], page n's. An index may hold one level of
# brackets, as b[a[1]], so that b[1]+b[2] is not read as one.
_INDEX = r"(?:[^\[\]]|\[[^\[\]]*\])*"
SCREEN_ARRAY = re.compile(r"(?:p\[%s\]\.)?b\[(%s)\]" % (_INDEX, _INDEX))
_NAME_ONLY = re.compile(r"[A-Za-z_]\w*")
# The places of commands' arguments that take a number, counted from 0: the
# Nextion Editor refused a text and a txt in each ("Invalid variable
# operation"), and an operand it does not read, such as `5a` ("Invalid
# Variables").
NUMBER_PLACES = {"cls": (0,), "add": (0, 1, 2), "addt": (0, 1, 2), "cle": (0, 1),
                 "prints": (1,), "pa_txt": (2, 3), "newfile": (1,), "rdfile": (1,)}
# Some commands take a single value in certain arguments, such as getv's
# argument or cov's destination. The Nextion Editor refuses an expression
# there, as in `wepo sys0+1,0` ("Invalid Variables"). The arguments are
# counted from 0, and sorted by what the command does with the value:
#   - READ_ONE_OPERAND_PLACES: the command only reads the value, as the
#     vendor's instruction set documents. In an event, nxlang puts an
#     expression in one of these arguments in a temporary first.
#   - _WRITTEN_ONE_OPERAND_PLACES: the command puts its result there.
#   - _UNDOCUMENTED_ONE_OPERAND_PLACES: arguments of commands the vendor
#     does not document, so nobody knows whether they are read or written.
# covx's first argument is checked along with get's (ONE_OPERAND_FIRST).
READ_ONE_OPERAND_PLACES = {"wepo": (0,), "crcputs": (0,), "delfile": (0,), "strlen": (0,),
                           "substr": (0,), "spstr": (0, 2), "btlen": (0,)}
_WRITTEN_ONE_OPERAND_PLACES = {"repo": (0,), "ucopy": (0,), "findfile": (1,), "cov": (1,),
                               "covx": (1,), "strlen": (1,)}
_UNDOCUMENTED_ONE_OPERAND_PLACES = {
    "getv": (0,), "fstr": (0,), "strsize": (2,), "pa_q": (0, 1), "pa_txt": (1,), "gets": (1,),
    "i": (0, 1), "nstr": (0,), "zstr": (4,), "qrcode": (7,), "piccolor": (3,)}
ONE_OPERAND_PLACES = {
    word: (READ_ONE_OPERAND_PLACES.get(word, ()) + _WRITTEN_ONE_OPERAND_PLACES.get(word, ())
           + _UNDOCUMENTED_ONE_OPERAND_PLACES.get(word, ()))
    for word in (READ_ONE_OPERAND_PLACES.keys() | _WRITTEN_ONE_OPERAND_PLACES.keys()
                 | _UNDOCUMENTED_ONE_OPERAND_PLACES.keys())}
# sets takes any number of arguments, and the Nextion Editor refused an
# expression in each.
ONE_OPERAND_EVERYWHERE = ("sets",)
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
# The most characters the Nextion Editor takes in the name of an int of
# program.nx ("Illegal global variable name length").
LONGEST_INT_NAME = 32
# An int declaration's starting value written in decimal: an optional
# sign, then the digits.
_DECIMAL_START = re.compile(r"([+-]?)([0-9]+)")
# A decimal starting value with spaces or tabs between its sign and its
# digits. The Nextion Editor rejects it.
_SPACED_SIGN_START = re.compile(r"[+-]\s+[0-9]+")
# The Nextion Editor's words for a starting value it rejects.
_INITIAL_VALUE_WORDS = "Initial value for a global variable must be a constant"
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
# Editor 1.68.2's compile refused any other number, "Invalid number of
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
    # Undocumented by the vendor. TFTTool's command tables name them
    # (INDEPENDENCE.md, Public documents). Each compiled with one number of
    # arguments, and no other from 0 to 12, on every series that takes it;
    # draw_h and setbrush to 16. lcd_dev's hex values are spaced, as printh's
    # bytes.
    "lcd_dev": 1, "getpassw": 0, "lcd_refx": 0, "lhmi_cle": 0, "showqq": 0, "getv": 1,
    "init": 1, "setbaudz": 1, "pa_q": 2, "whmi_cle": 2, "fstr": 3, "nstr": 3, "rfpt": 3,
    "strsize": 3, "wfpt": 3, "pa_txt": 4, "timerset": 4, "zstr": 5, "comok": 7, "draw3d": 7,
    "qrcode": 8, "draw_h": 13, "setbrush": 15,
    # Undocumented too: each compiled with one number of arguments, and the
    # Editor refused the other numbers tried. Only the number is checked here.
    # i takes two texts or two numbers, then two numbers. gets takes two
    # values of any kind. piccolor takes three numbers, then one value of any
    # kind. The others take numbers.
    "i": 4, "beepset": 2, "meup": 2, "gets": 2, "cfguart": 4, "piccolor": 4, "cuts": 7,
    "xnum": 10,
    "covx": 4, "cov": 3, "substr": 4, "spstr": 4, "strlen": 2, "btlen": 2,
    "newdir": 1, "deldir": 1, "delfile": 1, "refile": 2, "redir": 2, "newfile": 2,
    "findfile": 2, "finddir": 2, "rdfile": 4, "twfile": 2,
    # The Editor compiled each with two, and refused none, one, and three.
    "crcrest": 2, "crcputs": 2, "crcputu": 2,
    # The Editor compiled each alone, and refused each given one argument.
    "rest": 0, "touch_j": 0, "code_c": 0,
    # The Nextion Editor refused `doevents 1`, `page 1,2`, and `page` alone
    # as it compiled. Its simulator answered 1E to the first two typed, as
    # to `get 1,2`.
    "doevents": 0, "ref_stop": 0, "ref_star": 0, "com_stop": 0, "com_star": 0, "page": 1,
}
# One operand alone: a string, a number, or a name, which may be dotted.
_ONE_OPERAND = re.compile(r'"(?:\\.|[^"\\])*"|-?\w+(?:\[[^\]]*\])?(?:\.\w+(?:\[[^\]]*\])?)*')
# A minus before a name, as in -sys0 or -RED (_has_minus_before_a_name).
_MINUS_BEFORE_A_NAME = re.compile(r"-[A-Za-z_]")
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

    `reachable` contains each page's components of global scope, by page
    name. Another page's code, or a macro's, can use only these, and only
    with their page's name. Scope is not checked for a page whose entry is
    None or missing. A macro's code belongs to no page, because the Nextion
    Editor compiles macros apart from every page (macros_source.py). Its
    `page` is None, and its `own` is empty.

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
                screen: ScreenModel, number: int, program_pages: dict = None, codec=None,
                program_globals: dict = None, suggest_nxlang: bool = False):
    """Raises NxwrightError for a line's code part, its resources' names
    resolved, that the Editor refuses as it compiles, as
    code_preprocessor.preprocess says. `program_pages`, for a line of
    program.nx, holds each page's objects, by page name, and
    `program_globals` each page's components of global scope. `codec`, the
    project's TextCodec, counts the line's bytes for `screen`'s series
    (_check_length). If `suggest_nxlang` is true and the line starts with a
    word that only nxlang has, the error says how to switch."""
    if _TAB_AFTER_INT.match(code):
        raise NxwrightError("a tab after int: the Nextion Editor takes int and a space only, and "
                            "refuses this declaration (\"Invalid Variables\")", line=number,
                            fix={"kind": "tab-after-int", "text": "int\t", "new": "int "})
    _check_hex(code, number)
    if is_declaration(code):
        if program_pages is not None:
            _check_declared_names(code, program_pages, number)
            check_int_declaration(code, number)
        elif objects is not None:
            _refuse_declaration_outside_program(code, objects, number)
        return
    if code.endswith("{") and code != "{":
        code = code[:-1].rstrip()
        if not (_BLOCK_HEAD.match(code) or ELSE.match(code)):
            if suggest_nxlang:
                _check_nxlang_word(code, number)
            raise NxwrightError("\"{\" can only end an if, while, for, or else line",
                                line=number)
    code = compact(code)
    if codec is not None and screen is not None:
        _check_length(code, codec, LONGEST_LINES[screen.series], number)
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
        _check_program_attributes(code, program_pages, program_globals or {}, number)
    # Before the number of arguments, as the Editor named the series
    # first for `beep 100,2` on a screen whose series lacks beep.
    if screen is not None:
        _check_series(code, screen, number)
        if objects is not None:
            _check_series_assignment(code, objects, screen, number)
    # A word that is no command has no number of arguments to count.
    _check_first_word(code, number, suggest_nxlang)
    _check_parameter_count(code, number)
    _check_first_argument(code, number)
    _check_xstr_text(code, number)
    _check_components(code, objects, variables, program_pages, number)
    _check_number_arguments(code, number)
    _check_one_operand_arguments(code, number)
    pages = program_pages if program_pages is not None else (
        objects.pages if objects is not None else None)
    _check_page_argument(code, pages, variables, number)
    if variables is not None:
        _check_program_variables(code, variables, number)
        _check_names_alone(code, objects, variables, number)
    if macros is not None:
        _check_call(code, macros, number)
    _check_escapes(code, number)
    _check_condition_texts(code, number)
    if codec is not None:
        _check_texts_in_pairs(code, codec, number)
        _check_texts_byte_by_byte(code, codec, number)
    # A name a component's type lacks, or one its values leave out, first,
    # as the Editor names it.
    if objects is not None:
        _check_type_names(code, objects, number)
        _check_absent_attributes(code, objects, number)
    _check_assignment_kinds(code, variables, number)


def _check_length(code: str, codec, longest: int, number: int):
    """Raises NxwrightError for a compacted line longer than `longest`
    bytes in the project's encoding, `codec`. The head of an `if`, an
    `else if`, or a `while` is not limited as a whole, but each comparison
    in it is (_check_comparison_lengths). In a `for`'s head, the start, the
    step, and each comparison in the condition are limited like lines. The
    Nextion Editor refused longer ones ("The instructions are too long"),
    but it compiled heads of more than 1000 characters. If the encoding
    cannot store a character, the line is left to the build, which refuses
    it."""
    head, otherwise = _BLOCK_HEAD.match(code), ELSE.match(code)
    if otherwise and otherwise[2]:
        opening = code.find("(", otherwise.end())
        if opening >= 0:
            _check_comparison_lengths(code[opening + 1:].removesuffix(")"), codec, longest,
                                      number)
        return
    if head and head[1] != "for":
        _check_comparison_lengths(code[head.end():].removesuffix(")"), codec, longest, number)
        return
    refusal = "and this series takes at most %d (\"The instructions are too long\")" % longest
    if not head:
        _check_part_length(code, "this line", refusal, codec, longest, number)
        return
    # The parts end at the head's semicolons, which no text in a for's head
    # may hold (_check_value_and_head).
    parts = code[head.end():].removesuffix(")").split(";")
    _check_part_length(parts[0], "this for's start", refusal, codec, longest, number)
    if len(parts) > 1:
        _check_comparison_lengths(parts[1], codec, longest, number)
    if len(parts) > 2:
        _check_part_length(parts[2], "this for's step", refusal, codec, longest, number)


def _check_comparison_lengths(condition: str, codec, longest: int, number: int):
    """Raises NxwrightError when a comparison in the compacted `condition`
    is too long once the Nextion Editor compiles it. The Nextion Editor
    turns each comparison into a line of its own, `i <left>,<right>,<number>,0`,
    which is the two sides plus 7 bytes. When that line was longer than
    `longest` bytes in `codec`'s encoding, the Nextion Editor said "The
    instructions are too long", then "Index was outside the bounds of the
    array", and wrote no file."""
    for comparison in _comparisons(condition):
        sides = _comparison_sides(comparison)
        if sides is None:
            continue
        try:
            size = sum(len(codec.encode(side, "")) for side in sides) + _COMPARISON_LINE_EXTRA
        except NxwrightError:
            return
        if size > longest:
            shown = comparison if len(comparison) <= _SHOWN_COMPARISON else \
                comparison[:_SHOWN_COMPARISON] + "…"
            # Only a long quoted text can make a side this long, so the
            # message suggests a shorter one.
            raise NxwrightError("the comparison %s is too long. The Nextion Editor turns it into "
                                "a line of %d bytes in %s, and on this series it takes at most "
                                "%d (\"The instructions are too long\"). Compare a shorter text."
                                % (shown, size, codec.name, longest), line=number)


def _comparisons(condition: str) -> list:
    """Returns the comparisons of a condition, split at each `&&` and `||`
    outside its texts. For example, `t0.txt=="a&&b"&&sys0==1` gives
    `t0.txt=="a&&b"` and `sys0==1`."""
    comparisons = [""]
    # STRING.split puts the parts outside texts at even places, and the
    # texts at odd places.
    for index, piece in enumerate(STRING.split(condition)):
        if index % 2:
            comparisons[-1] += piece
            continue
        first, *others = _JOIN.split(piece)
        comparisons[-1] += first
        comparisons += others
    return comparisons


def _comparison_sides(comparison: str):
    """Returns the two sides of `comparison`, split at its first comparison
    operator outside its texts. Returns None if it has no such operator."""
    position = 0
    for index, piece in enumerate(STRING.split(comparison)):
        operator = _COMPARISON_OPERATOR.search(piece) if index % 2 == 0 else None
        if operator:
            return (comparison[:position + operator.start()],
                    comparison[position + operator.end():])
        position += len(piece)
    return None


def _check_part_length(part: str, what: str, refusal: str, codec, longest: int, number: int):
    """Raises NxwrightError, saying `what` is too long and then `refusal`,
    when `part` is longer than `longest` bytes in `codec`'s encoding
    (_check_length)."""
    try:
        size = len(codec.encode(part, ""))
    except NxwrightError:
        return
    if size > longest:
        raise NxwrightError("%s is %d bytes in %s, not counting the spaces the Nextion Editor "
                            "drops, %s" % (what, size, codec.name, refusal), line=number)


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
    """Raises NxwrightError when a line of a page's code uses a component or
    a page that does not exist, another page's component of local scope
    (ObjectNames.reachable), or another page's own attribute. Another page's
    components are written with the page's name first.

    On the T and K series, the Nextion Editor rejected a line that used
    another page's component of local scope, such as `page1.t1.txt` with
    `t1` local, or another page's own attribute, such as `page1.bco`,
    whatever that page's scope. It gave "Invalid Variables" for both,
    whether the line read or assigned them. It compiled `page0.t0.txt` on
    page0 with `t0` local, and the array form `page1.b[1].val`. The array
    form picks its component when the code runs, so it is not checked."""
    for part in STRING.split(code)[::2]:
        for match in _DOTTED.finditer(part):
            first, second, third = match[1], match[2], match[3] or ""
            if first not in objects.pages:
                if first not in objects.own:
                    raise NxwrightError("%s is neither on this page nor a page"
                                        % first, line=number)
                continue
            known = objects.pages[first]
            if known is None:
                continue
            if third and second not in known:
                raise NxwrightError("page %s has no component %s"
                                    % (first, second), line=number)
            # `first` is this page, or one of its components that has the same
            # name as another page, such as a radio named `second` in `second.val`.
            if first in objects.own:
                continue
            # In `page1.b[1].val`, `b` is the array of page1's components, so the
            # check for another page's attributes skips it.
            array = part.startswith("[", match.end())
            if not third and not array and second not in known:
                raise NxwrightError("%s.%s: only page %s's own code can use the page's "
                                    "attributes. The Nextion Editor refuses this line (\"%s\")"
                                    % (first, second, first, INVALID_VARIABLES), line=number)
            reachable = (objects.reachable or {}).get(first)
            if third and reachable is not None and second not in reachable:
                raise NxwrightError("%s.%s: %s is of local scope, so another page's code cannot "
                                    "use it. The Nextion Editor refuses this line (\"%s\"). Give "
                                    "%s global scope (vscope = 1)."
                                    % (first, second, second, INVALID_VARIABLES, second),
                                    line=number)


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


def _check_declared_names(code: str, pages: dict, number: int):
    """Raises NxwrightError for an int declaration of program.nx whose name
    the Editor refuses. `pages` holds each page's objects, by page name, as
    ObjectNames.pages does, the page itself among them.

    The Nextion Editor refuses five kinds of name, and a name past
    LONGEST_INT_NAME characters:
      - a command's, even one the series lacks, as `int sets=0` on T;
      - a system variable's, as `int dim=0`;
      - a colour's, as `int RED=1`;
      - a page's;
      - a component's, on any page.
    Names are compared as written, letter case included, so `Red` is fine.

    nxlang refuses these names too, rather than renaming the int. A
    program.nx int is shared by name with whatever reads it over the serial
    line, so a new name would break that reader."""
    for name in declared_int_names(code):
        if len(name) > LONGEST_INT_NAME:
            raise NxwrightError("%s: %s has %d characters, and the Nextion Editor takes at most "
                                "%d in an int's name (\"Illegal global variable name length\")"
                                % (code, name, len(name), LONGEST_INT_NAME), line=number)
        if name in EDITOR_COMMANDS:
            what, words = "a command of the Nextion Editor", "Conflict with instructions name"
        elif name in EDITOR_SYSTEM_VARIABLES:
            what, words = "a system variable", "Illegal name"
        elif name in EDITOR_COLOURS:
            what, words = "a colour", "Illegal name"
        elif name in pages:
            what, words = "a page", "Conflict with page name"
        else:
            owner = next((page for page, known in pages.items()
                          if known is not None and name in known), None)
            if owner is None:
                continue
            what, words = "a component of page %s" % owner, "Conflict with Component name"
        raise NxwrightError("%s: %s is %s, and the Nextion Editor refuses that name for an "
                            "int (\"%s\")" % (code, name, what, words), line=number)


def check_int_declaration(code: str, number: int):
    """Raises NxwrightError for an int declaration of program.nx that is
    malformed (_check_declaration_form), or whose starting value is not a
    number the Nextion Editor accepts (_check_starting_values). The build
    and the test runner both check a declaration with it."""
    _check_declaration_form(code, number)
    _check_starting_values(code, number)


def _check_declaration_form(code: str, number: int):
    """Raises NxwrightError for a malformed int declaration, such as `int a b`,
    `int a=1,5`, `int a=1,`, or `int` alone. A well-formed declaration lists
    its variables separated by commas, and each variable is a name that can
    be followed by "=" and a starting value.

    The Nextion Editor 1.68.2 rejected `int a=1,5` ("First character of a
    Name can not be number"), `int a=1,` and `int a=1,,b=2` ("Illegal global
    variable name length"), and `int` alone ("Invalid command"). It
    compiled `int a b`, but code could then read neither `a` nor `ab`, so
    the build rejects that line too."""
    part = malformed_int_part(code)
    if part is not None:
        raise NxwrightError("%s: %s. An int line lists variables separated by commas, as in "
                            "int a=1,b"
                            % (code, '"%s" is not a variable' % part if part
                               else "a variable is missing"), line=number)


def _check_starting_values(code: str, number: int):
    """Raises NxwrightError for an int declaration of program.nx whose
    starting value is not a whole number from -2147483648 to 2147483647,
    written in decimal, with or without a sign right before it.

    The Nextion Editor 1.68.2 compiled a decimal number in the range, with
    or without leading zeros. It rejected every other starting value tried:
    a number outside the range, a hexadecimal number, a sign followed by a
    space, another variable, arithmetic, a number with a fraction, a text,
    and nothing after the "=". Its message was always the one in
    _INITIAL_VALUE_WORDS. In the build, _check_hex reports a hexadecimal
    number before this check runs."""
    for name, value in declared_ints(code):
        if value is None:
            continue
        if _SPACED_SIGN_START.fullmatch(value):
            raise NxwrightError("%s: the starting value of %s has a space after its sign. The "
                                "Nextion Editor rejects it (\"%s\")"
                                % (code, name, _INITIAL_VALUE_WORDS), line=number)
        decimal = _DECIMAL_START.fullmatch(value)
        if decimal is None:
            raise NxwrightError("%s: the starting value of %s must be a whole number, written "
                                "in decimal. The Nextion Editor rejects anything else (\"%s\")"
                                % (code, name, _INITIAL_VALUE_WORDS), line=number)
        value = int(decimal[1] + decimal[2])
        if value != int32(value):
            raise NxwrightError("%s: %s starts at %d, which does not fit in 32 bits "
                                "(-2147483648 to 2147483647). The Nextion Editor rejects it "
                                "(\"%s\")" % (code, name, value, _INITIAL_VALUE_WORDS),
                                line=number)


def _refuse_declaration_outside_program(code: str, objects: ObjectNames, number: int):
    """Raises NxwrightError for an int declaration in an event, or in a
    macro when `objects` has no page. An int is a variable every page
    shares, which the Nextion Editor takes in program.s alone. The Nextion
    Editor's message differs between an event and a macro."""
    where, words = (("a macro", "Global variable definitions must precede all code in the "
                                "program") if objects.page is None else
                    ("an event", "Global variable definitions must precede all code in the "
                                 "program.c"))
    raise NxwrightError("%s: an int is a variable every page shares, so declare it in "
                        "program.nx. The Nextion Editor refuses an int in %s (\"%s\")"
                        % (code, where, words), line=number)


def check_program_declarations(lines: list):
    """Raises NxwrightError for an int declaration among program.nx's
    `lines`, as (line number, code), that the Nextion Editor refuses: one declaring
    a name declared already, letter case included, and one after a line of
    other code. A line of only a comment is not code: `nxwright new` writes
    comments before its int line."""
    declared, first_code = {}, None
    for number, code in lines:
        if not is_declaration(code):
            if code and first_code is None:
                first_code = number
            continue
        if first_code is not None:
            raise NxwrightError("%s: an int goes before program.nx's other code, so move it "
                                "above line %d. The Nextion Editor refuses an int after other "
                                "code (\"Global variable definitions must precede all code in "
                                "the program\")" % (code, first_code), line=number)
        for name in declared_int_names(code):
            if name in declared:
                raise NxwrightError("%s: %s is declared already, on line %d, and the Nextion "
                                    "Editor refuses a name declared twice (\"Repeated "
                                    "definition global variable name\")"
                                    % (code, name, declared[name]), line=number)
            declared[name] = number


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
        named = page in pages or _page_having(page, pages) is not None
    if named:
        raise NxwrightError("%s: program.nx belongs to no page, so %s takes a component's "
                            "number, or a variable that contains it. The Nextion Editor "
                            "refuses a page's or a component's name there (\"Invalid "
                            "Component ID\")" % (code, command[1]), line=number)


def _check_components(code: str, objects: ObjectNames, variables: frozenset,
                      program_pages: dict, number: int):
    """Raises NxwrightError for a command's component (COMPONENT_PLACES) that
    the Nextion Editor refused as it compiled ("Invalid Component ID").

    In a page's event, the Nextion Editor refused:
      - a component's txt, as `vis t0.txt,0`;
      - a name that is neither on the page nor a variable, as `vis zz,0`
        and `move zz,...`.
    It compiled a variable in an event, as `vis sys0,0`.

    program.nx belongs to no page. In program.nx, the Nextion Editor refused:
      - a component reached through the screen's arrays, as `vis b[1],0`,
        `vis p[0].b[1],0`, and `cfgpio 1,1,b[1]`;
      - a name that is not a variable, as `ref zz` and `move t0,...`.
    _check_program_names refuses a page's or a component's name in
    program.nx first, for the commands it knows.

    A variable is an int of program.nx (`variables`), a system variable, or
    a colour. When `variables` is None, as for nxlang, a name is not
    checked: nxlang's compiler checks names itself. Macros have their own
    rules (_check_macro_references)."""
    word = command_word(code)
    places = COMPONENT_PLACES.get(word)
    in_program = program_pages is not None
    in_event = not in_program and objects is not None and objects.page is not None
    if places is None or not (in_program or in_event):
        return
    known = None if variables is None else (
        variables | EDITOR_SYSTEM_VARIABLES | frozenset(EDITOR_COLOURS)
        | frozenset(EDITOR_PROGRAM_VARIABLES))
    arguments = command_arguments(code[len(word) + 1:])
    for place in places:
        if place >= len(arguments):
            continue
        component = arguments[place].strip()
        if in_event and _TXT.fullmatch(component):
            raise NxwrightError("%s: %s is a text, and the Nextion Editor refuses it as %s's "
                                "component (\"%s\")"
                                % (code, component, word, INVALID_COMPONENT_ID), line=number)
        if in_program and SCREEN_ARRAY.fullmatch(component):
            raise NxwrightError("%s: program.nx belongs to no page, so %s does not reach a "
                                "component in program.nx. Give the component's number, or a "
                                "variable that contains it (\"%s\")"
                                % (code, component, INVALID_COMPONENT_ID), line=number)
        if (_NAME_ONLY.fullmatch(component) and known is not None and component not in known
                and not (in_event and component in objects.own)):
            what = ("%s is neither a component of this page nor a variable" % component
                    if in_event else "program.nx belongs to no page, and %s is not a variable"
                    % component)
            raise NxwrightError("%s: %s, so the Nextion Editor refuses it as %s's component "
                                "(\"%s\")" % (code, what, word, INVALID_COMPONENT_ID),
                                line=number)


def _check_number_arguments(code: str, number: int):
    """Raises NxwrightError for a command's argument in one of its number
    places (NUMBER_PLACES) that the Nextion Editor refused as it compiled:
      - a quoted text or a component's txt, as `cls t0.txt` ("Invalid
        variable operation");
      - an operand it does not read, as `cls 5a`, `cls 1_000`, `cls -a`,
        or `cls RED+*1` ("Invalid Variables"), as in an assignment's value
        (code_lines.chain_parts)."""
    word = command_word(code)
    places = NUMBER_PLACES.get(word)
    if places is None:
        return
    arguments = command_arguments(code[len(word) + 1:])
    for place in places:
        if place >= len(arguments):
            continue
        argument = arguments[place].strip()
        quoted = STRING.fullmatch(argument) is not None
        if _TXT.fullmatch(argument) or quoted:
            raise NxwrightError("%s: %s is a text, where %s takes a number, and the Nextion "
                                "Editor refuses it (\"%s\")"
                                % (code, argument, word, INVALID_VARIABLE_OPERATION),
                                line=number)
        if not quoted and chain_parts(argument) is None:
            raise NxwrightError("%s: the Nextion Editor does not read %s as a number, or as "
                                "numbers joined by operators (\"%s\")"
                                % (code, argument, INVALID_VARIABLES), line=number)


def _check_one_operand_arguments(code: str, number: int):
    """Raises NxwrightError when a command is given an expression in an
    argument that takes a single value (ONE_OPERAND_PLACES), as in
    `getv sys0+1` or `spstr t0.txt,t0.txt,"a"+"b",0`, or a minus before a
    name, as in `getv -sys0` or `getv -RED`. The Nextion Editor refused
    such lines as it compiled ("Invalid Variables"). The message's
    advice depends on whether the command reads the argument, puts its
    result in it, or is undocumented."""
    word = command_word(code)
    if word not in ONE_OPERAND_PLACES and word not in ONE_OPERAND_EVERYWHERE:
        return
    arguments = command_arguments(code[len(word) + 1:])
    places = (range(len(arguments)) if word in ONE_OPERAND_EVERYWHERE
              else ONE_OPERAND_PLACES[word])
    for place in places:
        if place >= len(arguments):
            continue
        argument = arguments[place].strip()
        parts = chain_parts(argument)
        joined = parts is not None and len(parts) > 1
        # chain_parts cannot read a minus before a name, so this looks for one separately.
        if not joined and not _has_minus_before_a_name(argument):
            continue
        if place in READ_ONE_OPERAND_PLACES.get(word, ()):
            advice = "Put the expression in a variable first, then give that variable."
        elif place in _WRITTEN_ONE_OPERAND_PLACES.get(word, ()):
            advice = "Give the variable that is to take the result."
        else:
            advice = "Give a single value."
        raise NxwrightError("%s: %s takes a single value here, such as a number, a text, or an "
                            "attribute, not the expression %s. %s The Nextion Editor refuses "
                            "this line (\"%s\")"
                            % (code, word, argument, advice, INVALID_VARIABLES), line=number)


def _check_page_argument(code: str, pages, variables: frozenset, number: int):
    """Raises NxwrightError for an argument of `page` that the Nextion
    Editor refused when it compiled ("Invalid Page ID"):
      - a quoted text, as in `page "page0"`. `page` takes a page's name
        without quotes, or its number. nxlang does not read a quoted text
        as a page's name either.
      - a name alone that `page` does not take (refused_page_name), as in
        `page zz`.
    `pages` contains the folder's pages, by name. If it is None, the pages
    are not known, and no name is checked. `variables` contains
    program.nx's ints. It is None in nxlang, whose compiler checks the
    names itself (nxlang.py)."""
    if command_word(code) != "page":
        return
    argument = code[len("page"):].strip()
    if STRING.fullmatch(argument):
        raise NxwrightError("%s: page takes a page's name without quotes, or its number, and "
                            "the Nextion Editor refuses a text (\"%s\")"
                            % (code, INVALID_PAGE_ID), line=number)
    if pages is None or variables is None:
        return
    known = (variables | EDITOR_SYSTEM_VARIABLES | frozenset(EDITOR_COLOURS)
             | frozenset(EDITOR_PROGRAM_VARIABLES))
    name = refused_page_name(argument, pages, known.__contains__)
    if name is not None:
        raise NxwrightError(page_name_refusal(code, name, pages, "an int variable, a system "
                                              "variable, or a colour"), line=number)


def refused_page_name(argument: str, pages, is_value):
    """Returns the first name alone in `argument`, the argument of a `page`
    command, that the Nextion Editor refused when it compiled ("Invalid Page
    ID:" followed by the name). Returns None if it took every name. A name
    alone is a name that stands by itself, such as `zz` in `page sys0+zz`.
    The `n0` and the `val` of `n0.val` are not names alone, nor is the `b`
    of `b[2]`.

    `page` takes a page's name, one of `pages`, as its whole argument. Any
    other argument is a value, read the same way as the right side of an
    assignment. A name alone in a value must be one that `is_value(name)`
    accepts: an int variable, a system variable, or a colour, and in nxlang
    also a constant or a local. The Nextion Editor therefore refused:
      - a name that is not defined, as in `page zz` and `page sys0+zz`;
      - a component's name, as in `page t0`;
      - a page's name in an expression, as in `page page1+1`;
      - a page's name in another letter case, as in `page PAGE1`."""
    if argument in pages:
        return None
    for part in STRING.split(argument)[::2]:
        for name in _NAME_ALONE.findall(part):
            if not is_value(name):
                return name
    return None


def page_name_refusal(code: str, name: str, pages, values: str) -> str:
    """Returns the error message for `name`, a name that `page` does not
    take in the line `code` (refused_page_name). `values` lists the kinds of
    name that give a value in `page`'s argument, such as "an int variable, a
    system variable, or a colour"."""
    if name in pages:
        words = "%s is a page's name, which must be the whole argument of page" % name
    else:
        written = next((page for page in pages if page.lower() == name.lower()), None)
        words = ("no page is named %s, though one is named %s" % (name, written) if written
                 else "%s is not a page, %s" % (name, values))
    return "%s: %s. The Nextion Editor refuses this line (\"%s\")" % (code, words,
                                                                   INVALID_PAGE_ID)


def _check_program_attributes(code: str, pages: dict, globals_: dict, number: int):
    """Raises NxwrightError when a line of program.nx names a component's
    attribute in a way the Nextion Editor refuses. program.s belongs to no
    page, so a component's attribute there needs its page's name, as
    `page0.n2.val`, and the component must be of global scope. Two kinds
    of line are refused:
      - an attribute named without its page, as `n0.val`;
      - an attribute of a component of local scope, even with its page's
        name, as `page0.n0.val`.
    `pages` contains each page's objects, by page name, as
    ObjectNames.pages does. `globals_` contains each page's components of
    global scope. A page's entry is None or missing when its components
    are unknown. The Nextion Editor's words are in _program_refusal_words.

    nxlang does not add the page's name itself. program.nx is compiled
    apart from the pages' components, and a name may belong to several
    pages."""
    for part in STRING.split(code)[::2]:
        for first, second, third in _DOTTED.findall(part):
            if first in pages:
                known, reachable = pages[first], globals_.get(first)
                if (third and known is not None and second in known and reachable is not None
                        and second not in reachable):
                    raise NxwrightError("%s.%s.%s: %s is of local scope, and program.nx can use "
                                        "only a component of global scope. The Nextion Editor "
                                        "refuses this line%s"
                                        % (first, second, third, second,
                                           _program_refusal_words(code, local=True)),
                                        line=number)
                continue
            page = _page_having(first, pages, globals_)
            if page is None:
                continue
            words = _program_refusal_words(code, local=False)
            reachable = globals_.get(page)
            if reachable is not None and first not in reachable:
                # Adding the page's name would not help, because no page
                # has the component of global scope.
                raise NxwrightError("%s.%s: %s is of local scope, and program.nx can use only a "
                                    "component of global scope, with its page's name. The "
                                    "Nextion Editor refuses this line%s"
                                    % (first, second, first, words), line=number)
            raise NxwrightError("%s.%s: in program.nx, a component needs its page's name, as "
                                "in %s.%s.%s, because program.nx belongs to no page. The "
                                "Nextion Editor refuses this line%s"
                                % (first, second, page, first, second, words), line=number)


def _program_refusal_words(code: str, local: bool) -> str:
    """Returns the Nextion Editor's words, as ' ("Invalid Variables")', for
    refusing the line of program.nx `code` that uses a component's
    attribute: of `local` scope with its page's name, or else without its
    page's name. Returns "" for a line of a form the Nextion Editor was not
    seen to refuse.

    On the T series, the Nextion Editor said "Invalid Variables" for both
    kinds in an assignment,
    as `sys0=n0.val`. Without the page's name, it said "Invalid Page ID"
    for `page n0.val`, and "Invalid Component ID" for `vis n0.val,0` and
    `tsw n0.val,1`."""
    if _ASSIGNMENT_LINE.fullmatch(code):
        return ' ("Invalid Variables")'
    if local:
        return ""
    if code.startswith("page "):
        return ' ("Invalid Page ID")'
    if re.match(r"(vis|tsw) ", code):
        return ' ("Invalid Component ID")'
    return ""


def _page_having(name: str, pages: dict, globals_: dict = None):
    """Returns the name of a page, in `pages`' order, that has a component
    named `name`, or None. `pages` holds each page's objects, by page name,
    None for a page whose objects are unknown. With `globals_`, each page's
    components of global scope, a page where the component is of global
    scope comes first, as program.nx reaches it there."""
    having = [page for page, known in pages.items() if known is not None and name in known]
    reached = [page for page in having if name in ((globals_ or {}).get(page) or ())]
    return (reached or having or [None])[0]


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
    argument is arithmetic, which the Editor refuses as it compiles. A
    minus before a name counts as arithmetic: the Nextion Editor refused
    `print -sys0` and `print -RED` ("Invalid Variables"), and compiled
    `print -5`."""
    word = command_word(code)
    if word not in ONE_OPERAND_FIRST:
        return
    first = ARGUMENT.match(code[len(word):].strip())
    if first is None or is_one_operand(first[0]):
        return
    if _has_minus_before_a_name(first[0]):
        raise NxwrightError("%s: the Nextion Editor takes only a single text or number as the "
                            "first argument of %s, and it refuses a minus before a name there "
                            "(\"%s\")" % (code, word, INVALID_VARIABLES), line=number)
    raise NxwrightError("%s: the Nextion Editor takes only a single text or number as the "
                        "first argument of %s, not arithmetic or joined texts" % (code, word),
                        line=number)


def is_one_operand(text: str) -> bool:
    """Whether `text` is one operand alone: a text, a number, or a name,
    which may be dotted, as the Editor takes where it refuses arithmetic
    and texts joined (_ONE_OPERAND). A minus before a number is part of
    the number. A minus before a name is not one operand, as the Nextion
    Editor refused it in such places."""
    return _ONE_OPERAND.fullmatch(text.strip()) is not None and not _has_minus_before_a_name(text)


def _has_minus_before_a_name(text: str) -> bool:
    """Whether `text`, a command's argument, has a minus that is the sign
    of a name, as in `-sys0`, `-RED`, or `1+-sys0`. Where a command takes a
    single value, the Nextion Editor refused each of these ("Invalid
    Variables"), though it took a minus before a number, as in `getv -5`.
    A minus right after an operand subtracts, as in `sys0-sys1`, and one
    inside a quoted text is part of the text."""
    text = STRING.sub('""', text.strip())
    return any(minus_is_sign(text[:minus.start()])
               for minus in _MINUS_BEFORE_A_NAME.finditer(text))


def _check_xstr_text(code: str, number: int):
    """Raises NxwrightError for an xstr whose text, its last argument, is
    more than one operand, as texts joined or arithmetic. The Editor
    refused `"a"+"b"`, `t0.txt+"b"`, `"a"+t0.txt+"c"`, `sys0+1`, and
    `n0.val*2` there as it compiled ("Invalid Variables"), and a minus
    before a name, as in `-sys0` and `-RED`. It compiled one
    operand alone, as a text, a txt, a number, or a variable. An xstr of
    another number of arguments is refused by _check_parameter_count."""
    if command_word(code) != "xstr":
        return
    arguments = command_arguments(code[len("xstr"):].strip())
    if len(arguments) == COMMAND_PARAMETERS["xstr"] and not is_one_operand(arguments[-1]):
        raise NxwrightError("%s: the text of xstr must be a single value: a text, a txt, a "
                            "number, or a variable. The Nextion Editor refuses joined "
                            "texts, arithmetic, and a minus before a name here (\"%s\")"
                            % (code, INVALID_VARIABLES), line=number)


def _check_nxlang_word(code: str, number: int):
    """Raises NxwrightError for a line that starts with a word only nxlang
    has. `nxwright language` stops on such a line, so the error says to take
    it out before switching."""
    word = first_word(code) or code.split(" ", 1)[0].split("(", 1)[0]
    if word in _NXLANG_WORDS:
        raise NxwrightError("%s: %s is part of nxlang, but this folder uses strict Nextion "
                            "syntax. To switch to nxlang, take out the lines that already use it, "
                            "run nxwright language <source-folder> nxlang, then put them back"
                            % (code, word), line=number)


def _check_first_word(code: str, number: int, suggest_nxlang: bool = False):
    """Raises NxwrightError for a line whose first word is not a Nextion Editor
    command. The error quotes the words the Nextion Editor refuses the line
    with as it compiles (first_word_refusal). If `suggest_nxlang` is true and
    only nxlang has that word, the error says how to switch instead."""
    refusal = first_word_refusal(code)
    if refusal is None:
        return
    if suggest_nxlang:
        _check_nxlang_word(code, number)
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
    command the table lacks takes any number."""
    word = first_word(code)
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
    for text in _condition_texts(code):
        if ends_in_escaped_backslash(text):
            raise NxwrightError("%s: the Nextion Editor refuses a text that ends in an escaped "
                                "backslash in a condition (\"SYNTAX ERROR\")" % code,
                                line=number)


# The encodings in which the Nextion Editor reads every text in code in
# pairs of bytes: from the opening quote, a byte from 0x81 up takes the byte
# after it, as the first byte of a character of two, and so does a
# backslash's. The first quote left ends the text. In shift-jis, a
# half-width katakana, one byte from 0xA1 to 0xDF, then takes the byte
# after it too (ResearchNotes/tft/encodings.md).
_PAIRED_ENCODINGS = frozenset({"gb2312", "big5", "shift-jis"})
_BACKSLASH_BYTE, _QUOTE_BYTE = 0x5C, 0x22
# The commands among whose arguments the Nextion Editor reads a text before
# a comma byte by byte (_check_texts_byte_by_byte), as it refused `prints
# "日表",0` in shift-jis. Other commands no probe tried.
TEXTS_READ_BYTE_BY_BYTE = frozenset({"prints", "spstr", "strlen", "btlen", "crcputs"})


def _check_texts_in_pairs(code: str, codec, number: int):
    """Raises NxwrightError for a quoted text of the line that the Nextion
    Editor, reading it in pairs of bytes in `codec`'s encoding, ends
    elsewhere than at its closing quote: in shift-jis, one with a half-width
    katakana that takes the closing quote, as in `t0.txt="aｱ"`. It refused
    such lines as it compiled. A data record's call is left to the Nextion
    Editor, as no probe tried one."""
    if codec.name not in _PAIRED_ENCODINGS or DATA_RECORD_CALL.match(code):
        return
    for text in STRING.findall(code):
        stored = _stored_text(text, codec)
        if stored is not None and _reading_in_pairs(stored)[-1] != len(stored) - 1:
            katakana = _katakana_read_with_the_next_byte(text, codec)
            raise NxwrightError("%s: the Nextion Editor reads this text in pairs of bytes. The "
                                "half-width katakana %s is a single byte, so it gets paired "
                                "with the next byte, and the closing quote ends up inside the "
                                "text (\"Invalid "
                                "Variables\"). Put another character after the katakana, or "
                                "write the text another way." % (code, katakana), line=number)


def _reading_in_pairs(stored: bytes) -> list:
    """Returns where the Nextion Editor's reading in pairs of bytes of the
    quoted text `stored`, its bytes with its quotes, starts each character
    it reads, then where it ends the text: the place of the first quote it
    does not take as a second byte."""
    places = [1]
    while places[-1] < len(stored) and stored[places[-1]] != _QUOTE_BYTE:
        taken = stored[places[-1]] >= 0x81 or stored[places[-1]] == _BACKSLASH_BYTE
        places.append(places[-1] + (2 if taken else 1))
    return places


def _katakana_read_with_the_next_byte(text: str, codec) -> str:
    """Returns the half-width katakana of the quoted text `text` that the
    reading in pairs (_reading_in_pairs) last takes as the first of two
    bytes: putting a character after it ends the misreading. In `"ｱｲ日ｳ"`,
    ｱ and ｲ read as a pair, and 日 as one character, so ｳ takes the closing
    quote. The text's last character when none is."""
    # Each one-byte character past ASCII, by the place of its byte.
    katakana, place = {}, 1
    for character in text[1:-1]:
        size = len(_stored_text(character, codec) or b"")
        if size == 1 and ord(character) > 0x7F:
            katakana[place] = character
        place += size
    read = [katakana[start] for start in _reading_in_pairs(_stored_text(text, codec))[:-1]
            if start in katakana]
    return read[-1] if read else text[-2]


def _check_texts_byte_by_byte(code: str, codec, number: int):
    """Raises NxwrightError for a quoted text in a condition, or before a
    comma among the arguments of TEXTS_READ_BYTE_BY_BYTE's commands, that
    the Nextion Editor's reading byte by byte ends elsewhere than at its
    closing quote. There each 0x5C byte escapes the byte after it, so a
    character whose last byte is 0x5C, as shift-jis's 表, escapes the
    closing quote. It refused such lines as it compiled ("Invalid number of
    arguments")."""
    for text in _condition_texts(code) + _texts_before_commas(code):
        if not misread_byte_by_byte(text, codec):
            continue
        # The misreading starts at a character of more than one byte that
        # ends in 0x5C: in `"a表\\"`, 表's 0x5C escapes the first backslash,
        # and the second escapes the quote. The last such character is given.
        escaping = next((character for character in reversed(text[1:-1])
                         if len(_stored_text(character, codec) or b"") > 1
                         and _stored_text(character, codec)[-1] == _BACKSLASH_BYTE), text[-2])
        raise NxwrightError("%s: %s ends in the byte 0x5C, which the Nextion Editor reads as a "
                            "backslash before the closing quote (\"Invalid number of "
                            "arguments\"). Put the text in a variable first, and use the "
                            "variable here." % (code, escaping), line=number)


def misread_byte_by_byte(text: str, codec) -> bool:
    """Whether the Nextion Editor's reading byte by byte ends the quoted
    text `text`, its quotes included, elsewhere than at its closing quote,
    in `codec`'s encoding (_check_texts_byte_by_byte). False without a
    codec, for a text the encoding cannot store, and for anything but one
    quoted text, such as a name or an expression."""
    if codec is None or not STRING.fullmatch(text):
        return False
    stored = _stored_text(text, codec)
    return stored is not None and _end_byte_by_byte(stored) != len(stored) - 1


def _end_byte_by_byte(stored: bytes) -> int:
    """Returns where the Nextion Editor's reading byte by byte ends the
    quoted text `stored`, its bytes with its quotes: the place of the first
    quote that no 0x5C byte escapes."""
    place = 1
    while place < len(stored) and stored[place] != _QUOTE_BYTE:
        place += 2 if stored[place] == _BACKSLASH_BYTE else 1
    return place


def _condition_texts(code: str) -> list:
    """Returns the quoted texts of a line's condition: the head of an if, an
    else if, or a while, or the middle part of a for's head, as
    _check_condition_texts finds them. [] for another line."""
    head, otherwise = _BLOCK_HEAD.match(code), ELSE.match(code)
    if not (head or (otherwise and otherwise[2])):
        return []
    in_for = head is not None and head[1] == "for"
    # A for's parts are apart at the semicolons outside its texts.
    found, semicolons, after = [], 0, 0
    for text in STRING.finditer(code):
        semicolons += code.count(";", after, text.start())
        after = text.end()
        if not in_for or semicolons == 1:
            found.append(text[0])
    return found


def _texts_before_commas(code: str) -> list:
    """Returns the quoted texts given as arguments other than the last to a
    command of TEXTS_READ_BYTE_BY_BYTE, as `"日表"` in `prints "日表",0`."""
    word = command_word(code)
    if word not in TEXTS_READ_BYTE_BY_BYTE:
        return []
    arguments = [argument.strip() for argument in command_arguments(code[len(word) + 1:])]
    return [argument for argument in arguments[:-1] if STRING.fullmatch(argument)]


def _stored_text(text: str, codec):
    """Returns `text` as the bytes it is stored as in `codec`'s encoding, or
    None when the encoding cannot store it, which the build refuses
    elsewhere."""
    try:
        return codec.encode(text, "")
    except NxwrightError:
        return None


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
