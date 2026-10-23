"""Editor code coming into a source folder that uses nxlang.

Unlike in most modern computer languages, the Nextion Editor computes arithmetic
strictly from left to right: it reads `a+b*c` as `(a+b)*c`. nxlang follows the
usual precedence (e.g., like C) and reads it as `a+(b*c)` (see nxlang.py). So
when Editor code comes into a folder with code in nxlang, each assignment that
the two would read differently is rewritten with the parentheses that keep the
Editor's meaning. That happens when a folder switches from Editor code to nxlang
code, and when extracting takes an event the Editor changed and writes it into
nxlang code. Compiling the rewritten code when rebuilding a project converts
back to the Editor's code.

The exception is a compound assignment like `x-=a+b`: the Editor computes
`(x-a)+b`, nxlang would compute `x-(a+b)`, so it is rewritten as `x=x-a+b`.
That compiles to `x=x-a+b`, not back to `x-=a+b`. editor_equivalent applies
the same rewrite to the Editor's code, so that extracting can check that the
rewritten events compile to the same thing.

A hexadecimal number written `0X10` is rewritten `0x10` the same way: the
Editor reads the two alike, and nxlang reads only the second.

This module also recognises what the build adds to Editor code: the names of
the generated variables, and the `tsw` lines that turn off the touch of the
functions' hotspots (both described in nxlang.py).
"""
import re

from nxwright import NxwrightError
from nxwright.language.code_lines import outside_strings, split_line
from nxwright.language.nxlang import (COMPOUND_ASSIGNMENTS, GENERATED_ANY, GENERATED_GLOBAL,
                                      HOTSPOT_PREFIX, LEVELS, PRECEDENCE, STRING_LITERAL,
                                      Binary, Literal, NotParsed, OwnAttribute, Parser, Reference,
                                      Unary, kind_of, same_as_editor, tokenize)

_TOUCH_OFF = re.compile(r"tsw (%s[0-9]+),0" % HOTSPOT_PREFIX)
_GLOBAL_DECLARATION = re.compile(r"int {0}=0(,{0}=0)*".format(GENERATED_GLOBAL.pattern))
# A generated name that Editor code uses, not part of a longer name.
_GENERATED_USE = re.compile(r"(?<![\w.])(%s)\b" % GENERATED_ANY.pattern)
# The generated globals are declared this many to a line of program.s.
DECLARATIONS_PER_LINE = 50
# The 0X of a hexadecimal number, not part of a name, as in a0X1.
_HEX_0X = re.compile(r"(?<![\w.])0X(?=[0-9A-Fa-f])")


def global_declarations(names: list) -> list:
    """Returns the lines of program.s that declare the generated globals
    `names`, such as "int __g0_0=0,__g0_1=0"."""
    return ["int " + ",".join(name + "=0" for name in names[start:start + DECLARATIONS_PER_LINE])
            for start in range(0, len(names), DECLARATIONS_PER_LINE)]


def without_global_declarations(lines: list) -> list:
    """Returns the lines of program.s without the declarations of generated
    globals that global_declarations wrote at its start."""
    position = 0
    while position < len(lines) and _GLOBAL_DECLARATION.fullmatch(lines[position]):
        position += 1
    return lines[position:]


def without_touch_off(code: list) -> list:
    """Returns the lines of an event without the `tsw __f0,0` lines that the
    build puts at the start of a page's Preinitialize event."""
    position = 0
    while position < len(code) and _TOUCH_OFF.fullmatch(code[position].strip()):
        position += 1
    return code[position:]


def keep_editor_meaning(lines: list) -> list:
    """Returns lines of Editor code, as (line number, text), rewritten so that
    nxlang reads them as the Editor does: with parentheses where needed,
    `x-=a+b` as `x=x-a+b`, and `0X10` as `0x10`. Other lines come back
    unchanged."""
    out = []
    for number, text in hex_written_0x(lines):
        indent, code, comment = split_line(text, number)
        rewritten = _rewrite_assignment(code, number)
        out.append((number, text if rewritten is None else indent + rewritten + comment))
    return out


def hex_written_0x(lines: list) -> list:
    """Returns lines of Editor code, as (line number, text), with the 0X of
    each hexadecimal number changed to 0x, outside strings and comments.
    This is the one rewrite of keep_editor_meaning that is not about the
    order the two languages compute in."""
    out = []
    for number, text in lines:
        indent, code, comment = split_line(text, number)
        written = _hex_written_0x(code)
        out.append((number, text if written == code else indent + written + comment))
    return out


def _hex_written_0x(code: str) -> str:
    """Returns a line's code with the 0X of each hexadecimal number changed
    to 0x, outside its strings."""
    return outside_strings(code, lambda part: _HEX_0X.sub("0x", part))


def _editor_assignment(code: str, number: int):
    """Returns (target, operator, expression) of an assignment, read from left
    to right as the Editor does, or None for any other line."""
    try:
        tokens = tokenize(code, number)
    except NxwrightError:
        return None
    # The target is a name, or the form '&name&', an attribute of the
    # event's object, written back as it is.
    if not tokens or tokens[0][0] not in ("name", "own"):
        return None
    parser = Parser(tokens, number, left_to_right=True)
    try:
        target = parser.primary()
        operator = parser.peek()
        if not (operator == "=" or operator in COMPOUND_ASSIGNMENTS):
            return None
        parser.take()
        expression = parser.expression()
    except NotParsed:
        return None
    return (target, operator, expression) if parser.at_end() else None


def _rewrite_assignment(code: str, number: int):
    """Returns one line as keep_editor_meaning rewrites it, or None to keep it."""
    assignment = _editor_assignment(code, number)
    if assignment is None:
        return None
    target, operator, expression = assignment
    target_text = write_expression(target)
    if operator == "=":
        rewritten = target_text + "=" + write_expression(expression)
    else:
        chain = _left_to_right_chain(expression)
        try:
            kind = kind_of(target, number)
        except NxwrightError:
            return None
        if len(chain) == 1 or same_as_editor(operator[:-1], chain, kind):
            rewritten = target_text + operator + write_expression(expression)
        else:
            # The Editor applies the compound operator to the first operand
            # only, then the rest of the chain to the result: x-=a+b is (x-a)+b.
            whole = Binary(operator[:-1], target, chain[0][1])
            for item_operator, operand in chain[1:]:
                whole = Binary(item_operator, whole, operand)
            rewritten = target_text + "=" + write_expression(whole)
    return None if rewritten == outside_strings(code, _drop_spaces) else rewritten


def editor_equivalent(code: list) -> list:
    """Returns lines of Editor code with each `x-=a+b` that keep_editor_meaning
    rewrites written as `x=x-a+b`, and each `0X10` as `0x10`, for the check
    the module describes."""
    out = []
    for line in code:
        indent, body, comment = split_line(line, 0)
        hex_0x = _hex_written_0x(body)
        expanded = _expanded_compound(hex_0x)
        if expanded is None and hex_0x != body:
            expanded = hex_0x
        out.append(line if expanded is None else indent + expanded + comment)
    return out


def _expanded_compound(code: str):
    """Returns `x-=a+b` as `x=x-a+b`, or None when the line needs no rewriting."""
    assignment = _editor_assignment(code, 0)
    if assignment is None or assignment[1] == "=":
        return None
    target, operator, expression = assignment
    chain = _left_to_right_chain(expression)
    try:
        if len(chain) == 1 or same_as_editor(operator[:-1], chain, kind_of(target, 0)):
            return None
    except NxwrightError:
        return None
    target_text = write_expression(target)
    if not code.startswith(target_text + operator):
        return None
    return target_text + "=" + target_text + operator[:-1] + code[len(target_text + operator):]


def uses_generated(code: list) -> str:
    """Returns the first name of a generated variable that lines of Editor
    code use, outside strings, or "" when they use none."""
    for line in code:
        for part in STRING_LITERAL.split(line):
            found = _GENERATED_USE.search(part)
            if found:
                return found[1]
    return ""


def _left_to_right_chain(expression) -> list:
    """Returns an expression read from left to right as a list of
    (operator, operand): `a-b+c` gives [(None, a), ("-", b), ("+", c)]."""
    if isinstance(expression, Binary):
        return _left_to_right_chain(expression.left) + [(expression.operator, expression.right)]
    return [(None, expression)]


def write_expression(expression, parent: int = -1, right_side: bool = False) -> str:
    """Returns an expression as nxlang text with only the parentheses it needs.
    `parent` is the precedence of the operator around it, and `right_side`
    whether it is that operator's right operand."""
    if isinstance(expression, (Literal, OwnAttribute)):
        return expression.text
    if isinstance(expression, Reference):
        return ".".join(name if index is None else "%s[%s]" % (name, write_expression(index))
                        for name, index in expression.parts)
    if isinstance(expression, Unary):
        return expression.operator + write_expression(expression.operand, len(LEVELS))
    level = PRECEDENCE[expression.operator]
    right = write_expression(expression.right, level, True)
    if expression.operator == "-" and right.startswith("-"):
        right = "(" + right + ")"   # "a--1" would read as a decrement
    text = write_expression(expression.left, level) + expression.operator + right
    if level < parent or (right_side and level == parent):
        return "(" + text + ")"
    return text


def _drop_spaces(text: str) -> str:
    return text.replace(" ", "").replace("\t", "")
