"""nxlang, the nxwright language, compiled into code the Nextion Editor accepts.

A source folder with `language = "nxlang"` in its app.toml may use, in event code:
  - expressions with the usual precedence and parentheses;
  - `const NAME = <number or text>`, at the top of a page's .nx file (that
    page) or anywhere in program.nx (every page);
  - `var name = <expression>`, a local variable of one event;
  - `!`, and conditions mixing `&&` and `||`;
  - joining a number to text, and a minus before a name;
  - functions of a page, `function name(param: number) -> text:`, with
    their body indented like an event's and, with a result, ending with `return`;
  - `break`, `continue`, and `switch` with `case` and `default`, as in C.
The compiler runs before code_preprocessor.py and hands it lines it accepts.

What the Editor allows, and so what the compiler works around:
  - Arithmetic runs strictly left to right, with no parentheses: `a+b*c` is
    `(a+b)*c`. An expression is turned into such a chain of operators, and a
    part that cannot join the chain is computed first into a hidden variable
    (a temporary).
  - `x-=a+b` computes `(x-a)+b`. nxlang means `x-(a+b)`, so the right side
    is computed first unless both agree.
  - A condition compares plain values. It holds no arithmetic, and it never
    mixes `&&` and `||`. Operands are computed into temporaries first. In a
    condition that mixes the two, each inner `&&` or `||` part is computed
    into a temporary holding 0 or 1.
  - A number cannot be joined to text. It is converted first with covx.
  - `-x` is refused; `0-x` is not.
  - Names are at most 14 bytes (NAME_LIMIT, editor_limits.py), so generated
    names are short and numbered.
  - A hotspot is at least 2 by 2, and `click` runs its Touch Press event
    at once, even with its touch turned off by `tsw`.

A page holds at most 256 objects, so the compiler adds as few as it can.
Every number it needs is an `int` global of program.s, `__g<page>_<n>`,
declared by the build; pages never share one, since changing page runs the
new page's Preinitialize event in the middle of the old page's event. Only
text needs a variable component on the page: `__s0` for temporaries, and
`__v0` for the text that lasts longer: locals, parameters, results, and a
switch's value. Their names start with "__", which the project's own names
may not; one "_" is the project's to use. The code calls the `__v` text
"shared", since events and functions that never run at once share it (see
below).

No event runs in the middle of another except through `click`: a hand-made
one, or a call, which clicks a hotspot. So the compiler knows what may run
during each event or function: the functions it calls and the events its
clicks run, and what those run in turn. A click must name its component and
0 or 1, so the build can tell which event it runs, and calls and clicks
cannot come back to an event or function already running. The code calls an
event or a function an "owner", since it owns a set of variables.

A macro of macros.nx, which `call <name>` runs, is followed the same way:
what may run during it is the macros it calls and the events its clicks
run. A macro is strict Nextion syntax, whose click gives a component's ID,
counted on the page whose code called it. A macro owns no variables, but
counts in a chain as an event does.

An event or function's `__v` variables start just after those of everything
that may run during it, so none of those can change them. Two that never
run at once may share variables, and a page needs as many as its heaviest
chain of calls and clicks.

An event's depth is 0 when nothing runs it, and an event or function's
depth is 1 more than its deepest caller or clicker. Temporaries live only
within one statement, a click being a statement of its own, so the events
and functions of one depth share a pool of temporaries. One that runs
during another always has a greater depth, so the two never share one.

A function's body goes in the Touch Press event of a 2 by 2 hotspot in the
page's top left corner. The page's functions of one depth share a hotspot
(`__f0` for the smallest depth, `__f1` for the next, ...), and its event picks
the body to run by a "which function" global. A call sets the parameters,
then that global, clicks the hotspot, and reads the result. The page's
Preinitialize event turns the hotspots' touch off first.
`click` nests 9 events deep at most, so a chain of calls and clicks holds
at most MOST_CALL_DEPTH of them.

`&&` and `||` evaluate their right side only when needed, as in C. A right
side the Editor can test as it is stays in the condition; one that must be
computed first is reached through nested `if` blocks.

The Editor has no `break`, `continue`, or `switch`. A loop holding a `break`
or `continue` of its own gets a control variable: 0 while a pass runs,
1 after `continue`, 2 after `break`. Its condition tests it first, and code
that could run after a jump in the same pass goes inside `if` blocks
testing it. A `switch` puts its value in a variable of its own, and its cases'
code runs inside `if` blocks testing whether a case matched and whether a
`break` ran, so falling through works as in C. Generated variables keep
their values between runs, so each of these is set when its loop or switch
starts.

Editor code coming into a folder that uses nxlang goes through
editor_code.py, which adds the parentheses that keep its left-to-right
meaning. Compiling the result gives back the Editor's code, except for a
compound assignment such as `x-=a+b` (see editor_code.py).
"""
from contextlib import contextmanager
import copy
from dataclasses import dataclass, field
import re

from nxwright import NxwrightError
from nxwright.language.code_checks import (DATA_RECORD_ARGUMENTS, DATA_RECORD_CALL,
                                           ONE_OPERAND_FIRST, ends_in_escaped_backslash,
                                           is_one_operand, method_count_refusal)
from nxwright.language.code_lines import (LABEL, OWN_ATTRIBUTE, command_word, declared_int_names,
                                          goto_label, minus_is_sign, outside_strings, split_line)
from nxwright.language.code_preprocessor import with_own_attributes
from nxwright.language.resource_names import REFERENCE_TEXT
from nxwright.project.editor_language import (EDITOR_PROGRAM_VARIABLES, EDITOR_SYSTEM_VARIABLES,
                                              UNDECLARED_PROGRAM_VARIABLE)
from nxwright.project.editor_limits import NAME_LIMIT
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.project.page_text import STRING_ATTRIBUTES, is_string_attribute
from nxwright.project.screen_arithmetic import int32

NUMBER, TEXT = "number", "text"
# The names nxlang takes as texts after a component whose type it cannot
# tell, one reached through b[] or p[], or of a page whose types it is not
# given: the names that are texts on every type, and `dir` and `vvs2`, which
# it took as texts before it knew types, so that such code compiles as it
# did. A component whose type it knows has its own (attribute_kind).
_TEXTS_BY_NAME = STRING_ATTRIBUTES | {"dir", "vvs2"}
# The start of every name nxlang generates, which the project's own names
# may not have. The Editor took it for globals, number and text variables,
# and hotspots (probed with the Editor 1.68.2). Every generated name's shape
# below is built from it, and the rest of nxwright reads them through these.
GENERATED_PREFIX = "__"
# A program.s global, `__g<page>_<n>`: GLOBAL_NAME % (page, n).
GLOBAL_NAME = GENERATED_PREFIX + "g%d_%d"
# The generated components: shared text `__v0`, a text temporary `__s0`,
# and a function hotspot `__f0`.
SHARED_PREFIX = GENERATED_PREFIX + "v"
TEMPORARY_PREFIX = GENERATED_PREFIX + "s"
HOTSPOT_PREFIX = GENERATED_PREFIX + "f"
# A function's label, `__l0`, as nxlang renames it in its hotspot's event.
# It names no component or variable, so the patterns below leave it out.
LABEL_PREFIX = GENERATED_PREFIX + "l"
GENERATED_NAME = re.compile(r"%s[vsf][0-9]+" % GENERATED_PREFIX)
# A generated global, its page's number and its own as the groups.
GENERATED_GLOBAL = re.compile(r"%sg([0-9]+)_([0-9]+)" % GENERATED_PREFIX)
# Any generated name: a global or a component.
GENERATED_ANY = re.compile(r"%s|%s" % (GENERATED_GLOBAL.pattern, GENERATED_NAME.pattern))
HOTSPOT = "hotspot"     # the kind of a function's generated component
HOTSPOT_SIZE = 2        # the smallest hotspot the Editor accepts
# `click` nests 9 events deep at most. The first is the event a press or a
# timer runs, and each call or click in a chain nests one more. One level
# stays free, since a `page` command runs the new page's load event inside
# the current event. So a chain holds at most 9 - 1 - 1 calls and clicks.
MOST_CALL_DEPTH = 7
# The most program.s globals checked to work in the Editor; the build stops past it.
MOST_GLOBALS = 8000
# The most characters a generated text variable holds, shared text included.
TEXT_TEMPORARY_SIZE = 255

_KEYWORDS = frozenset({"if", "else", "while", "for", "int", "const", "var", "function",
                       "return", "break", "continue", "switch", "case", "default"})
_CASE_LABEL = re.compile(r"case\b(.*):")
_DEFAULT_LABEL = re.compile(r"default\s*:")

# Precedence levels, lowest first, as in C. So `a & 1 == 1` means
# `a & (1 == 1)`, which is refused: a comparison is not a number.
LEVELS = [("||",), ("&&",), ("|",), ("^",), ("&",), ("==", "!="), ("<", ">", "<=", ">="),
           ("<<", ">>"), ("+", "-"), ("*", "/", "%")]
PRECEDENCE = {operator: level for level, operators in enumerate(LEVELS) for operator in operators}
_LOGIC = ("&&", "||")
_COMPARISONS = ("==", "!=", "<", ">", "<=", ">=")
_ARITHMETIC = frozenset(operator for operator in PRECEDENCE
                        if operator not in _LOGIC and operator not in _COMPARISONS)
_NUMBER_COMMUTATIVE = frozenset({"+", "*", "&", "|", "^"})
# For each comparison, the one true exactly when it is false: `!(a==b)` is `a!=b`.
_REVERSED = {"==": "!=", "!=": "==", "<": ">=", ">=": "<", ">": "<=", "<=": ">"}
COMPOUND_ASSIGNMENTS = frozenset(operator + "=" for operator in _ARITHMETIC)

# The form '&name&' is one token, "own", so that no reader of tokens takes
# the name inside it for a name of its own (code_lines.OWN_ATTRIBUTE, without
# its group).
_TOKEN = re.compile(r'''[ \t]*(?:
      (?P<string>"(?:\\.|[^"\\])*")
    | (?P<reference>''' + REFERENCE_TEXT + r''')
    | (?P<own>'&[A-Za-z_][A-Za-z0-9_]*&')
    | (?P<number>0x[0-9A-Fa-f]+|[0-9]+)
    | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<operator><<=|>>=|<<|>>|<=|>=|==|!=|&&|\|\||\+\+|--|[-+*/%&|^]=|[-+*/%&|^<>!=()\[\].,;{}?:])
    )''', re.X)
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')
_CONST_LINE = re.compile(r"const\b")
_INCLUDE_LINE = re.compile(r"include\b")
FUNCTION_SIGNATURE = re.compile(r"function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*"
                                r"(?:->\s*(number|text)\s*)?:\s*")
PARAMETER = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(number|text)\s*")
# In a command's arguments: a resource's reference, matched so that it
# stays whole, or a bare name, which a local or constant may replace. A name
# before or after a dot, or before "[" or "(", is not bare.
_COMMAND_NAME = re.compile(r"(%s)|(?<![.\w@])([A-Za-z_][A-Za-z0-9_]*)(?![\w.\[(])"
                           % REFERENCE_TEXT)
# A name and "(" start a call, which no Editor command does. So a statement
# that starts so but does not read as a call, such as a half-typed one, is a
# mistake, not a command to pass on to the Editor.
_CALL_START = re.compile(r"[A-Za-z_][A-Za-z0-9_]*[ \t]*\(")
# A click the build can follow: a component's name, then 1 (Touch Press) or
# 0 (Touch Release).
_CLICK = re.compile(r"click\s+([A-Za-z_][A-Za-z0-9_]*)\s*,\s*([01])")
# A hex number in a command's arguments, with any minus right before it.
_COMMAND_HEX = re.compile(r"(?<![\w.])(-?)(0x[0-9A-Fa-f]+)(?![\w.])")
# A starting value of an `int` line written in hex, with any minus sign:
# "=" and the spaces after it, the sign, and the number.
_INT_HEX_VALUE = re.compile(r"(=\s*)(-?)\s*(0x[0-9A-Fa-f]+)\b")
# `int` and the whitespace after it, at an `int` line's start, when it holds
# a tab, which the Editor would read as part of the name. Spaces alone are
# kept, as the Editor takes them.
_INT_START = re.compile(r"^int(?=[ \t]*\t)[ \t]+")


@dataclass(frozen=True)
class Literal:
    """An operand used as written: a number, a text, a picture or font
    reference, or a constant's value. `kind` is NUMBER or TEXT."""
    text: str       # as written: 12, -5, 0x1f, "a", @pic(name)
    kind: str


@dataclass(frozen=True)
class Reference:
    """A named value, such as t0.txt, sys0, or p[0].b[1].txt: an attribute,
    an `int` variable of program.nx, or a system variable. `kind` is NUMBER
    or TEXT (attribute_kind)."""
    parts: tuple    # ((name, index expression or None), ...), as in p[0].b[1].txt
    kind: str


@dataclass(frozen=True)
class OwnAttribute:
    """The form '&name&' as written: an attribute of the object whose event
    holds the line. Only Editor code coming into nxlang is parsed with it
    (editor_code.py): nxlang replaces it before it compiles an event's
    lines, and refuses it elsewhere. Its kind, a number or a text, is not
    known (kind_of)."""
    text: str


@dataclass(frozen=True)
class Local:
    """A local or a function's parameter, held in a generated variable."""
    variable: str   # the generated variable, as referenced: __g0_3 or __v0.txt
    kind: str


@dataclass(frozen=True)
class Unary:
    """`-x` or `!x`."""
    operator: str   # "-" or "!"
    operand: object


@dataclass(frozen=True)
class Binary:
    """Two operands and the operator between them, such as `a + b`."""
    operator: str
    left: object
    right: object


@dataclass(frozen=True)
class Conditional:
    """`condition ? then : otherwise`, as in C: `then` when the condition
    holds, `otherwise` when it does not."""
    condition: object
    then: object
    otherwise: object


@dataclass(eq=False)
class Function:
    """A function of a page, with the generated variables and hotspot that
    the compiler gives it."""
    name: str
    parameters: list        # [(name, NUMBER or TEXT)]
    result: str             # NUMBER, TEXT, or None
    signature: str          # as written, for the comment heading its body
    number: int             # the line of its heading
    file: str = ""          # the .nx file defining it
    hotspot: str = ""       # shared by the functions of its call depth
    which: str = ""         # the global telling that hotspot which function runs
    index: int = 0          # this function's value of `which`
    depth: int = 1          # its call depth (see the module docstring)
    parameter_variables: list = field(default_factory=list)   # references, such as __g0_3
    result_variable: str = ""


@dataclass(frozen=True)
class Call:
    """A call of a page's function, with its argument expressions."""
    function: Function
    arguments: tuple


@dataclass
class Generated:
    """A component the compiler adds to a page: a text variable (`kind` TEXT)
    or a function hotspot (`kind` HOTSPOT)."""
    name: str
    kind: str


@dataclass(frozen=True)
class Macro:
    """A macro of macros.nx, as the compiler follows it when nxlang code
    calls it: the file holding it, the line of its heading, and its code
    lines as (line number, text), in strict Nextion syntax."""
    file: str
    number: int
    lines: tuple


@dataclass
class ProgramNames:
    """What every page's code may use beyond its own: program.nx's
    constants and `int` variables, and macros.nx's macros, {name: Macro}."""
    constants: dict = field(default_factory=dict)
    variables: frozenset = frozenset()
    macros: dict = field(default_factory=dict)


@dataclass(frozen=True)
class _MacroRun:
    """A macro in the graph of what may run during what (compile_page), with
    the place of its heading, for errors."""
    name: str
    file: str
    number: int


@dataclass
class CompiledPage:
    """A page's compiled code, and what the build must add to the page for it."""
    events: dict                                    # {(object, event): [(line number, text)]}
    generated: list = field(default_factory=list)   # [Generated], in the order to add them
    functions: dict = field(default_factory=dict)   # {name: Function}, those called
    globals: list = field(default_factory=list)     # the program.s globals it uses
    sources: dict = field(default_factory=dict)     # {event key: the .nx file defining it}
    bodies: dict = field(default_factory=dict)      # {function name: its compiled body}
    # The longest chain of calls and clicks, as "home.load", "showClock", ...:
    # an event, then what runs during it, each nesting one more.
    deepest_chain: list = field(default_factory=list)
    # {owner, as "home.load" or "show": {generated variable, as "__g0_3" or
    # "__v1.txt": the local, parameter, or result it holds, by its nxlang name}}
    local_names: dict = field(default_factory=dict)


class NotParsed(NxwrightError):
    """A line is not what the parser tried to read it as."""


def tokenize(code: str, number: int) -> list:
    """Returns the tokens of a line of code as (kind, text). `kind` is
    "string", "reference", "own" (the form '&name&'), "number", "name", or
    "operator". Raises NxwrightError for text that is none of these."""
    return [(kind, text) for kind, text, _, _ in token_spans(code, number)]


def token_spans(code: str, number: int = None) -> list:
    """Returns the tokens of a line of code as (kind, text, start, end), where
    `start` and `end` are the columns of the token's first character and of
    the character after it. `kind` is as for tokenize.

    With a line `number`, text that is no token raises NxwrightError naming
    that line. Without one, such a character is skipped, as a code editor
    reading half-typed code needs."""
    tokens, position = [], 0
    code = code.rstrip(" \t")
    while position < len(code):
        match = _TOKEN.match(code, position)
        if not match or match.end() == position:
            if number is not None:
                raise NxwrightError("cannot read %r" % code[position:].strip(), line=number)
            position += 1
            continue
        kind = match.lastgroup
        tokens.append((kind, match[kind], match.start(kind), match.end(kind)))
        position = match.end()
    return tokens


def _whole_expression(parser: "Parser"):
    """Returns the expression that takes every token `parser` has left.
    Raises NxwrightError, with the parser's reason and line, otherwise."""
    try:
        return parser.whole_expression()
    except NotParsed as error:
        raise NxwrightError(error.reason, line=error.line) from None


class Parser:
    """Reads expressions from tokens. `left_to_right` reads them as the Editor
    does: one chain of operators, each applied in turn. With a `scope`, a
    constant or local is read as its value, and a name before "(" as a call."""

    def __init__(self, tokens: list, number: int, scope=None, left_to_right: bool = False):
        self.tokens, self.position, self.number = tokens, 0, number
        self.scope, self.left_to_right = scope, left_to_right

    def peek(self):
        """Returns the next token's text, or None at the end."""
        return self.tokens[self.position][1] if self.position < len(self.tokens) else None

    def take(self) -> tuple:
        """Returns the next token as (kind, text), and moves past it."""
        if self.position >= len(self.tokens):
            raise NotParsed("the line ends too early", line=self.number)
        self.position += 1
        return self.tokens[self.position - 1]

    def expect(self, text: str):
        """Takes the next token, which must be `text`; raises NotParsed otherwise."""
        if self.peek() != text:
            raise NotParsed("expected %r" % text, line=self.number)
        self.position += 1

    def at_end(self) -> bool:
        """True when every token has been taken."""
        return self.position == len(self.tokens)

    def expect_end(self):
        """Raises NotParsed, naming the next token, unless every token has
        been taken."""
        if not self.at_end():
            raise NotParsed("unexpected %r" % self.peek(), line=self.number)

    def whole_expression(self):
        """Reads an expression that takes every token left. Raises NotParsed
        otherwise."""
        expression = self.expression()
        self.expect_end()
        return expression

    def expression(self):
        """Reads an expression. Read left to right, it stops at any operator
        but arithmetic. Otherwise it may be a conditional, `a ? b : c`,
        looser than every operator of LEVELS. A conditional groups from the
        right: `a ? b : c ? d : e` is `a ? b : (c ? d : e)`."""
        if self.left_to_right:
            left = self.unary()
            while self.peek() in _ARITHMETIC:
                operator = self.take()[1]
                left = Binary(operator, left, self.unary())
            return left
        condition = self.binary(0)
        if self.peek() != "?":
            return condition
        self.take()
        then = self.expression()
        self.expect(":")
        return Conditional(condition, then, self.expression())

    def binary(self, level: int):
        """Reads an expression with no conditional outside parentheses. It
        stops at an operator looser than LEVELS[level]."""
        if level == len(LEVELS):
            return self.unary()
        left = self.binary(level + 1)
        while self.peek() in LEVELS[level]:
            operator = self.take()[1]
            left = Binary(operator, left, self.binary(level + 1))
        return left

    def unary(self):
        """Reads an operand and any `-` or `!` before it (`!` only when not
        reading left to right). A minus right before a number is part of it."""
        if self.peek() == "-":
            self.take()
            if self.position < len(self.tokens) and self.tokens[self.position][0] == "number":
                return Literal(editor_number("-" + self.take()[1]), NUMBER)
            return Unary("-", self.unary())
        if self.peek() == "!" and not self.left_to_right:
            self.take()
            return Unary("!", self.unary())
        return self.primary()

    def primary(self):
        """Reads an expression in parentheses, a literal, a call, or a name."""
        kind, text = self.take()
        if text == "(" and kind == "operator":
            inner = self.expression()
            self.expect(")")
            return inner
        if kind == "string":
            return Literal(text, TEXT)
        if kind == "number":
            return Literal(editor_number(text), NUMBER)
        if kind == "reference":
            return Literal(text, NUMBER)
        if kind == "own":
            return OwnAttribute(text)
        if kind == "name":
            if self.peek() == "(" and self.scope is not None:
                return self.call(text)
            return self.reference(text)
        raise NotParsed("unexpected %r" % text, line=self.number)

    def call(self, name: str) -> Call:
        """Reads the arguments of a call of the function `name`, from its "("."""
        function = self.scope.function(name, self.number)
        self.take()
        arguments = []
        if self.peek() != ")":
            arguments.append(self.expression())
            while self.peek() == ",":
                self.take()
                arguments.append(self.expression())
        self.expect(")")
        if len(arguments) != len(function.parameters):
            raise NxwrightError("%s takes %d arguments, not %d"
                                % (name, len(function.parameters), len(arguments)),
                                line=self.number)
        return Call(function, tuple(arguments))

    def reference(self, first: str):
        """Reads a name and its fields after `first`, such as p[0].b[1].txt.
        A bare name that is a constant or local gives its value instead."""
        parts = [(first, self.index())]
        while self.peek() == ".":
            self.take()
            kind, text = self.take()
            if kind != "name":
                raise NotParsed("expected a name after '.'", line=self.number)
            parts.append((text, self.index()))
        if len(parts) == 1 and parts[0][1] is None and self.scope is not None:
            found = self.scope.lookup(first)
            if found is not None:
                return found
        page = self.scope.page if self.scope is not None else None
        return Reference(tuple(parts), attribute_kind(parts, page))

    def index(self):
        """Reads `[expression]` after a name, or returns None when none follows."""
        if self.peek() != "[":
            return None
        self.take()
        inner = self.expression()
        self.expect("]")
        return inner


def attribute_kind(parts: tuple, page) -> str:
    """Returns NUMBER or TEXT, the kind of the value a reference's `parts`
    name, as Reference holds them: by the type of the component they name,
    `t0.txt` or `page1.t0.txt`, where `page`, the _PageState compiling,
    knows it; else by the last name alone (_TEXTS_BY_NAME)."""
    names = [name for name, index in parts]
    indexed = any(index is not None for name, index in parts)
    type_number = None
    if page is not None and not indexed and len(names) in (2, 3):
        owner = page.page_name if len(names) == 2 else names[0]
        type_number = _type_number((page.object_types.get(owner) or {}).get(names[-2]))
    if type_number is not None:
        return TEXT if is_string_attribute(type_number, names[-1]) else NUMBER
    return TEXT if names[-1] in _TEXTS_BY_NAME else NUMBER


def _type_number(type_value):
    """The number of a type as a page file gives it, by its name
    ("data-record") or its number; None for no type, or one unknown."""
    if isinstance(type_value, str):
        return TYPES_BY_NAME.get(type_value)
    return type_value if isinstance(type_value, int) and not isinstance(type_value, bool) else None


def kind_of(expression, number: int) -> str:
    """Returns NUMBER or TEXT, the kind of the expression's value. Raises
    NxwrightError for text in arithmetic, and for what has a value only in a
    condition (a comparison, `!`) or none at all (a call without a result)."""
    if isinstance(expression, (Literal, Local, Reference)):
        return expression.kind
    if isinstance(expression, OwnAttribute):
        raise NxwrightError("the kind of %s is not known here" % expression.text, line=number)
    if isinstance(expression, Call):
        if expression.function.result is None:
            raise NxwrightError("function %s has no result"
                                % expression.function.name, line=number)
        return expression.function.result
    if isinstance(expression, Unary):
        if expression.operator == "!":
            raise NxwrightError("! can only be in a condition", line=number)
        if kind_of(expression.operand, number) != NUMBER:
            raise NxwrightError("%s cannot apply to text" % expression.operator, line=number)
        return NUMBER
    if isinstance(expression, Conditional):
        kind = kind_of(expression.then, number)
        if kind != kind_of(expression.otherwise, number):
            raise NxwrightError("both sides of ? : must be numbers, or both texts", line=number)
        return kind
    if expression.operator in _LOGIC or expression.operator in _COMPARISONS:
        raise NxwrightError("a comparison can only be a condition", line=number)
    kinds = (kind_of(expression.left, number), kind_of(expression.right, number))
    if expression.operator == "+" and TEXT in kinds:
        return TEXT
    if TEXT in kinds:
        raise NxwrightError("%s cannot apply to text" % expression.operator, line=number)
    return NUMBER


def _is_atomic(expression) -> bool:
    """True for a literal, local, or reference: an operand with no operator
    of its own, though a reference's index may hold one."""
    return isinstance(expression, (Literal, Local, Reference))


def _count_calls(expression) -> int:
    if isinstance(expression, Call):
        return 1 + sum(_count_calls(argument) for argument in expression.arguments)
    if isinstance(expression, Binary):
        return _count_calls(expression.left) + _count_calls(expression.right)
    if isinstance(expression, Unary):
        return _count_calls(expression.operand)
    if isinstance(expression, Conditional):
        # Both sides count, though only one runs: a result copied when it
        # need not be costs a line, never a wrong value.
        return sum(_count_calls(part) for part in
                   (expression.condition, expression.then, expression.otherwise))
    if isinstance(expression, Reference):
        return sum(_count_calls(index) for _, index in expression.parts if index is not None)
    return 0


def _plain(expression) -> bool:
    """True for an operand a condition can hold as it is: nothing to compute first."""
    if isinstance(expression, Literal):
        return not _refused_in_condition(expression)
    if isinstance(expression, Local):
        return True
    if isinstance(expression, Reference):
        return all(index is None or (_is_atomic(index) and _plain(index))
                   for _, index in expression.parts)
    return False


def _refused_in_condition(literal: Literal) -> bool:
    """True for a text the Editor refuses in a condition, though it takes it
    in an assignment: one that ends in an escaped backslash, as `"a\\\\"`
    (code_checks.ends_in_escaped_backslash). Such a text goes into a text
    temporary first."""
    return literal.text.startswith('"') and ends_in_escaped_backslash(literal.text)


def _last_argument_start(code: str):
    """Returns where the last argument of the command `code` starts: right
    after its last comma outside its texts, parentheses, and brackets, as a
    call's arguments hold commas of their own. None when it has none."""
    depth, start, quoted, escaped = 0, None, False, False
    for place, character in enumerate(code):
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif character == "," and depth == 0:
            start = place + 1
    return start


def _holds_semicolon_text(lines: list) -> bool:
    """True when a line of `lines` holds a quoted text with a semicolon. The
    Editor refused such a text in any part of a for's head, and compiled it
    in a while's condition and in a statement of its own."""
    return any(";" in text for line in lines for text in STRING_LITERAL.findall(line))


def _needs_computing(condition) -> bool:
    """True when a part of `a && b && ...` (or ||) needs lines of code run
    before it can be tested: it is an inner `&&` or `||`, or it compares
    something not plain."""
    if condition.operator in _LOGIC:
        return True
    return not (_plain(condition.left) and _plain(condition.right))


def _render_chain(chain: list) -> str:
    """Returns a chain as Editor code. A chain is a list of (operator,
    operand) applied in turn from left to right, the first operator None:
    [(None, "a"), ("-", "b")] gives "a-b"."""
    text = ""
    for operator, operand in chain:
        if operator == "-" and operand.startswith("-"):
            # "a--1" would read as a decrement.
            operator, operand = "+", operand[1:]
        text += (operator or "") + operand
    return text


class _Temporaries:
    """The temporaries shared by the events and functions of one call depth.
    A temporary lives only within one statement, so each statement takes
    them again from the first, and a new one is made only when a statement
    needs more than any before it."""

    def __init__(self, page: "_PageState"):
        self.page = page
        self.pool = {NUMBER: [], TEXT: []}
        self.used = {NUMBER: 0, TEXT: 0}

    def start_statement(self):
        self.used = {NUMBER: 0, TEXT: 0}

    def take(self, kind: str, number: int) -> str:
        """Returns the next temporary of `kind` that this statement has not used."""
        pool = self.pool[kind]
        if self.used[kind] == len(pool):
            pool.append(self.page.variable(TEMPORARY_PREFIX, kind, number))
        self.used[kind] += 1
        return pool[self.used[kind] - 1]


class _Emitter:
    """Compiles one statement: collects the lines that compute its parts."""

    def __init__(self, temporaries, indent: str, number: int, variables=frozenset()):
        self.temporaries, self.indent, self.number = temporaries, indent, number
        self.variables = variables     # program.nx's int variables
        # With two calls or more in a statement, a result is copied at once:
        # a later call could overwrite it.
        self.copy_results = False
        self.lines = []     # Editor code, indentation included

    def part(self, indent: str) -> "_Emitter":
        """Returns an emitter for a part of this statement, at another indentation."""
        part = _Emitter(self.temporaries, indent, self.number, self.variables)
        part.copy_results = self.copy_results
        return part

    def emit(self, code: str, extra_indent: str = ""):
        self.lines.append(self.indent + extra_indent + code)

    def temporary(self, kind: str) -> str:
        if self.temporaries is None:
            raise NxwrightError("this needs a temporary variable, which program.nx "
                                "cannot have; split it into simpler steps", line=self.number)
        return self.temporaries.take(kind, self.number)

    def atom(self, expression, in_condition: bool = False) -> str:
        """Returns the Editor text of a literal, local, or reference. In a
        condition, which holds no arithmetic, an index with arithmetic is
        computed into a temporary first, and so is a text the Editor
        refuses there (_refused_in_condition)."""
        if isinstance(expression, Literal):
            if in_condition and _refused_in_condition(expression):
                target = self.temporary(TEXT)
                self.emit(target + "=" + expression.text)
                return target
            return expression.text
        if isinstance(expression, Local):
            return expression.variable
        name, index = expression.parts[0]
        if (len(expression.parts) == 1 and index is None and name not in EDITOR_SYSTEM_VARIABLES
                and name not in self.variables):
            # A value is a constant, a local, a system variable, or an attribute.
            if name in EDITOR_PROGRAM_VARIABLES:
                raise NxwrightError(UNDECLARED_PROGRAM_VARIABLE % name, line=self.number,
                                    fix={"kind": "declare", "variable": name})
            raise NxwrightError("unknown name %s: not a constant, local, int "
                                "variable, or system variable" % name, line=self.number)
        parts = []
        for name, index in expression.parts:
            if index is None:
                parts.append(name)
            else:
                if kind_of(index, self.number) != NUMBER:
                    raise NxwrightError("an index must be a number", line=self.number)
                inner = self.value(index) if in_condition else _render_chain(self.chain(index))
                parts.append("%s[%s]" % (name, inner))
        return ".".join(parts)

    def value(self, expression, in_condition: bool = False) -> str:
        """Returns an operand holding the value: the expression itself when it
        is atomic, else a temporary computed first."""
        if _is_atomic(expression):
            return self.atom(expression, in_condition)
        if isinstance(expression, Call):
            kind = kind_of(expression, self.number)
            result = self.call(expression)
            if not self.copy_results:
                return result
            target = self.temporary(kind)
            self.emit(target + "=" + result)
            return target
        if isinstance(expression, Conditional):
            return self.conditional(expression)
        kind = kind_of(expression, self.number)
        chain = self.chain(expression)
        target = self.temporary(kind)
        self.emit(target + "=" + _render_chain(chain))
        return target

    def chain(self, expression) -> list:
        """Returns a chain (see _render_chain) that computes the expression."""
        kind = kind_of(expression, self.number)
        if kind == TEXT:
            return self.text_chain(expression)
        if isinstance(expression, (Call, Conditional)):
            return [(None, self.value(expression))]
        if _is_atomic(expression):
            return [(None, self.atom(expression))]
        if isinstance(expression, Unary):
            # The Editor refuses "-x"; "0-x" starts a chain the same way.
            return [(None, "0"), ("-", self.value(expression.operand))]
        left, right = expression.left, expression.right
        if _is_atomic(right):
            return self.chain(left) + [(expression.operator, self.atom(right))]
        if expression.operator in _NUMBER_COMMUTATIVE and _is_atomic(left):
            # `a+b*c` becomes `b*c+a`, with no temporary.
            return self.chain(right) + [(expression.operator, self.atom(left))]
        return self.chain(left) + [(expression.operator, self.value(right))]

    def text_chain(self, expression) -> list:
        """Returns the chain of a text expression. Joining is associative, so
        nested joins make one chain. A number in it is converted with covx first."""
        if isinstance(expression, (Call, Conditional)) and kind_of(expression, self.number) == TEXT:
            return [(None, self.value(expression))]
        if isinstance(expression, Binary) and kind_of(expression, self.number) == TEXT:
            left, right = self.text_chain(expression.left), self.text_chain(expression.right)
            return left + [("+", right[0][1])] + right[1:]
        if kind_of(expression, self.number) == NUMBER:
            source = self.value(expression)
            target = self.temporary(TEXT)
            self.emit("covx %s,%s,0,0" % (source, target))
            return [(None, target)]
        return [(None, self.atom(expression))]

    def assign(self, target: str, target_kind: str, operator: str, expression):
        """Emits `target operator expression`, after the lines that compute its
        parts. `target` is Editor text, such as t0.txt, and `target_kind` its kind."""
        kind = kind_of(expression, self.number)
        if target_kind == NUMBER and kind == TEXT:
            raise NxwrightError("text cannot be put in a number", line=self.number)
        if target_kind == TEXT and operator == "-=":
            # The Editor's "t0.txt-=n" removes the last n characters.
            if kind != NUMBER:
                raise NxwrightError("-= on text takes a number of characters", line=self.number)
            self.emit(target + "-=" + self.value(expression))
            return
        if target_kind == TEXT and operator not in ("=", "+="):
            raise NxwrightError("%s cannot apply to text" % operator, line=self.number)
        if target_kind == TEXT and kind == NUMBER:
            # A number becomes text through covx; adding it needs a temporary.
            source = self.value(expression)
            if operator == "=":
                self.emit("covx %s,%s,0,0" % (source, target))
                return
            text = self.temporary(TEXT)
            self.emit("covx %s,%s,0,0" % (source, text))
            self.emit(target + "+=" + text)
            return
        chain = self.chain(expression)
        if target_kind == TEXT and _names_target_unsafely(target, operator, chain):
            temporary = self.temporary(TEXT)
            self.emit(temporary + "=" + _render_chain(chain))
            chain = [(None, temporary)]
        if operator == "=":
            self.emit(target + "=" + _render_chain(chain))
            return
        if len(chain) > 1 and not same_as_editor(operator[:-1], chain, target_kind):
            # The Editor reads `x-=a+b` as `(x-a)+b`: compute `a+b` first.
            temporary = self.temporary(kind)
            self.emit(temporary + "=" + _render_chain(chain))
            chain = [(None, temporary)]
        self.emit(target + operator + _render_chain(chain))

    def call(self, call: Call) -> str:
        """Emits a call; returns its result variable ("" without a result).
        All arguments are computed before any parameter is set, so a call
        among them cannot overwrite one."""
        function = call.function
        operands = [Literal(self.value(argument), kind_of(argument, self.number))
                    if _count_calls(argument) else argument for argument in call.arguments]
        for (_, kind), variable, operand in zip(function.parameters, function.parameter_variables,
                                                operands):
            if kind == NUMBER and kind_of(operand, self.number) == TEXT:
                raise NxwrightError("%s takes a number, not text"
                                    % function.name, line=self.number)
            self.assign(variable, kind, "=", operand)
        # Last: an argument may have called another function of this hotspot.
        self.emit("%s=%d" % (function.which, function.index))
        self.emit("click %s,1" % function.hotspot)
        return function.result_variable if function.result else ""

    def conditional(self, expression: Conditional) -> str:
        """Computes `condition ? then : otherwise` into a temporary of its
        kind, and returns the temporary. Each side's own lines are written
        inside its block, so only the chosen side is computed."""
        kind = kind_of(expression, self.number)
        condition = self.condition(expression.condition)
        target = self.temporary(kind)
        self.emit("if(%s)" % condition)
        self.emit("{")
        self.side(target, kind, expression.then)
        self.emit("}else")
        self.emit("{")
        self.side(target, kind, expression.otherwise)
        self.emit("}")
        return target

    def side(self, target: str, kind: str, expression):
        """Emits the lines setting `target` to one side of a conditional, one
        step further in."""
        part = self.part(self.indent + "  ")
        part.assign(target, kind, "=", expression)
        self.lines += part.lines

    def condition(self, expression) -> str:
        """Returns the Editor text of a condition, after emitting the lines
        that compute its parts."""
        return self._condition(_normalize(expression, False, self.number))

    def _condition(self, expression) -> str:
        """Does what condition does, for a condition _normalize has rewritten."""
        if isinstance(expression, Binary) and expression.operator in _LOGIC:
            children = _flatten(expression, expression.operator)
            if any(_needs_computing(child) for child in children[1:]):
                return self.short_circuit(expression.operator, children) + "==1"
            parts = []
            for child in children:
                if isinstance(child, Binary) and child.operator in _LOGIC:
                    parts.append(self.flag(child) + "==1")
                else:
                    parts.append(self.comparison(child))
            return expression.operator.join(parts)
        return self.comparison(expression)

    def comparison(self, expression) -> str:
        """Returns `left operator right`, with each side computed first unless plain."""
        left_kind = kind_of(expression.left, self.number)
        if left_kind != kind_of(expression.right, self.number):
            raise NxwrightError("a comparison needs two numbers or two texts", line=self.number)
        if left_kind == TEXT and expression.operator not in ("==", "!="):
            raise NxwrightError("texts compare only with == and !=", line=self.number)
        return (self.value(expression.left, True) + expression.operator
                + self.value(expression.right, True))

    def short_circuit(self, operator: str, children: list) -> str:
        """Computes `child && child ...` (or ||) into a number temporary
        holding 0 or 1, reaching each child only when the ones before it
        leave the result open."""
        target = self.temporary(NUMBER)
        self.emit(target + "=0")
        self._short_circuit_level(operator, children, target, self.indent)
        return target

    def _short_circuit_level(self, operator: str, children: list, target: str, indent: str):
        """Emits the `if` that tests the first of `children`. With `&&`, it
        holds the tests of the rest, and the last test sets `target` to 1.
        With `||`, it sets `target` to 1, and its `else` tests the rest."""
        part = self.part(indent)
        condition = part._condition(children[0])
        self.lines += part.lines
        rest = children[1:]
        self.lines += [indent + "if(%s)" % condition, indent + "{"]
        if operator == "&&" and rest:
            self._short_circuit_level(operator, rest, target, indent + "  ")
        else:
            self.lines.append(indent + "  " + target + "=1")
        if operator == "||" and rest:
            self.lines += [indent + "}else", indent + "{"]
            self._short_circuit_level(operator, rest, target, indent + "  ")
        self.lines.append(indent + "}")

    def flag(self, expression) -> str:
        """Computes a condition into a number temporary holding 0 or 1."""
        condition = self._condition(expression)
        target = self.temporary(NUMBER)
        self.emit(target + "=0")
        self.emit("if(%s)" % condition)
        self.emit("{")
        self.emit(target + "=1", "  ")
        self.emit("}")
        return target


def _names_target_unsafely(target: str, operator: str, chain: list) -> bool:
    """True when a text assignment names its own target where the screen gets
    it wrong. The screen keeps the target's text and appends the other pieces,
    so only `t0.txt=t0.txt+...`, with the target once and first, comes out as
    written. With `+=`, any mention of the target goes wrong (checked in the Editor)."""
    places = [position for position, (_, operand) in enumerate(chain) if operand == target]
    if operator == "+=":
        return bool(places)
    return bool(places) and places != [0]


def same_as_editor(operator: str, chain: list, kind: str) -> bool:
    """True when the Editor computes a compound assignment as nxlang does.
    The Editor reads `x-=a+b` as `(x-a)+b`, nxlang as `x-(a+b)`. `operator`
    is the compound's operator without "=", `chain` its right side (see
    _render_chain), and `kind` the target's kind."""
    others = {item[0] for item in chain[1:]}
    if kind == TEXT or operator == "+":
        return others <= {"+", "-"} if kind == NUMBER else True
    return operator in ("*", "&", "|", "^") and others == {operator}


def _flatten(expression, operator: str) -> list:
    """Returns the operands that `operator` joins: `a && b && c` gives [a, b, c]."""
    if isinstance(expression, Binary) and expression.operator == operator:
        return _flatten(expression.left, operator) + _flatten(expression.right, operator)
    return [expression]


def _normalize(expression, negate: bool, number: int):
    """Returns a condition without "!", and with a plain number `n` written
    `n!=0`. `negate` is True inside an odd number of "!". A negated
    comparison is reversed: `!(a==b)` gives `a!=b`, and `!n` gives `n==0`.
    A negated `&&` becomes `||` of the negated sides, and the other way round."""
    if isinstance(expression, Unary) and expression.operator == "!":
        return _normalize(expression.operand, not negate, number)
    if isinstance(expression, Binary) and expression.operator in _LOGIC:
        operator = expression.operator
        if negate:
            operator = "||" if operator == "&&" else "&&"
        return Binary(operator, _normalize(expression.left, negate, number),
                      _normalize(expression.right, negate, number))
    if isinstance(expression, Binary) and expression.operator in _COMPARISONS:
        operator = _REVERSED[expression.operator] if negate else expression.operator
        return Binary(operator, expression.left, expression.right)
    if kind_of(expression, number) != NUMBER:
        raise NxwrightError("a condition needs a comparison", line=number)
    return Binary("==" if negate else "!=", expression, Literal("0", NUMBER))


class _PageState:
    """What every event of a page shares: its names and generated variables."""

    def __init__(self, page_name: str, component_names, program: ProgramNames, page_id: int = 0,
                 object_types: dict = None):
        self.page_name, self.page_id = page_name, page_id
        self.component_names = set(component_names)
        # {page: {name: type}}, a page's None while unknown (compile_page)
        self.object_types = object_types or {}
        self.data_records = frozenset(      # which components are data records
            name for name, kind in (self.object_types.get(page_name) or {}).items()
            if _type_number(kind) == TYPES_BY_NAME["data-record"])
        self.constants = dict(program.constants)
        self.variables = program.variables
        self.functions = None   # {name: Function}; None where calls are not possible
        self.generated = []
        self.globals = []
        self.counters = {}      # {name prefix: how many components it has named}
        self.labels = 0         # how many functions' labels it has named
        self.pools = {}         # {call depth: _Temporaries}
        # The number of the next shared text variable of the event or
        # function being compiled; None outside one, where each gets a new one.
        self.next_shared = None

    def variable(self, prefix: str, kind: str, number: int) -> str:
        """Returns a generated variable, as code refers to it, such as __g0_3 or
        __s0.txt. A number is always a new program.s global, whatever `prefix`.
        A text temporary (`prefix` TEMPORARY_PREFIX) is a new variable
        component. Any other text is the next shared text variable, from
        shared_text."""
        if kind == NUMBER:
            name = GLOBAL_NAME % (self.page_id, len(self.globals))
            if len(name) > NAME_LIMIT:
                raise NxwrightError("page %s needs too many generated variables"
                                    % self.page_name, line=number)
            self.globals.append(name)
            return name
        if prefix == TEMPORARY_PREFIX:
            return self.generate(prefix, kind, number) + ".txt"
        return self.shared_text(number)

    def shared_text(self, number: int) -> str:
        """Returns the next shared text variable of the event or function being
        compiled, such as __v2.txt. Its component is made only when nothing
        compiled before needed that many."""
        made = self.counters.get(SHARED_PREFIX, 0)
        if self.next_shared is None:
            slot = made
        else:
            slot, self.next_shared = self.next_shared, self.next_shared + 1
        if slot == made:
            self.generate(SHARED_PREFIX, TEXT, number)
        return "%s%d.txt" % (SHARED_PREFIX, slot)

    def start_owner(self, first: int):
        """Starts compiling an event or function whose shared text variables
        are numbered from `first`."""
        self.next_shared = first

    def end_owner(self) -> int:
        """Ends what start_owner started; returns the number after its last
        shared text variable."""
        after, self.next_shared = self.next_shared, None
        return after

    def label(self) -> str:
        """Returns a new name for a function's label, such as __l0. The
        functions of one depth compile into one event, their hotspot's, so
        one function's label may not share another's name. The names are
        numbered across the page, so none is shared in any hotspot."""
        name = "%s%d" % (LABEL_PREFIX, self.labels)
        self.labels += 1
        return name

    def temporaries(self, depth: int) -> "_Temporaries":
        """Returns the temporaries of the events and functions of call depth `depth`."""
        return self.pools.setdefault(depth, _Temporaries(self))

    def scratch(self) -> "_PageState":
        """Returns a copy for compiling code only to check it: what it generates
        is dropped."""
        other = copy.copy(self)
        other.generated, other.globals, other.counters, other.pools = [], [], {}, {}
        other.next_shared = None
        return other

    def generate(self, prefix: str, kind: str, number: int) -> str:
        """Returns the name of a new component to add to the page, `prefix`
        then a number, such as __f0."""
        count = self.counters.get(prefix, 0)
        self.counters[prefix] = count + 1
        name = "%s%d" % (prefix, count)
        if len(name) > NAME_LIMIT:
            raise NxwrightError("page %s needs too many generated variables"
                                % self.page_name, line=number)
        self.generated.append(Generated(name, kind))
        return name

    def check_new_name(self, name: str, number: int, what: str):
        """Raises NxwrightError when `name` cannot be given to a new `what`:
        "constant", "function", "parameter", or "local"."""
        if name.startswith(GENERATED_PREFIX):
            raise NxwrightError("%s %s may not start with %r, which generated "
                                "variables use" % (what, name, GENERATED_PREFIX), line=number)
        # A local or parameter may share a component's name: bare, the name is
        # the local; with a field, such as name.txt, it is the component. A
        # library function cannot know the components of the pages including it.
        may_shadow = what in ("local", "parameter")
        if ((name in self.component_names and not may_shadow) or name in EDITOR_SYSTEM_VARIABLES
                or name in _KEYWORDS or name in self.variables):
            raise NxwrightError("%s %s has the name of a component, variable, or "
                                "keyword" % (what, name), line=number)
        if name in self.constants:
            raise NxwrightError("%s is already a constant" % name, line=number)
        if self.functions and name in self.functions:
            raise NxwrightError("%s is already a function" % name, line=number)


class _Scope:
    """The names an event or function can use: its locals and parameters, and
    the page's constants and functions."""

    def __init__(self, page: _PageState):
        self.page, self.locals = page, {}

    def lookup(self, name: str):
        """Returns the Local or the constant's Literal that `name` stands for, or None."""
        return self.locals.get(name) or self.page.constants.get(name)

    def function(self, name: str, number: int) -> Function:
        if self.page.functions is None:
            raise NxwrightError("program.nx cannot call functions", line=number)
        if name not in self.page.functions:
            raise NxwrightError("unknown function %s" % name, line=number)
        return self.page.functions[name]


@dataclass(eq=False)
class _Block:
    """A block of code open while an event compiles. It records what to write
    when it closes, and the `break` and `continue` that may have run inside."""
    kind: str           # "if" (an if or else-if), "else", "while", "for", "switch", "case"
    recompute: list = field(default_factory=list)   # code to run again before the closing "}"
    # How many "}" to add when its if chain ends: one for each `else if`
    # written as `else { ... if`.
    extra: int = 0
    on_open: list = field(default_factory=list)     # code to run first inside the "{"
    braces: bool = True                 # False for a switch: no Editor block
    flag: str = ""                      # a loop's or switch's control variable
    # The jumps that may have run inside it, each as (control variable, the
    # loop or switch it leaves). `pending` holds those the next statement
    # must be guarded against: guard() puts it inside an `if` testing them.
    jumps: set = field(default_factory=set)
    pending: set = field(default_factory=set)
    guards: int = 0                     # those `if` blocks, closed with this block
    indent: str = ""
    switch: tuple = ()                  # a switch's (value, matched, no-case-matches) variables, and kind


def _read_constants(lines: list, page: _PageState):
    """Adds the `const` lines among `lines` [(number, text)] to the page's constants.
    Raises NxwrightError for a line that is not a constant, comment, or blank."""
    for number, text in lines:
        indent, code, _ = split_line(text, number)
        if not code:
            continue
        if not _CONST_LINE.match(code):
            raise NxwrightError("only includes and constants can come before the "
                                "first event or function", line=number)
        name, value = _parse_constant(code, number)
        page.check_new_name(name, number, "constant")
        page.constants[name] = value


def _parse_constant(code: str, number: int) -> tuple:
    """Returns (name, Literal) of a `const` line."""
    _check_no_own_attribute(code, number, _IN_A_CONSTANT)
    tokens = tokenize(code, number)
    if len(tokens) < 4 or tokens[1][0] != "name" or tokens[2][1] != "=":
        raise NxwrightError("a constant is written const NAME = <number or text>", line=number)
    rest = tokens[3:]
    if len(rest) == 2 and rest[0][1] == "-" and rest[1][0] == "number":
        return tokens[1][1], Literal(editor_number("-" + rest[1][1]), NUMBER)
    if len(rest) == 1 and rest[0][0] == "number":
        return tokens[1][1], Literal(editor_number(rest[0][1]), NUMBER)
    if len(rest) == 1 and rest[0][0] == "string":
        return tokens[1][1], Literal(rest[0][1], TEXT)
    raise NxwrightError("a constant's value must be a number or a text", line=number)


# Why nxlang refuses the form '&name&' outside an event of an object, which
# replaces it before its lines are compiled (compile_page).
_IN_A_FUNCTION = ("in a function: a function's body runs from a hotspot nxlang adds, so the "
                 "form would name the hotspot's attributes")
_IN_A_CONSTANT = "in a constant: its text reaches every line that names it, a function's too"
_IN_NO_EVENT = "here: no object's event holds this line"


def _with_owner(lines: list, owner) -> tuple:
    """Returns an event's lines, [(line number, text)], with the form
    '&name&' replaced in each line's code part by `owner`'s ID or attribute,
    in a quoted text too, as the Nextion Editor reads it
    (with_own_attributes), and {line number: code as written} of the lines
    it changed. Every line is replaced before any is compiled, so that what
    reads lines ahead, such as a switch's case labels, reads them replaced."""
    replaced, written = [], {}
    for number, text in lines:
        indent, code, comment = split_line(text, number)
        read = with_own_attributes(code, owner)
        if read != code:
            written[number] = code
            text = indent + read + comment
        replaced.append((number, text))
    return replaced, written


def _check_no_own_attribute(code: str, number: int, where: str):
    """Raises NxwrightError for a line's code part using the form '&name&',
    in a quoted text too, saying why it is refused `where`: _IN_A_FUNCTION,
    _IN_A_CONSTANT, or _IN_NO_EVENT. The Editor would replace it by an
    attribute of the object whose event holds the line."""
    if OWN_ATTRIBUTE.search(code):
        raise NxwrightError("nxlang refuses the form '&name&' %s. Name the object itself, as "
                            "in n0.val" % where, line=number)


def is_constant_line(text: str) -> bool:
    """True for a `const` line of program.nx or of a page's preamble."""
    return _CONST_LINE.match(text.lstrip(" \t")) is not None


def compile_page(page_name: str, component_names, program: ProgramNames, preambles: list,
                 events: dict, functions: dict = None, page_id: int = 0,
                 object_types: dict = None, owners: dict = None) -> CompiledPage:
    """Compiles a page's code, from its .nx file and the files it includes,
    into lines for the preprocessor. `program` is what program.nx declares.
    `preambles` is [(file, lines)]: each file's constants, the page's own
    file last. `events` is {(object, event): (file, [(line number, text)])}.
    `functions` is {name: (file, heading line number, heading, body lines)};
    those the page calls run in the Touch Press event of their depth's
    hotspot, and the page's Preinitialize event turns their touch off first.
    The others are checked only. `page_id` numbers the page's globals.
    `object_types` gives the types of the pages' objects, {page: {name:
    type}}, types as page files name them ("data-record"), as the build's
    checks hold them (code_checks.ObjectNames): the page's own at
    least, a page's None while unknown. A component's type tells the kind of
    its attributes (attribute_kind), and the page's data records have their
    calls compiled (_EventCompiler.data_record_call). `owners` gives an
    event's owner, {(object, event): Owner}, the object whose event it is:
    its lines have the form '&name&' replaced before they are compiled, as
    the Nextion Editor reads them (_with_owner). An event without one, a
    function, and a constant refuse the form.

    Raises NxwrightError naming the file and line of anything it cannot compile.
    """
    functions, owners = functions or {}, owners or {}
    page_file = preambles[-1][0] if preambles else page_name + ".nx"
    for name in component_names:
        if name.startswith(GENERATED_PREFIX):
            raise NxwrightError("component %s starts with %r, which generated variables use"
                                % (name, GENERATED_PREFIX))
    for name in program.constants:
        if name in component_names:
            raise NxwrightError("program.nx constant %s has the name of a component of page %s"
                                % (name, page_name))
    page = _PageState(page_name, component_names, program, page_id, object_types)
    for file, lines in preambles:
        with _naming(file):
            _read_constants(lines, page)
    page.functions = {}
    for name, (file, number, heading, _) in functions.items():
        with _naming(file):
            page.functions[name] = _declare_function(page, heading, number, file)
    # Each parameter was checked only against the functions declared before
    # its own: check it against all of them.
    for function in page.functions.values():
        for parameter, _ in function.parameters:
            if parameter in page.functions:
                raise NxwrightError("%s is already a function"
                                    % parameter, file=function.file, line=function.number)
    callees = {name: _calls_in(lines, page.functions) for name, (_, _, _, lines) in functions.items()}
    _check_no_cycle(callees, page.functions)
    # A macro's click gives an object's ID, which each event's owner holds.
    objects = {owner.id: owner.name for owner in owners.values() if owner is not None}
    graph, called = _runs_during(page, events, functions, callees, program.macros, objects)
    order = _callees_first(graph, events, page.functions)
    depths, deepest_caller = _depths(graph, order)
    for name, function in page.functions.items():
        if name in called:
            _name_variables(page, function, NUMBER)
    hotspots = _place_functions(page, callees, depths)
    chain = _deepest_chain(depths, deepest_caller)
    _check_nesting(chain, events, page.functions)
    compiled = CompiledPage({}, functions={name: function for name, function in page.functions.items()
                                           if name in called},
                            deepest_chain=[_owner_label(owner) for owner in chain])
    # Each owner's shared text variables start after those of everything
    # that may run during it, so none of those can change them. Owners on
    # separate chains share variables.
    results, ends = {}, {}
    for owner in order:
        if isinstance(owner, _MacroRun):
            # A macro owns no variables: those of what runs during it come
            # before its caller's.
            ends[owner] = max((ends[runs] for runs in graph[owner]), default=0)
            continue
        page.start_owner(max((ends[runs] for runs in graph[owner]), default=0))
        if isinstance(owner, tuple):
            file, lines = events[owner]
            with _naming(file):
                written = {}
                if owners.get(owner) is not None:
                    lines, written = _with_owner(lines, owners[owner])
                compiler = _EventCompiler(page, page.temporaries(depths[owner]), written=written)
                results[owner] = compiler.compile(lines)
        else:
            function = page.functions[owner]
            with _naming(function.file):
                _name_variables(page, function, TEXT)
                compiler = _EventCompiler(page, page.temporaries(function.depth), function)
                results[owner] = compiler.compile(functions[owner][3])
        compiled.local_names[_owner_label(owner)] = compiler.local_names()
        ends[owner] = page.end_owner()
    for key, (file, _) in events.items():
        compiled.sources[key] = file
        compiled.events[key] = results[key]
    bodies = {}
    for name, function in compiled.functions.items():
        body = results[name]
        compiled.bodies[name] = body
        bodies.setdefault(function.hotspot, []).extend(
            [(function.number, "// " + function.signature),
             (function.number, "if(%s==%d)" % (function.which, function.index)),
             (function.number, "{")]
            + [(number, "  " + text) for number, text in body] + [(function.number, "}")])
    _check_uncalled(page, functions, called)
    for hotspot in hotspots:
        compiled.events[(hotspot, "down")] = bodies[hotspot]
    if hotspots:
        load = (page_name, "load")
        compiled.sources.setdefault(load, page_file)
        compiled.events[load] = ([(0, "tsw %s,0" % hotspot) for hotspot in hotspots]
                                 + compiled.events.get(load, []))
    compiled.generated = page.generated
    compiled.globals = page.globals
    return compiled


def _check_uncalled(page: _PageState, functions: dict, called: set):
    """Compiles the functions the page does not call, in a copy of the page
    that is then dropped: they are checked, and generate nothing."""
    scratch = page.scratch()
    unused = [function for name, function in page.functions.items() if name not in called]
    # Their variables first: one may call another.
    for function in unused:
        _name_variables(scratch, function, NUMBER)
        _name_variables(scratch, function, TEXT)
    for function in unused:
        with _naming(function.file):
            _EventCompiler(scratch, scratch.temporaries(1), function).compile(
                functions[function.name][3])


@contextmanager
def _naming(file: str):
    """Puts the file's name before the line number of an error raised inside."""
    try:
        yield
    except NxwrightError as error:
        raise error.in_file(file) from None


def _reachable(start: set, callees: dict) -> set:
    """Returns `start` and every function they call, directly or not."""
    found, waiting = set(), list(start)
    while waiting:
        name = waiting.pop()
        if name not in found:
            found.add(name)
            waiting.extend(callees.get(name, ()))
    return found


def _clicks_in(lines: list, page: _PageState) -> set:
    """Returns the events that the `click` commands among `lines` run:
    (component, "down") for `click name,1`, (component, "up") for 0.

    Raises NxwrightError for a click that does not name its component and
    0 or 1: the build could not tell which event it runs.
    """
    clicked = set()
    for number, text in lines:
        code = split_line(text, number)[1].rstrip(" \t")
        if not re.match(r"click(\s|$)", code):
            continue
        match = _CLICK.fullmatch(code)
        if match is None or match[1] in page.constants:
            raise NxwrightError("a click names its component and 0 or 1, as in "
                                "click b0,1, so the build can tell which event it runs",
                                line=number)
        clicked.add((match[1], "down" if match[2] == "1" else "up"))
    return clicked


def _runs_during(page: _PageState, events: dict, functions: dict, callees: dict, macros: dict,
                 objects: dict) -> tuple:
    """Returns {owner: what may run during it directly}, for each event and
    called function: the functions it calls, the events of this page its
    clicks run, and the macros it calls, and for each such macro what may
    run during it (_follow_macros). `macros` are macros.nx's {name: Macro},
    and `objects` the page's {ID: object name}. Also returns the names of
    the called functions. Every function's clicks are checked, called or not."""
    clicks = {}
    for name, (file, _, _, lines) in functions.items():
        with _naming(file):
            clicks[name] = _clicks_in(lines, page)
    graph = {}
    for key, (file, lines) in events.items():
        with _naming(file):
            graph[key] = _calls_in(lines, page.functions) | (_clicks_in(lines, page) & events.keys())
        graph[key] |= _macros_called_in(lines, macros)
    called = _reachable(set().union(*(graph[key] for key in events)) & page.functions.keys(), callees)
    graph.update({name: callees[name] | (clicks[name] & events.keys())
                  | _macros_called_in(functions[name][3], macros)
                  for name in page.functions if name in called})
    _follow_macros(graph, macros, objects, events)
    return graph, called


# A click in a macro: a component's ID, then 1 (Touch Press) or 0 (Touch
# Release). A macro gives a component by its ID alone (macros_source.py).
_MACRO_CLICK = re.compile(r"click\s+([0-9]+)\s*,\s*([01])")


def _code_of(lines: list):
    """Yields (line number, code) of `lines`, comments left out. A line
    that does not read is skipped: the build reports it where it compiles
    that line."""
    for number, text in lines:
        try:
            yield number, split_line(text, number)[1]
        except NxwrightError:
            continue


def _macros_called_in(lines: list, macros: dict) -> set:
    """Returns the macros of `macros`, {name: Macro}, that the `call` lines
    among `lines` run, as _MacroRun. A call of a macro the folder lacks runs
    none: the build's checks refuse it (code_checks.py)."""
    called = set()
    for _, code in _code_of(lines):
        if command_word(code) == "call":
            name = code[len("call"):].strip(" \t")
            if name in macros:
                called.add(_MacroRun(name, macros[name].file, macros[name].number))
    return called


def _follow_macros(graph: dict, macros: dict, objects, events: dict):
    """Adds to `graph` each macro that its owners call, directly or not,
    with what may run during it: the macros it calls, and the events its
    clicks run. A click gives the ID of an object of `objects`, {ID: object
    name}, the page whose code calls it; an ID it lacks runs nothing.
    `objects` is None for program.nx, which has no page.

    Raises NxwrightError, naming the macro's line, for a click whose ID or
    event is not a written number, as nxlang refuses such a click in its
    own code; and without a page, for any click."""
    waiting = [node for runs in list(graph.values()) for node in runs
               if isinstance(node, _MacroRun)]
    while waiting:
        node = waiting.pop()
        if node in graph:
            continue
        macro = macros[node.name]
        runs = _macros_called_in(macro.lines, macros)
        for number, code in _code_of(macro.lines):
            if not re.match(r"click(\s|$)", code):
                continue
            match = _MACRO_CLICK.fullmatch(code)
            if match is None:
                raise NxwrightError("%s: a click in a macro that nxlang code calls gives a "
                                    "component's ID and 0 or 1, as in click 3,1, so that the "
                                    "build can tell which event it runs" % code,
                                    file=macro.file, line=number)
            if objects is None:
                raise NxwrightError("%s: program.nx runs macro %s, and has no page whose "
                                    "events the build could follow from its click"
                                    % (code, node.name), file=macro.file, line=number)
            if int(match[1]) in objects:
                runs.add((objects[int(match[1])], "down" if match[2] == "1" else "up"))
        graph[node] = {item for item in runs if isinstance(item, _MacroRun) or item in events}
        waiting.extend(item for item in runs if isinstance(item, _MacroRun))


def _owner_label(owner) -> str:
    """Returns an event as component.event, a function as its name, and a
    macro as `macro <name>`."""
    if isinstance(owner, _MacroRun):
        return "macro %s" % owner.name
    return "%s.%s" % owner if isinstance(owner, tuple) else owner


def _owner_place(owner, events: dict, functions: dict) -> tuple:
    """Returns the file and line where an event, function, or macro starts, for errors."""
    if isinstance(owner, _MacroRun):
        return owner.file, owner.number
    if isinstance(owner, tuple):
        file, lines = events[owner]
        return file, lines[0][0] if lines else 0
    return functions[owner].file, functions[owner].number


def _callees_first(graph: dict, events: dict, functions: dict) -> list:
    """Returns the events and functions of `graph` {owner: what may run
    during it}, each after everything that may run during it.

    Raises NxwrightError when calls and clicks come back to an owner already
    running: it has one set of variables, which the second run would overwrite.
    Coming back to a macro is refused too: how deep it nests cannot be counted.
    """
    def refuse(cycle: list):
        owner = cycle[0]
        file, number = _owner_place(owner, events, functions)
        why = ("the build cannot count how deep they nest" if isinstance(owner, _MacroRun)
               else "which has one set of variables")
        raise NxwrightError("the calls and clicks %s come back to %s, %s" % (" -> ".join(
                                _owner_label(item) for item in cycle), _owner_label(owner), why),
                            file=file, line=number)
    return _depth_first(graph, lambda owner: sorted(graph[owner], key=_owner_label), refuse)


def _depth_first(nodes, edges, refuse_cycle) -> list:
    """Returns the nodes reached from `nodes`, depth first, each after every
    node it leads to. `edges(node)` gives those, in the order to follow
    them. Each node is visited once. A path that comes back to a node whose
    search is still open is a cycle: `refuse_cycle` is given that path, from
    the node back to itself, and raises."""
    order, state = [], {}

    def visit(node, path: list):
        if state.get(node) == "done":
            return
        if state.get(node) == "open":
            refuse_cycle(path[path.index(node):] + [node])
        state[node] = "open"
        for following in edges(node):
            visit(following, path + [node])
        state[node] = "done"
        order.append(node)
    for node in nodes:
        visit(node, [])
    return order


def _depths(graph: dict, order: list) -> tuple:
    """Returns {owner: its depth}, the most calls and clicks leading to it
    from an event that nothing runs, and {owner: the caller on that chain}."""
    depths = {owner: 0 for owner in order}
    deepest_caller = {}
    for owner in reversed(order):
        for runs in graph[owner]:
            if depths[owner] + 1 > depths[runs]:
                depths[runs] = depths[owner] + 1
                deepest_caller[runs] = owner
    return depths, deepest_caller


def _deepest_chain(depths: dict, deepest_caller: dict) -> list:
    """Returns the longest chain of owners, from an event that nothing runs
    to the deepest event or function, or [] for a page with no code."""
    deepest = max(depths, key=depths.get, default=None)
    if deepest is None:
        return []
    chain = [deepest]
    while chain[0] in deepest_caller:
        chain.insert(0, deepest_caller[chain[0]])
    return chain


def _check_nesting(chain: list, events: dict, functions: dict):
    """Refuses a chain of more than MOST_CALL_DEPTH calls and clicks: each
    nests one event, and `click` nests 9 at most. The error names the
    deepest event or function of the chain."""
    if len(chain) - 1 <= MOST_CALL_DEPTH:
        return
    file, number = _owner_place(chain[-1], events, functions)
    raise NxwrightError("the calls and clicks %s nest %d deep; at most %d may, so "
                        "that a page change keeps room within the 9 `click` allows"
                        % (" -> ".join(_owner_label(owner) for owner in chain),
                           len(chain) - 1, MOST_CALL_DEPTH), file=file, line=number)


def _calls_in(lines: list, functions: dict) -> set:
    """Returns the names of the page's functions that `lines` call."""
    called = set()
    for number, text in lines:
        try:
            tokens = tokenize(split_line(text, number)[1], number)
        except NxwrightError:
            continue    # a command with unusual arguments: it calls nothing
        for position, (kind, name) in enumerate(tokens[:-1]):
            if kind == "name" and name in functions and tokens[position + 1][1] == "(":
                called.add(name)
    return called


def _longest_chains(names, callees: dict) -> dict:
    """Returns {name: the longest chain of `names` calling down to it, itself last}."""
    callers = {name: [caller for caller in names if name in callees.get(caller, ())]
               for name in names}
    chains = {}

    def chain(name: str) -> list:
        if name not in chains:
            longest = max((chain(caller) for caller in callers[name]), key=len, default=[])
            chains[name] = longest + [name]
        return chains[name]
    return {name: chain(name) for name in names}


def _place_functions(page: _PageState, callees: dict, depths: dict) -> list:
    """Gives each called function its call depth from `depths`, its depth's
    hotspot and "which function" global, and its index there; returns the
    hotspots in order.

    Raises NxwrightError for a call chain of more than MOST_CALL_DEPTH calls
    among all the functions, called or not, so that a library's functions are
    checked on every page. _check_nesting checks the page's own chains.
    """
    for name, chain in _longest_chains(list(page.functions), callees).items():
        if len(chain) > MOST_CALL_DEPTH:
            function = page.functions[name]
            raise NxwrightError("the calls %s nest %d deep; at most %d may, so "
                                "that a page change keeps room within the 9 `click` allows"
                                % (" -> ".join(chain), len(chain),
                                   MOST_CALL_DEPTH), file=function.file, line=function.number)
    by_depth = {}
    for name, function in page.functions.items():
        if name in depths:
            function.depth = depths[name]
            by_depth.setdefault(function.depth, []).append(function)
    hotspots = []
    for depth in sorted(by_depth):
        hotspot = page.generate(HOTSPOT_PREFIX, HOTSPOT, by_depth[depth][0].number)
        which = page.variable("", NUMBER, by_depth[depth][0].number)
        for index, function in enumerate(by_depth[depth]):
            function.hotspot, function.which, function.index = hotspot, which, index
        hotspots.append(hotspot)
    return hotspots


def _declare_function(page: _PageState, heading: str, number: int, file: str) -> Function:
    """Reads a function heading; _name_variables names its variables."""
    match = FUNCTION_SIGNATURE.fullmatch(heading)
    if not match:
        raise NxwrightError("a function is written function name(param: number, "
                            "other: text) -> number:", line=number)
    name, parameter_text, result = match.groups()
    if page.functions and name in page.functions:
        raise NxwrightError("function %s is defined twice" % name, line=number)
    page.check_new_name(name, number, "function")
    parameters = []
    for part in parameter_text.split(",") if parameter_text.strip() else []:
        parameter = PARAMETER.fullmatch(part)
        if not parameter:
            raise NxwrightError("a parameter is written name: number or name: text", line=number)
        if parameter[1] in [known for known, _ in parameters]:
            raise NxwrightError("parameter %s appears twice" % parameter[1], line=number)
        page.check_new_name(parameter[1], number, "parameter")
        parameters.append((parameter[1], parameter[2]))
    return Function(name, parameters, result, heading.strip()[:-1].rstrip(), number, file)


def _name_variables(page: _PageState, function: Function, kind: str):
    """Gives the function's parameters and result of `kind` their generated
    variables. Numbers get theirs before anything compiles. Text gets shared
    text variables when the function starts compiling, numbered with its own."""
    if not function.parameter_variables:
        function.parameter_variables = [""] * len(function.parameters)
    for index, (_, parameter_kind) in enumerate(function.parameters):
        if parameter_kind == kind:
            function.parameter_variables[index] = page.variable(SHARED_PREFIX, kind, function.number)
    if function.result == kind:
        function.result_variable = page.variable(SHARED_PREFIX, kind, function.number)


def _check_no_cycle(callees: dict, functions: dict):
    """Refuses functions calling themselves, directly or through others: each
    has one set of variables, which a second call would overwrite."""
    def refuse(cycle: list):
        name = cycle[0]
        raise NxwrightError("function %s calls itself (%s)" % (name, " -> ".join(cycle)),
                            file=functions[name].file, line=functions[name].number)
    _depth_first(functions, lambda name: sorted(callees.get(name, ())), refuse)


def compile_program(lines: list, program: ProgramNames) -> list:
    """Compiles program.nx's lines, its `const` lines left out (read them first
    with read_program_names). Its code cannot have locals or temporaries."""
    page = _PageState("program", (), program)
    kept = [(number, text) for number, text in lines
            if not _CONST_LINE.match(split_line(text, number)[1])
            and not _INCLUDE_LINE.match(split_line(text, number)[1])]
    _check_program_macros(kept, program.macros)
    return _EventCompiler(page, None, allow_locals=False).compile(kept)


def _check_program_macros(lines: list, macros: dict):
    """Refuses what program.nx's `call` lines would run that the build cannot
    follow: a macro that clicks, directly or through the macros it calls,
    since program.nx has no page; calls coming back to a macro already
    running; and a chain of more than MOST_CALL_DEPTH."""
    # program.nx's code stands in as an event, labelled program.nx.
    root = ("program", "nx")
    events = {root: ("program.nx", lines)}
    graph = {root: _macros_called_in(lines, macros)}
    _follow_macros(graph, macros, None, events)
    depths, deepest_caller = _depths(graph, _callees_first(graph, events, {}))
    _check_nesting(_deepest_chain(depths, deepest_caller), events, {})


def read_program_names(lines: list, included: list = ()) -> ProgramNames:
    """Returns the constants and `int` variables program.nx's lines declare,
    with the constants of the files it includes, `included` [(file, lines)].
    Errors name the file."""
    variables = set()
    with _naming("program.nx"):
        _read_int_names(lines, variables)
    page = _PageState("program", (), ProgramNames({}, frozenset(variables)))
    for file, file_lines in included:
        with _naming(file):
            _read_constants(file_lines, page)
    with _naming("program.nx"):
        _read_constants([(number, text) for number, text in lines
                         if _CONST_LINE.match(split_line(text, number)[1])], page)
    return ProgramNames(page.constants, frozenset(variables))


def _read_int_names(lines: list, variables: set):
    """Adds the names that the `int` lines among `lines` declare to `variables`."""
    for number, text in lines:
        declared = declared_int_names(split_line(text, number)[1])
        for name in declared:
            if name.startswith(GENERATED_PREFIX):
                raise NxwrightError("int %s may not start with %r, which "
                                    "generated variables use" % (name, GENERATED_PREFIX),
                                    line=number)
        variables.update(declared)


class _EventCompiler:
    """Compiles the lines of one event, one function's body, or program.nx,
    keeping a stack of the blocks open at each line."""

    def __init__(self, page: _PageState, temporaries, function: Function = None,
                 allow_locals: bool = True, written: dict = None):
        self.page, self.temporaries, self.allow_locals = page, temporaries, allow_locals
        self.function = function    # the function whose body this is, or None
        # An event's lines whose form '&name&' its owner replaced: {line
        # number: the code as written}, which a refusal of the line gives.
        self.written = written or {}
        self.scope = _Scope(page)
        if function:
            for (name, kind), variable in zip(function.parameters, function.parameter_variables):
                self.scope.locals[name] = Local(variable, kind)
        self.returned = False
        self.out = []
        # `stack` holds the open blocks. `pending` is a block whose head was
        # read, waiting for its "{" on the next line. After the "}" of an if
        # followed by else, `carry` is the "}" count (_Block.extra) the else takes over.
        self.stack, self.pending, self.carry = [], None, None
        self.carry_jumps = set()    # jumps of the closed blocks of the current if chain
        # A function's labels: {label as written: its name}, the labels
        # placed, and each goto as (line number, label).
        self.label_names, self.placed_labels, self.gotos = {}, set(), []

    def compile(self, lines: list) -> list:
        for position, (number, text) in enumerate(lines):
            self.line(number, text, lines[position + 1:])
        if self.pending or self.stack:
            raise NxwrightError("a block is not closed", line=lines[-1][0] if lines else 0)
        for number, label in self.gotos:
            if label not in self.placed_labels:
                raise NxwrightError("function %s has no label %s"
                                    % (self.function.name, label), line=number)
        if self.function and self.function.result and not self.returned:
            raise NxwrightError("function %s must end with return"
                                % self.function.name, line=self.function.number)
        return self.out

    def put(self, number: int, text: str):
        self.out.append((number, text))

    def put_lines(self, number: int, lines: list, comment: str):
        """Writes `lines`, compiled from the source line `number`, the last
        with that line's `comment`."""
        for line in lines[:-1]:
            self.put(number, line)
        self.put(number, lines[-1] + comment)

    def local_names(self) -> dict:
        """Returns {generated variable: nxlang name} of the locals and
        parameters the code declared, and of a function's result, named
        "(result)", which no nxlang name can be."""
        names = {local.variable: name for name, local in self.scope.locals.items()}
        if self.function is not None and self.function.result_variable:
            names[self.function.result_variable] = "(result)"
        return names

    def emitter(self, indent: str, number: int) -> _Emitter:
        """Returns an emitter for a new statement, which takes temporaries
        from the first again."""
        if self.temporaries is not None:
            self.temporaries.start_statement()
        return self.same_statement(indent, number)

    def same_statement(self, indent: str, number: int) -> _Emitter:
        """Returns an emitter for another part of the current statement."""
        return _Emitter(self.temporaries, indent, number, self.page.variables)

    def line(self, number: int, text: str, following: list):
        """Compiles one line. `following` holds the lines after it, for those
        that read ahead, such as a loop's head looking for `break`. A line
        whose form '&name&' was replaced is refused as the Nextion Editor
        reads it, the message giving the line as written first."""
        try:
            self._compile_line(number, text, following)
        except NxwrightError as error:
            written = self.written.get(number)
            if written is None or error.line != number:
                raise
            raise type(error)("%s, as the Nextion Editor reads it: %s" % (written, error.reason),
                              line=number, fix=error.fix) from None

    def _compile_line(self, number: int, text: str, following: list):
        indent, code, comment = split_line(text, number)
        _check_no_own_attribute(code, number, _IN_A_FUNCTION if self.function else _IN_NO_EVENT)
        if self.pending is not None and code != "{":
            raise NxwrightError("expected \"{\" on the line after if, while, for, or else",
                                line=number)
        if not code:
            self.put(number, text)
            return
        if code == "{":
            if self.pending is None:
                raise NxwrightError("\"{\" must follow if, while, for, or else", line=number)
            block, self.pending = self.pending, None
            if block.braces:
                self.put(number, text)
            self.enter(block, number, indent)
            return
        rest = code
        if rest.startswith("}"):
            rest = rest[1:].lstrip(" \t")
            self.close(number, indent, comment if not rest else "", rest, following)
            if not rest:
                return
        opens = rest.endswith("{")
        if opens:
            rest = rest[:-1].rstrip(" \t")
        bare = STRING_LITERAL.sub("", rest)
        if "{" in bare or "}" in bare:
            raise NxwrightError("\"{\" and \"}\" go at the start or end of a line", line=number)
        head = _NAME.match(rest)
        word = head[0] if head else ""
        if word == "else":
            self.else_head(number, indent, rest, comment, opens)
            return
        if not opens and (_CASE_LABEL.fullmatch(rest) or _DEFAULT_LABEL.fullmatch(rest)):
            self.case_label(number, indent, rest, comment)
            return
        self.guard(number, indent)
        heads = rest[len(word):].lstrip(" \t").startswith("(")
        if word in ("if", "while", "for") and heads:
            self.head(number, indent, word, rest, comment, opens, following)
        elif word == "switch" and heads:
            self.switch_head(number, indent, rest, comment, opens, following)
        elif opens:
            raise NxwrightError("\"{\" can only end an if, while, for, or else line",
                                line=number)
        else:
            self.statement(number, indent, rest, comment, following)

    def close(self, number: int, indent: str, comment: str, rest: str, following: list):
        """Compiles a "}", closing the innermost block. `rest` is what follows
        it on its line, which only else may be."""
        if not self.stack:
            raise NxwrightError("\"}\" closes no block", line=number)
        if self.stack[-1].kind == "case":
            self.close_case(number)
        block = self.stack.pop()
        for _ in range(block.guards):
            self.put(number, indent + "  }")
        for code in block.recompute:
            self.put(number, indent + "  " + code)
        if block.braces:
            self.put(number, indent + "}" + comment)
        elif comment:
            self.put(number, indent + comment.lstrip(" \t"))
        continues = rest.startswith("else") or (not rest and _next_is_else(following))
        if continues and block.kind != "if":
            raise NxwrightError("else must follow the block of an if", line=number)
        if rest and not rest.startswith("else"):
            raise NxwrightError("only else can follow \"}\" on its line", line=number)
        # Jumps that may have run inside leave the rest of the enclosing
        # blocks to skip, up to the loop or switch they leave.
        leaving = {jump for jump in block.jumps if jump[1] is not block}
        if continues:
            # The else block takes them over, and hands them on when it closes.
            self.carry, self.carry_jumps = block.extra, leaving
        else:
            for _ in range(block.extra):
                self.put(number, indent + "}")
            if leaving:
                self.stack[-1].jumps |= leaving
                self.stack[-1].pending |= leaving

    def guard(self, number: int, indent: str):
        """Before a statement: puts it inside an `if` when a jump may have run."""
        if not self.stack:
            return
        block = self.stack[-1]
        if block.kind == "switch":
            raise NxwrightError("code before the first case of a switch can never run", line=number)
        if block.pending:
            condition = "&&".join(sorted(flag + "==0" for flag, _ in block.pending))
            self.put(number, indent + "if(%s)" % condition)
            self.put(number, indent + "{")
            block.guards += 1
            block.pending = set()

    def head(self, number: int, indent: str, word: str, rest: str, comment: str, opens: bool,
             following: list):
        """Compiles the head of an if, while, or for. A loop holding its own
        `break` or `continue` gets a control variable."""
        tokens = tokenize(rest, number)[1:]
        brace = " {" if opens else ""
        flag = ""
        if word in ("while", "for") and any(_loop_jumps(following, opens)):
            self.need_page(number, "break or continue")
            flag = self.page.variable("_k", NUMBER, number)
        if word == "for":
            block = self.for_head(number, indent, tokens, comment, brace, flag)
        else:
            emitter = self.emitter(indent, number)
            condition = self.condition(tokens, number, emitter, flag)
            if flag:
                self.put(number, indent + flag + "=0")
            for line in emitter.lines:
                self.put(number, line)
            self.put(number, "%s%s(%s)%s%s" % (indent, word, condition, brace, comment))
            recompute = [line[len(indent):] for line in emitter.lines] if word == "while" else []
            block = _Block(word, recompute, flag=flag)
        if flag:
            block.on_open = [flag + "=0"]
        self.open(block, opens, number, indent)

    def for_head(self, number, indent, tokens, comment, brace, flag) -> _Block:
        """Compiles a for head into one Editor for line when it fits, else
        into its start and a while loop. Returns the block it opens."""
        start, condition_tokens, step_tokens = _split_for(tokens, number)
        # One statement: the three parts use different temporaries.
        init = self.emitter(indent, number)
        test = self.same_statement(indent, number)
        step = self.same_statement("", number)
        if start:
            self.statement_lines(start, number, init)
        condition = self.condition([("operator", "(")] + condition_tokens + [("operator", ")")],
                                   number, test, flag)
        if step_tokens:
            self.statement_lines(step_tokens, number, step)
        if (len(init.lines) <= 1 and not test.lines and len(step.lines) <= 1 and not flag
                and not _holds_semicolon_text(init.lines + [condition] + step.lines)):
            self.put(number, "%sfor(%s;%s;%s)%s%s" % (indent, "".join(init.lines)[len(indent):],
                                                      condition, "".join(step.lines), brace, comment))
            return _Block("for")
        # Not expressible in one for line, as when a part needs temporaries
        # or holds a text the Editor refuses there: the start, then a while
        # loop that runs the step and recomputes its condition's parts at the
        # end of each pass. After a break, the step does not run, as in C.
        if flag:
            self.put(number, indent + flag + "=0")
        for line in init.lines + test.lines:
            self.put(number, line)
        self.put(number, "%swhile(%s)%s%s" % (indent, condition, brace, comment))
        steps = step.lines
        if flag and steps:
            steps = ["if(%s!=2)" % flag, "{"] + ["  " + line for line in steps] + ["}"]
        return _Block("while", steps + [line[len(indent):] for line in test.lines], flag=flag)

    def need_page(self, number: int, what: str):
        """Refuses `what` in program.nx, which has no page to hold its variables."""
        if self.temporaries is None:
            raise NxwrightError("program.nx cannot use %s, which needs variables "
                                "only a page can hold" % what, line=number)

    def switch_head(self, number: int, indent: str, rest: str, comment: str, opens: bool,
                    following: list):
        """Compiles a switch head: puts its value in a variable of its own and
        sets its control variables. It reads its case labels ahead, to check
        them and, with a default, to know before the first case whether any
        case can match."""
        self.need_page(number, "switch")
        tokens = tokenize(rest, number)[1:]
        parser = Parser(_inside_parentheses(tokens, number), number, self.scope)
        expression = _whole_expression(parser)
        kind = kind_of(expression, number)
        emitter = self.emitter(indent, number)
        emitter.copy_results = _count_calls(expression) > 1
        value = self.page.variable(SHARED_PREFIX, kind, number)
        emitter.assign(value, kind, "=", expression)
        values, has_default = [], False
        for label_number, label in _switch_labels(following, opens):
            if _DEFAULT_LABEL.fullmatch(label):
                if has_default:
                    raise NxwrightError("a switch has one default at most", line=label_number)
                has_default = True
                continue
            case_value = self.case_value(label, label_number, kind)
            # Numbers compare by value in 32 bits, as C compares them: 1, 01,
            # and 0x1 are the same case, and so are -1 and 0xFFFFFFFF.
            same = int32(_number_value(case_value)) if kind == NUMBER else case_value
            if same in [int32(_number_value(known)) if kind == NUMBER else known
                        for known in values]:
                raise NxwrightError("case %s appears twice"
                                    % _CASE_LABEL.fullmatch(label)[1].strip(), line=label_number)
            values.append(case_value)
        flag, matched = (self.page.variable("_k", NUMBER, number) for _ in range(2))
        no_match = self.page.variable("_k", NUMBER, number) if has_default else ""
        for line in emitter.lines:
            self.put(number, line)
        self.put(number, indent + flag + "=0" + comment)
        self.put(number, indent + matched + "=0")
        if has_default:
            # default runs when no case can match: known before the first case.
            self.put(number, indent + no_match + "=1")
            for case_value in values:
                self.put(number, indent + "if(%s)" % self.case_test(number, indent, value,
                                                                     case_value))
                self.put(number, indent + "{")
                self.put(number, indent + "  " + no_match + "=0")
                self.put(number, indent + "}")
        block = _Block("switch", braces=False, flag=flag, switch=(value, matched, no_match, kind))
        self.open(block, opens, number, indent)

    def case_value(self, label: str, number: int, kind: str) -> str:
        """Returns the Editor text of a case's value: a number, text, or constant."""
        parser = Parser(tokenize(_CASE_LABEL.fullmatch(label)[1], number), number, self.scope)
        try:
            value = parser.whole_expression()
        except NotParsed:
            value = None
        if not isinstance(value, Literal) or value.text.startswith("@"):
            raise NxwrightError("a case holds a number, a text, or a constant", line=number)
        if value.kind != kind:
            raise NxwrightError("the case's value is not of the switch's kind", line=number)
        return value.text

    def case_test(self, number: int, indent: str, value: str, case_value: str) -> str:
        """Returns the test of a case, `value==case_value`. A case's text
        the Editor refuses in a condition (_refused_in_condition) is put
        into a text temporary first, on a line of its own."""
        if not _refused_in_condition(Literal(case_value, TEXT)):
            return "%s==%s" % (value, case_value)
        target = self.emitter(indent, number).temporary(TEXT)
        self.put(number, indent + target + "=" + case_value)
        return "%s==%s" % (value, target)

    def case_label(self, number: int, indent: str, label: str, comment: str):
        """Compiles a case or default label: closes the case before it, and
        opens the `if` that runs its code once a case has matched."""
        if self.stack and self.stack[-1].kind == "case":
            self.close_case(number)
        if not self.stack or self.stack[-1].kind != "switch":
            raise NxwrightError("case and default can only be in a switch", line=number)
        switch = self.stack[-1]
        value, matched, no_match, kind = switch.switch
        if _DEFAULT_LABEL.fullmatch(label):
            test = no_match + "==1"
        else:
            test = self.case_test(number, indent, value, self.case_value(label, number, kind))
        self.put(number, indent + "if(%s)%s" % (test, comment))
        self.put(number, indent + "{")
        self.put(number, indent + "  " + matched + "=1")
        self.put(number, indent + "}")
        # Its code runs once a case matched, falling through, until a jump.
        flags = sorted({flag for flag, _ in switch.jumps} | {switch.flag})
        self.put(number, indent + "if(%s)" % "&&".join([matched + "==1"]
                                                         + [flag + "==0" for flag in flags]))
        self.put(number, indent + "{")
        self.stack.append(_Block("case", indent=indent))
        # The jumps of earlier cases are tested above; none is pending here.
        switch.pending = set()

    def close_case(self, number: int):
        """Closes the current case's `if` blocks, and hands its jumps to the switch."""
        block = self.stack.pop()
        for _ in range(block.guards):
            self.put(number, block.indent + "  }")
        self.put(number, block.indent + "}")
        leaving = {jump for jump in block.jumps if jump[1] is not block}
        self.stack[-1].jumps |= leaving
        self.stack[-1].pending |= leaving

    def function_label(self, number: int, code: str) -> str:
        """Returns a function's label, or a goto in it, with the label
        renamed by _PageState.label. A label placed twice is refused here;
        a goto to a label the function lacks, once the function is read."""
        target = goto_label(code)
        label = target if target is not None else LABEL.fullmatch(code)[1]
        if target is not None:
            self.gotos.append((number, label))
        elif label in self.placed_labels:
            raise NxwrightError("%s: function %s holds this label twice"
                                % (label, self.function.name), line=number)
        else:
            self.placed_labels.add(label)
        if label not in self.label_names:
            self.label_names[label] = self.page.label()
        name = self.label_names[label]
        return "goto " + name if target is not None else name + ":"

    def data_record_call(self, number: int, indent: str, call, comment: str):
        """Compiles a call of a data record's method, `call` matching
        DATA_RECORD_CALL. The Editor takes each argument as one text or number
        (DATA_RECORD_ARGUMENTS), so one of more operands is computed into a
        temporary first. A number given for text becomes its digits, as in an
        assignment; text given for a number is refused."""
        name = "%s.%s" % (call[1], call[2])
        kinds = [TEXT if kind is str else NUMBER for kind in DATA_RECORD_ARGUMENTS[call[2]]]
        arguments = self.arguments(call[3], number)
        if len(arguments) != len(kinds):
            raise NxwrightError(method_count_refusal(name, len(kinds)), line=number)
        emitter = self.emitter(indent, number)
        emitter.copy_results = sum(_count_calls(argument) for argument in arguments) > 1
        operands = []
        for place, (argument, kind) in enumerate(zip(arguments, kinds), 1):
            given = kind_of(argument, number)
            if kind == NUMBER and given == TEXT:
                raise NxwrightError("argument %d of %s is a number, not a text" % (place, name),
                                    line=number)
            if kind == TEXT and given == NUMBER:
                text = emitter.temporary(TEXT)
                emitter.emit("covx %s,%s,0,0" % (emitter.value(argument), text))
                operands.append(text)
            else:
                operands.append(emitter.value(argument))
        emitter.emit("%s(%s)" % (name, ",".join(operands)))
        self.put_lines(number, emitter.lines, comment)

    def command_with_operands(self, number: int, indent: str, word: str, rest: str,
                              comment: str):
        """Compiles get, print, prints, or covx (ONE_OPERAND_FIRST), `rest`
        being its arguments. The Editor takes its first argument as one text
        or number, so one of more operands is computed into a temporary
        first. Its other numbers, prints' length and covx's length and form,
        the Editor takes as arithmetic, so they are written as such."""
        arguments = self.arguments(rest, number)
        emitter = self.emitter(indent, number)
        emitter.copy_results = sum(_count_calls(argument) for argument in arguments) > 1
        operands = [emitter.value(argument) if place == 0 or _is_atomic(argument)
                    else _render_chain(emitter.chain(argument))
                    for place, argument in enumerate(arguments)]
        emitter.emit("%s %s" % (word, ",".join(operands)))
        self.put_lines(number, emitter.lines, comment)

    def xstr_text_computed(self, number: int, indent: str, code: str, comment: str) -> bool:
        """Compiles an xstr whose text, its last argument, is more than one
        operand, which the Editor refuses there: computes the text into a
        temporary first, as command_with_operands computes a first
        argument, and writes the other arguments as substitute_command
        writes them. Returns False, writing nothing, when the text is one
        operand as the build's check reads it (code_checks.is_one_operand):
        the line is then written as any other command, as before."""
        start = _last_argument_start(code)
        if start is None or is_one_operand(code[start:]):
            return False
        text = code[start:]
        try:
            expression = Parser(tokenize(text, number), number, self.scope).whole_expression()
        except NotParsed as error:
            raise NxwrightError(error.reason, line=error.line) from None
        emitter = self.emitter(indent, number)
        operand = emitter.value(expression)
        spaces = text[:len(text) - len(text.lstrip())]
        emitter.emit(self.substitute_command(code[:start], number) + spaces + operand)
        self.put_lines(number, emitter.lines, comment)
        return True

    def arguments(self, text: str, number: int) -> list:
        """Returns the expressions of `text`, a call's or a command's
        arguments, separated by commas: none when it is empty."""
        if not text.strip():
            return []
        parser = Parser(tokenize(text, number), number, self.scope)
        arguments = []
        try:
            arguments.append(parser.expression())
            while parser.peek() == ",":
                parser.take()
                arguments.append(parser.expression())
            parser.expect_end()
        except NotParsed as error:
            raise NxwrightError(error.reason, line=error.line) from None
        return arguments

    def jump(self, number: int, indent: str, word: str, comment: str):
        """Compiles `break` or `continue`: sets the control variable of the
        loop or switch it leaves; the code after it is skipped by guard()."""
        kinds = ("while", "for", "switch") if word == "break" else ("while", "for")
        target = next((block for block in reversed(self.stack) if block.kind in kinds), None)
        if target is None:
            raise NxwrightError("%s can only be in a loop%s"
                                % (word, " or a switch" if word == "break" else ""), line=number)
        self.put(number, indent + "%s=%d" % (target.flag, 2 if word == "break" else 1) + comment)
        self.stack[-1].jumps.add((target.flag, target))
        self.stack[-1].pending.add((target.flag, target))

    def else_head(self, number: int, indent: str, rest: str, comment: str, opens: bool):
        """Compiles an else or else if line."""
        if self.carry is None:
            raise NxwrightError("else must follow the \"}\" of an if", line=number)
        extra, self.carry = self.carry, None
        jumps, self.carry_jumps = self.carry_jumps, set()
        brace = " {" if opens else ""
        tokens = tokenize(rest, number)[1:]
        if not tokens:
            self.put(number, indent + "else" + brace + comment)
            self.open(_Block("else", extra=extra, jumps=jumps), opens, number, indent)
            return
        if tokens[0][1] != "if":
            raise NxwrightError("expected else or else if", line=number)
        emitter = self.emitter(indent, number)
        condition = self.condition(tokens[1:], number, emitter)
        if not emitter.lines:
            self.put(number, "%selse if(%s)%s%s" % (indent, condition, brace, comment))
            self.open(_Block("if", extra=extra, jumps=jumps), opens, number, indent)
            return
        # Its parts must be computed between "else" and its "if", so the rest
        # of the chain nests inside an else block, closed when the chain ends.
        self.put(number, indent + "else")
        self.put(number, indent + "{")
        for line in emitter.lines:
            self.put(number, line)
        self.put(number, "%sif(%s)%s%s" % (indent, condition, brace, comment))
        self.open(_Block("if", extra=extra + 1, jumps=jumps), opens, number, indent)

    def open(self, block: _Block, opens: bool, number: int, indent: str):
        """Enters the block now when its head ends with "{", else waits for
        the "{" on the next line."""
        if opens:
            self.enter(block, number, indent)
        else:
            self.pending = block

    def enter(self, block: _Block, number: int, indent: str):
        """Starts a block, after its "{"."""
        block.indent = indent
        self.stack.append(block)
        for code in block.on_open:
            self.put(number, indent + "  " + code)

    def condition(self, tokens: list, number: int, emitter: _Emitter, flag: str = "") -> str:
        """Compiles a condition; with a loop's control variable `flag`, the
        condition first tests that no `break` ran."""
        parser = Parser(_inside_parentheses(tokens, number), number, self.scope)
        expression = _whole_expression(parser)
        if flag:
            expression = Binary("&&", Binary("!=", Literal(flag, NUMBER), Literal("2", NUMBER)),
                                expression)
        emitter.copy_results = _count_calls(expression) > 1
        return emitter.condition(expression)

    def statement(self, number: int, indent: str, code: str, comment: str, following: list):
        """Compiles a line that opens no block: an assignment, a call, var,
        return, break, continue, an `int` declaration, or a command."""
        word = _NAME.match(code)
        word = word[0] if word else ""
        if word == "const":
            raise NxwrightError("constants go at the top of the file, before the "
                                "first event", line=number)
        if word == "return":
            self.return_statement(number, indent, code, comment, following)
            return
        if code in ("break", "continue"):
            self.jump(number, indent, code, comment)
            return
        if word == "int":
            self.put(number, indent + _int_line(code) + comment)
            return
        if goto_label(code) is not None or LABEL.fullmatch(code):
            # A goto names a label, never a local or a constant to replace.
            # Labels outside a function are written as they are.
            written = self.function_label(number, code) if self.function is not None else code
            self.put(number, indent + written + comment)
            return
        if command_word(code) == "call":
            # A macro's name, never a local or a constant to replace. What
            # the macro runs is followed before compiling (_follow_macros).
            self.put(number, indent + code + comment)
            return
        call = DATA_RECORD_CALL.fullmatch(code)
        if call and call[1] in self.page.data_records:
            self.data_record_call(number, indent, call, comment)
            return
        command = command_word(code)
        if command in ONE_OPERAND_FIRST:
            self.command_with_operands(number, indent, command, code[len(command):], comment)
            return
        if command == "xstr" and self.xstr_text_computed(number, indent, code, comment):
            return
        emitter = self.emitter(indent, number)
        try:
            tokens = tokenize(code, number)
        except NxwrightError:
            if _CALL_START.match(code):
                raise
            tokens = None   # not an expression: a command with unusual arguments
        lines = self.statement_lines(tokens, number, emitter, code) if tokens else None
        if lines is None:
            self.put(number, indent + self.substitute_command(code, number) + comment)
            return
        self.put_lines(number, lines, comment)

    def statement_lines(self, tokens: list, number: int, emitter: _Emitter, code: str = None):
        """Compiles an assignment, ++, --, or var; returns its lines, or None
        when `tokens` are a command. In a for header (no `code`), anything else is refused."""
        if tokens and tokens[0][1] == "var":
            return self.declare(tokens, number, emitter)
        parser = Parser(tokens, number, self.scope)
        calls = code is not None and _CALL_START.match(code) is not None
        try:
            target = parser.primary() if tokens and tokens[0][0] == "name" else None
            if isinstance(target, Call) and parser.at_end():
                # A call as a statement: its result, if any, is not used.
                emitter.copy_results = _count_calls(target) > 1
                emitter.call(target)
                return emitter.lines
            operator = parser.peek()
            if target is None or not (operator == "=" or operator in COMPOUND_ASSIGNMENTS
                                      or operator in ("++", "--")):
                raise NotParsed("unexpected %r" % operator, line=number)
        except NotParsed as error:
            if calls:
                raise NxwrightError(error.reason, line=error.line) from None
            if code is None:
                raise NxwrightError("a for header holds assignments", line=number) from None
            return None
        parser.take()
        if isinstance(target, Literal):
            raise NxwrightError("a constant cannot be assigned", line=number)
        if isinstance(target, Call):
            raise NxwrightError("a call cannot be assigned to", line=number)
        target_text = emitter.atom(target)
        target_kind = kind_of(target, number)
        if operator in ("++", "--"):
            if not parser.at_end() or target_kind != NUMBER:
                raise NxwrightError("%s takes a number and nothing after it"
                                    % operator, line=number)
            emitter.emit(target_text + operator)
            return emitter.lines
        expression = _whole_expression(parser)
        emitter.copy_results = _count_calls(expression) + _count_calls(target) > 1
        emitter.assign(target_text, target_kind, operator, expression)
        return emitter.lines

    def return_statement(self, number: int, indent: str, code: str, comment: str,
                         following: list):
        function = self.function
        if function is None:
            raise NxwrightError("return can only be in a function", line=number)
        if function.result is None:
            raise NxwrightError("function %s has no result to return"
                                % function.name, line=number)
        if self.stack or any(split_line(text, line)[1] for line, text in following):
            raise NxwrightError("return must be the last line of the function, "
                                "outside any block", line=number)
        parser = Parser(tokenize(code, number)[1:], number, self.scope)
        expression = _whole_expression(parser)
        emitter = self.emitter(indent, number)
        emitter.copy_results = _count_calls(expression) > 1
        emitter.assign(function.result_variable, function.result, "=", expression)
        self.put_lines(number, emitter.lines, comment)
        self.returned = True

    def declare(self, tokens: list, number: int, emitter: _Emitter) -> list:
        """Compiles `var name = <expression>`; returns its lines."""
        if not self.allow_locals:
            raise NxwrightError("program.nx cannot have locals", line=number)
        if len(tokens) < 4 or tokens[1][0] != "name" or tokens[2][1] != "=":
            raise NxwrightError("a local is written var name = <expression>", line=number)
        name = tokens[1][1]
        if name in self.scope.locals:
            raise NxwrightError("local %s is declared twice" % name, line=number)
        self.page.check_new_name(name, number, "local")
        parser = Parser(tokens[3:], number, self.scope)
        expression = _whole_expression(parser)
        kind = kind_of(expression, number)
        local = Local(self.page.variable(SHARED_PREFIX, kind, number), kind)
        emitter.copy_results = _count_calls(expression) > 1
        emitter.assign(emitter.atom(local), kind, "=", expression)
        # Declared after its value, so "var x = x" cannot read itself.
        self.scope.locals[name] = local
        return emitter.lines

    def substitute_command(self, code: str, number: int) -> str:
        """Replaces locals and constants in a command's arguments, keeping its
        spacing. Their other values reach the Editor as written, so a
        conditional, which the Editor has not, is refused."""
        word = _NAME.match(code)
        start = word.end() if word else 0
        if "?" in STRING_LITERAL.sub("", code[start:]):
            raise NxwrightError("nxlang passes this line on as written, so ? : cannot be in "
                                "it; put the value in a local first", line=number)

        def replace(match) -> str:
            found = self.scope.lookup(match[2]) if match[2] else None
            if found is None:
                return match[0]
            return found.text if isinstance(found, Literal) else _Emitter(None, "", number).atom(found)

        def hex_number(match) -> str:
            # A minus right after an operand subtracts; any other is the number's sign.
            sign, written = match[1], match[2]
            if sign and not minus_is_sign(match.string[:match.start()]):
                return sign + editor_number(written)
            return editor_number(sign + written)

        def arguments(part: str) -> str:
            return _COMMAND_HEX.sub(hex_number, _COMMAND_NAME.sub(replace, part))
        return code[:start] + outside_strings(code[start:], arguments)


def editor_number(text: str) -> str:
    """Returns a number constant, as nxlang reads it, written so that the
    Editor's code reads it alike. `text` is decimal, or hexadecimal after
    0x, with or without a minus sign.

    nxlang reads numbers as C does, in 32 bits. The Editor reads hex digits
    in pairs, a byte each, and refuses hex past 32 bits or with a sign (the
    vendor's instruction set, rule 1.8, and compiling in the Editor). So a
    decimal number, and a hex one the Editor reads, is kept as written;
    otherwise:
      - hex past 32 bits keeps its low 32 bits, its last 8 digits, as C
        keeps them: 0x0100000005 is 0x00000005;
      - hex of an odd count of digits gains a leading zero: 0x1 is 0x01;
      - hex with a minus sign is written in decimal: -0x10 is -16, and
        -0xFFFFFFFF is 1, in 32 bits."""
    digits = text.lstrip("-")
    if not digits.startswith("0x"):
        return text
    digits = digits[2:]
    if int(digits, 16) > 0xFFFFFFFF:
        digits = digits[-8:]
    if len(digits) % 2:
        digits = "0" + digits
    if text.startswith("-"):
        return str(int32(-int(digits, 16)))
    return "0x" + digits


def _int_line(code: str) -> str:
    """Returns an `int` line as the Editor takes it. Whitespace after `int`
    holding a tab becomes one space: the Editor reads a tab there as part of
    the name. Each starting value written in hex is written in
    decimal, which the Editor refuses there (the vendor's rule 1.8), as
    editor_number reads it: `int mask=0x8005` is `int mask=32773`."""
    def decimal(match) -> str:
        return match[1] + str(int32(_number_value(editor_number(match[2] + match[3]))))
    return _INT_HEX_VALUE.sub(decimal, _INT_START.sub("int ", code, count=1))


def _number_value(text: str) -> int:
    """Returns the value of a number as written: decimal, or hexadecimal after 0x."""
    digits = text.lstrip("-")
    value = int(digits, 16) if digits.lower().startswith("0x") else int(digits, 10)
    return -value if text.startswith("-") else value


def _inner_lines(following: list, opens: bool):
    """Yields ([kinds of the blocks around it], line number, code) for each
    code line inside the block a head opens, `opens` telling whether its "{"
    is on the head's line. A kind is "loop", "switch", or "other"."""
    kinds, waiting, started = [], None, opens
    for number, text in following:
        code = split_line(text, number)[1]
        if not code:
            continue
        if not started:
            if code != "{":
                return
            started = True
            continue
        if code == "{":
            kinds.append(waiting or "other")
            waiting = None
            continue
        if code.startswith("}"):
            if not kinds:
                return
            kinds.pop()
            code = code[1:].lstrip(" \t")
            if not code:
                continue
        opens_line = code.endswith("{")
        if opens_line:
            code = code[:-1].rstrip(" \t")
        yield list(kinds), number, code
        word = _NAME.match(code)
        word = word[0] if word else ""
        heads = code[len(word):].lstrip(" \t").startswith("(")
        kind = ("loop" if word in ("while", "for") and heads else
                "switch" if word == "switch" and heads else
                "other" if word in ("if", "else") else None)
        if kind and opens_line:
            kinds.append(kind)
        elif kind:
            waiting = kind


def _loop_jumps(following: list, opens: bool) -> tuple:
    """Returns (whether a `break`, whether a `continue`) leaves the loop whose
    head comes just before `following`."""
    breaks = continues = False
    for kinds, _, code in _inner_lines(following, opens):
        if code == "break" and "loop" not in kinds and "switch" not in kinds:
            breaks = True
        if code == "continue" and "loop" not in kinds:
            continues = True
    return breaks, continues


def _switch_labels(following: list, opens: bool) -> list:
    """Returns [(line number, label)] of the `case` and `default` lines of a switch."""
    return [(number, code) for kinds, number, code in _inner_lines(following, opens)
            if not kinds and (_CASE_LABEL.fullmatch(code) or _DEFAULT_LABEL.fullmatch(code))]


def _next_is_else(following: list) -> bool:
    for number, text in following:
        code = split_line(text, number)[1]
        if code:
            return bool(re.match(r"else\b", code))
    return False


def _inside_parentheses(tokens: list, number: int) -> list:
    """Returns the tokens inside the parentheses that wrap all of `tokens`."""
    depth = 0
    for position, (kind, text) in enumerate(tokens):
        if kind == "operator" and text == "(":
            depth += 1
        elif kind == "operator" and text == ")":
            depth -= 1
        if depth == 0 and (position == 0 or position < len(tokens) - 1):
            raise NxwrightError("expected a condition in parentheses", line=number)
    if len(tokens) < 3:
        raise NxwrightError("expected a condition in parentheses", line=number)
    return tokens[1:-1]


def _split_for(tokens: list, number: int) -> list:
    """Returns the tokens of a for header's start, condition, and step."""
    parts, current, depth = [], [], 0
    try:
        inside = _inside_parentheses(tokens, number)
    except NxwrightError:
        raise NxwrightError("a for header is written for(start;condition;step)",
                            line=number) from None
    for kind, text in inside:
        if kind == "operator" and text in ("(", "["):
            depth += 1
        elif kind == "operator" and text in (")", "]"):
            depth -= 1
        if text == ";" and depth == 0:
            parts.append(current)
            current = []
        else:
            current.append((kind, text))
    parts.append(current)
    if len(parts) != 3:
        raise NxwrightError("a for header is written for(start;condition;step)", line=number)
    return parts
