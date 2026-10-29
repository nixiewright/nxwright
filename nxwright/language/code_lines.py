"""The parts of one line of code, which the build, its checks, and the code
editor's tools read.

split_line splits a line into its indentation, its code, and its comment.
command_word and first_word give the command a line starts, and
command_arguments that command's arguments. goto_label gives the label a
goto jumps to, and LABEL matches a label line. declared_int_names and
program_int_variables give the names that `int` lines declare.
OWN_ATTRIBUTE matches an attribute of the object whose event holds the
line, written '&name&'. OWN_FORM matches any form '&...&', and
forms_without_spaces drops the spaces inside one.
compact puts a line's code part in the Nextion Editor's syntax, as
code_preprocessor.py's rules say. ASSIGNMENT matches an assignment in that
syntax, and chain_parts reads its value: the build checks it with them, and
the test runner computes it.

Strings ("...") never change: outside_strings changes only what lies
outside them.
"""
import re

from nxwright import NxwrightError

# Words a line can start with that are not commands. There is no list of
# commands: any other first word followed by a space, and not by an assignment,
# starts one. So a command nxwright does not know still keeps its spaces.
_NOT_COMMANDS = frozenset({"if", "while", "for", "else", "int"})
ELSE = re.compile(r"(\}?)\s*else\b(\s+if\b)?")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ASSIGNMENT = re.compile(r"(\+\+|--|[-+*/%&|^]?=(?!=))")
STRING = re.compile(r'("(?:\\.|[^"\\])*")')
# A name an int line declares: "int a=0,b" declares a and b.
_DECLARED_NAME = re.compile(r"(?:^int|,)\s*([A-Za-z_][A-Za-z0-9_]*)")
# The end of an operand, after which a "-" subtracts (minus_is_sign).
_OPERAND_END = re.compile(r"[\w\])\"]$")
# A label line, which a goto jumps to: a name, then a colon (the vendor's
# instruction set). As the Editor compiled them, a label may hold any
# character but those below, and may not start with a digit: it refused a
# first digit, and + - * / % = , . [ ] & ' \ ("the make is invalid"). A
# later probe found it refused " too, and compiled { and }, even first,
# which the build refuses all the same (code_checks.check_labels).
_NOT_IN_A_LABEL = r"\s:+\-*/%=,.\[\]&'\\\""
LABEL = re.compile(r"([^%s0-9][^%s]*):" % (_NOT_IN_A_LABEL, _NOT_IN_A_LABEL))
# An attribute of the object whose event holds the line, as '&val&' (the
# vendor's instruction set, section 9). The Editor replaces the text before
# it compiles, in a quoted text too (code_preprocessor.with_own_attributes),
# and refuses it in code of no event. A lone '& it keeps as written. The
# name is an attribute's: letters, digits, and _, not starting with a digit.
# (Worked out from the Editor 1.68.2.)
OWN_ATTRIBUTE = re.compile(r"'&([A-Za-z_][A-Za-z0-9_]*)&'")
# Any form '&...&', whose name the Editor reads with its spaces dropped. One
# whose name is no attribute's, as '&1a&' or '&a-b&', it refused as it
# compiled ("Invalid Variables").
OWN_FORM = re.compile(r"'&([^&']+)&'")
# An argument of a call: up to a comma outside its strings.
ARGUMENT = re.compile(r'(?:"(?:\\.|[^"\\])*"|[^,"])+')
# A number as code writes it: in decimal, or in hexadecimal, as 0x1234 or
# 0X1234, which the Nextion Editor compiled and ran alike.
NUMBER = r"-?0[xX][0-9A-Fa-f]+|-?[0-9]+"
# An operand of a chain: a number, a quoted text, or a name, which may be
# dotted and indexed, as n0.val or b[1].val.
OPERAND = (NUMBER + r'|"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?'
           r'(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?)*')
# An assignment in the Nextion Editor's syntax: its target, its operator, =
# or a compound one such as +=, and its value.
ASSIGNMENT = re.compile(r"^(%s)(<<=|>>=|[-+*/%%&|^]?=)(.*)$" % OPERAND)
_CHAIN_OPERAND = re.compile(OPERAND)
_CHAIN_OPERATOR = re.compile(r"<<|>>|[-+*/%&|^]")
# A command's comma or operator, with the spaces by it (_drop_spaces_by_separators).
_SPACED_SEPARATOR = re.compile(r"[ \t]*(,|<<|>>|[-+*/%&|^])[ \t]*")


def chain_parts(chain: str):
    """Returns the operands of `chain`, a value in the Nextion Editor's
    syntax such as `n0.val*2+1`, with the operators between them:
    [operand, operator, operand, ...]. Returns None when it does not read as
    operands joined by operators, as `2+` and `(1+2)` do not, which the
    Nextion Editor refuses. A "-" right after an operator starts a negative
    number, as in `2*-16`, but not a negative name, as in `2*-n0.val`, which
    the Nextion Editor refuses too."""
    parts, position = [], 0
    while True:
        operand = _CHAIN_OPERAND.match(chain, position)
        if not operand:
            return None
        parts.append(operand[0])
        if operand.end() == len(chain):
            return parts
        operator = _CHAIN_OPERATOR.match(chain, operand.end())
        if not operator:
            return None
        parts.append(operator[0])
        position = operator.end()


def command_arguments(text: str) -> list:
    """Returns the arguments of a command, `text` being what follows its
    name: split at the commas outside its strings, so that `"a,b"+t0.txt`
    is one."""
    return ARGUMENT.findall(text)


def forms_without_spaces(code: str) -> str:
    """Returns `code` with the spaces and tabs inside each form '&...&' outside
    its quoted texts dropped, as the Editor drops a line's spaces before it
    reads the form: '& val &' is '&val&'."""
    return outside_strings(code, lambda part: OWN_FORM.sub(
        lambda form: "'&%s&'" % re.sub(r"\s", "", form[1]), part))


def holds_own_attribute(code: str) -> bool:
    """Returns whether `code` uses the form '&name&' outside its quoted texts."""
    return any(OWN_ATTRIBUTE.search(part) for part in STRING.split(code)[::2])


def goto_label(code: str):
    """Returns the label a goto line's code jumps to, or None for another line."""
    return code[len("goto "):] if code.startswith("goto ") else None


def minus_is_sign(before: str) -> bool:
    """Whether a "-" right after `before`, the code before it, is a sign
    rather than a subtraction. After an operand, such as the 5 of 5-0x10,
    it subtracts; after an operator, "=", ",", or nothing, it is a sign."""
    return not _OPERAND_END.search(before.rstrip())


def is_declaration(code: str) -> bool:
    return code == "int" or code.startswith("int ")


def declared_int_names(code: str) -> list:
    """Returns the names that a line's `code`, its comment left out,
    declares when it is an `int` line: `int a=0,b` declares a and b. Any
    other line declares none. A tab after `int` is read too, so that its
    names are known though the build refuses the line
    (code_preprocessor.preprocess): the refusal then lands on the
    declaration, not on a line using the name."""
    return _DECLARED_NAME.findall(code) if re.match(r"int\b", code) else []


def program_int_variables(text: str) -> frozenset:
    """Returns the names that program.nx's `text` declares on its `int`
    lines, read by declared_int_names, without nxlang's rules for names."""
    return frozenset(name for number, line in enumerate(text.split("\n"), 1)
                     for name in declared_int_names(split_line(line, number)[1]))


def split_line(text: str, number: int) -> tuple:
    """Returns (indentation, code, comment) of one line. The comment is the "//"
    comment with the spaces before it; without one, the spaces and tabs ending
    the line, or "". Raises NxwrightError naming line `number` when a string
    is not closed."""
    indent = text[:len(text) - len(text.lstrip(" \t"))]
    rest = text[len(indent):]
    in_string = False
    position = 0
    while position < len(rest):
        char = rest[position]
        if in_string:
            if char == "\\":
                position += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif rest.startswith("//", position):
            code = rest[:position].rstrip(" \t")
            return indent, code, rest[len(code):]
        position += 1
    if in_string:
        raise NxwrightError("a string is not closed", line=number)
    return indent, rest.rstrip(" \t"), rest[len(rest.rstrip(" \t")):]


def command_word(code: str):
    """Returns the command a line's code part starts, as "covx" in
    "covx a,b,0,0", or None when the line is no command (see
    code_preprocessor.py's rules)."""
    word = _WORD.match(code)
    if word and word[0] not in _NOT_COMMANDS:
        after = code[word.end():]
        if after[:1] in (" ", "\t") and not _ASSIGNMENT.match(after.lstrip(" \t")):
            return word[0]
    return None


def first_word(code: str):
    """Returns the word a line's code part starts with as a command: the one
    command_word finds, or the code itself when it is a name alone, as
    "doevents"; None for a line with neither, such as an assignment, a
    label, a brace, or a keyword alone, as "else"."""
    word = command_word(code)
    if word is None and _WORD.fullmatch(code) and code not in _NOT_COMMANDS:
        return code
    return word


def compact(code: str) -> str:
    """Returns one line's code part in Editor syntax."""
    word = command_word(code)
    if word is not None:
        after = code[len(word):]
        return word + " " + outside_strings(after.strip(" \t"), _drop_spaces_by_separators)
    else_match = ELSE.match(code)
    if else_match:
        prefix = else_match[1] + ("else if" if else_match[2] else "else")
        return prefix + outside_strings(code[else_match.end():], _drop_spaces)
    return outside_strings(code, _drop_spaces)


def _drop_spaces(text: str) -> str:
    return text.replace(" ", "").replace("\t", "")


def _drop_spaces_by_separators(text: str) -> str:
    """Drops the spaces by a command's commas and by its arguments'
    operators: the Nextion Editor refused `page appid & 0x000000FF` and
    `vis b0,sys0 + 1`, and compiled them without the spaces. Other spaces
    stay, as those between printh's bytes."""
    return _SPACED_SEPARATOR.sub(r"\1", text)


def outside_strings(code: str, change) -> str:
    """Applies `change` to the parts of `code` outside "..." strings."""
    parts = STRING.split(code)
    return "".join(part if index % 2 else change(part) for index, part in enumerate(parts))
