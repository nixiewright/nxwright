"""Turns a run of code's blocks back into lines of Nextion code, as the
statement encoder (statements.py), the control statements
(control_statements.py), and the commands (instructions/) write them.

An operand that refers to an attribute is the number of an entry, counted
across the project, and comes back as the object's name and the
attribute's, by the decoded file's entries: t0.txt for a component of the
run's own page, and page1.t0.txt for one of another page. An int operand
comes back as the variable's name. A label comes back with a plain name,
as the file keeps none.

Where the compile writes the same bytes for several forms of a line, such
as a number in decimal or in hexadecimal, the decoder writes the easiest to
read of those the compile encodes into the same bytes.

A block is the line's own text, as written, but for its operands, which the
encoder writes as tagged values (statements.py): an attribute's entry, a long
number, a system variable or a colour, an int variable, and a text in the
project's encoding. So a block comes back as a line by writing each tagged
value as its name, and every other byte as the character it is. A command
starts with its number and its table, which come back as its name, then a
space. A command whose arguments are kept as written, as printh's, keeps
them as its text.

A return is a 0 word, an empty block inside its run.

The control statements come back from their jumps (jumps.py), as the
statements' modules lay them out (control_statements.py, if_statement.py,
while_statement.py, and for_statement.py). A condition is a run of
comparisons. With `&&`, each jumps where the last does, past what the
condition guards. With `||`, each but the last jumps onto what it guards,
its comparison inverted.

What a condition guards ends between two statements. It ends where its
last comparison jumps to. It may also end at a jump block that goes on
there, since threaded() sends a jump that lands on a jump block on to where
that one lands. The block where it ends tells the statement:

  - a jump block back to the condition's first comparison ends a while's
    body, and the loop;
  - a jump block onward, the condition's jump landing right after it, ends
    a branch of an if. The rest of the if, from there to where that jump
    block lands, is its else, or its else if when it is one if alone;
  - otherwise, the if has no else.

Several statements give the same blocks, and the decoder writes one of
them: a for as its start, then a while whose body ends with its step;
`if(a){if(b){...}}` as `if(a&&b){...}`; and an else that holds one if alone
as an else if. A comparison's block that starts no statement, as the
undocumented command i writes one, comes back as that command. A label
comes back as `label` and its number, then a colon; a goto by the label
whose block lies just before the place it gives; and a call by the macro
whose run starts at the place it gives.
"""
import re
import struct

from nxwright.project.device_settings import TextCodec

from nxwright.tft.component_types import ENTRY_TAG, VALUE_TAG
from nxwright.tft.control_statements import COMPARISON_HEAD, COMPARISONS, INVERTED, JUMP_START
from nxwright.tft.decompiling import DecodeError, numbers, objects
from nxwright.tft.decompiling.decoded_file import CodeRun, DecodedFile
from nxwright.tft.decompiling.jumps import jump_targets
from nxwright.tft.instructions.call_statement import RETURN
from nxwright.tft.label_numbers import CALL_START, GOTO_START, S_BLOCK_START
from nxwright.tft.statements import (COMMAND_TAG, LONG_NUMBER, PROGRAM_VARIABLE_SIZE,
                              PROGRAM_VARIABLE_TAG, SYSTEM_VARIABLE_TAG, TEXT, series_commands)

# The tags of the operands the encoder writes, each followed by 4 bytes: an
# attribute's entry, a long or hexadecimal number, a system variable or a
# colour, and an int variable of program.s.
_TAGS = (ENTRY_TAG, VALUE_TAG, SYSTEM_VARIABLE_TAG, PROGRAM_VARIABLE_TAG)
_OPERAND_SIZE = 5
_QUOTE = ord('"')
_TEXT = re.compile(TEXT)
# A block's size word.
_SIZE_WORD = 4
# Each level of a body is indented this much, which the encoder drops.
_INDENT = "  "


def decoded_lines(run: CodeRun, page_id, decoded: DecodedFile,
                  attribute_of_entry=objects.attribute_of_entry) -> list:
    """Returns the lines of code of `run`, which belongs to the page
    `page_id`, or to no page, None, for program.s's and the macros' runs.
    Encoding the lines again where the run lies gives its blocks. Raises
    DecodeError for a block it cannot read. `attribute_of_entry(decoded,
    number)` names an attribute operand's entry, as
    objects.attribute_of_entry does."""
    parser = _Parser(_Reader(page_id, decoded, attribute_of_entry), run, decoded)
    statements, _ = parser.statements(0, lambda at: at == len(run.blocks))
    return _lines(statements, "")


class _Reader:
    """Reads the blocks of one run back into lines."""

    def __init__(self, page_id, decoded: DecodedFile, attribute_of_entry):
        self.page_id, self.decoded = page_id, decoded
        self.attribute_of_entry = attribute_of_entry
        self.codec = TextCodec(decoded.encoding)
        # The commands, system variables, and colours by the numbers of the
        # file's version, which an older Nextion Editor may give otherwise.
        numbered = numbers.commands(decoded.series, decoded.version)
        self.commands = {numbered[name]: (name, command)
                         for name, command in series_commands(decoded.series).items()
                         if name in numbered}
        operands = numbers.operands(decoded.series, decoded.version)
        self.named = {key: name for name, key in operands.items()}

    def line(self, block: bytes, place: int) -> str:
        """Returns the line of `block`, whose size word lies at `place`."""
        if not block:
            # A return is written as a 0 word, the same word that ends a run
            # (call_statement.py).
            return RETURN
        if block[0] == COMMAND_TAG:
            return self.command(block, place)
        # An assignment, or a command written by its name, as add.
        return self.text(block, place)

    def command(self, block: bytes, place: int) -> str:
        """Returns the line of a command's block: its name, then its
        arguments."""
        found = self.commands.get((block[1], block[2])) if len(block) >= 3 else None
        if found is None:
            raise DecodeError("no command of the %s series is this block's"
                              % self.decoded.series, place, block)
        name, command = found
        arguments = block[3:]
        if not arguments:
            return name
        if command.raw:
            return name + " " + self.codec.decode_keeping_bytes(arguments)
        return name + " " + self.text(arguments, place)

    def text(self, data: bytes, place: int) -> str:
        """Returns `data`, the block at `place` or the part of it after a
        command's head, as the line writes it: each tagged operand as its
        name, each text in the project's encoding, and every other byte as
        its character."""
        return "".join(piece for piece, _ in self.pieces(data, place))

    def pieces(self, data: bytes, place: int) -> list:
        """Returns the pieces of `data` as text() writes them, each as (its
        text, whether it is one byte's own character). So a comma among them
        is one that parts operands, not one inside a text."""
        pieces, at = [], 0
        while at < len(data):
            byte = data[at]
            if byte in _TAGS:
                if at + _OPERAND_SIZE > len(data):
                    raise DecodeError("an operand cut short", place, data[at:])
                pieces.append((self.operand(data[at:at + _OPERAND_SIZE], place), False))
                at += _OPERAND_SIZE
            elif byte == _QUOTE:
                end = self.text_end(data, at, place)
                pieces.append((self.codec.decode_keeping_bytes(data[at:end]), False))
                at = end
            elif 0x20 <= byte < 0x7f:
                pieces.append((chr(byte), True))
                at += 1
            else:
                raise DecodeError("a byte that is no part of a line", place, data[at:])
        return pieces

    def operand(self, data: bytes, place: int) -> str:
        """Returns the name of the tagged operand `data`, 5 bytes."""
        tag, number = data[0], struct.unpack("<I", data[1:])[0]
        if tag == VALUE_TAG:
            return _number(struct.unpack("<i", data[1:])[0])
        if tag == PROGRAM_VARIABLE_TAG:
            index, rest = divmod(number, PROGRAM_VARIABLE_SIZE)
            if rest or index >= len(self.decoded.ints):
                raise DecodeError("no int variable is this operand's", place, data)
            return self.decoded.ints[index].name.text
        if tag == SYSTEM_VARIABLE_TAG:
            name = self.named.get((data[1], data[2]))
            if name is None or data[3:] != b"\x00\x00":
                raise DecodeError("no system variable or colour of the %s series is this "
                                  "operand's" % self.decoded.series, place, data)
            return name
        try:
            page, page_object, attribute = self.attribute_of_entry(self.decoded, number)
        except KeyError:
            # attribute_of_entry knows no place: the operand's block gives it.
            raise DecodeError("no attribute's entry is this operand's", place, data) from None
        name = "%s.%s" % (page_object.name.text, attribute)
        # A component of another page is named after its page, as is any in
        # program.s and the macros, which have no page.
        if page.page_id != self.page_id:
            name = "%s.%s" % (page.objects[0].name.text, name)
        return name

    def text_end(self, data: bytes, start: int, place: int) -> int:
        """Returns where the text that starts at `start` ends, after its
        closing quote: at the first quote that closes a text the encoder
        writes, its characters read in the project's encoding. A byte of a
        character of two bytes may be a quote's or a backslash's, so the
        bytes alone do not tell."""
        for end in range(start + 1, len(data)):
            if data[end] == _QUOTE and _TEXT.fullmatch(
                    self.codec.decode_keeping_bytes(data[start:end + 1])):
                return end + 1
        raise DecodeError("a text without its closing quote", place, data[start:])


class _Parser:
    """Reads a run's blocks into statements: ("line", its text), ("if",
    [(condition, body)], else's body or None), and ("while", condition,
    body), each body a list of statements."""

    def __init__(self, reader: _Reader, run: CodeRun, decoded: DecodedFile):
        self.reader, self.blocks = reader, run.blocks
        self.places = run.block_places()
        self.end = (self.places[-1] + _SIZE_WORD + len(self.blocks[-1]) if self.blocks
                    else run.place)
        self.landings = dict(jump_targets(run))
        self.index = {place: at for at, place in enumerate(self.places)}
        self.comparisons = {number: comparison for comparison, number
                            in COMPARISONS[decoded.series].items()}
        # The place after each label's block, where a goto to it lands.
        self.labels = {self.place(at + 1): self.label(at) for at in range(len(self.blocks))
                       if self.numbered(at, S_BLOCK_START)}
        self.macros = {macro.code.place: macro.name.text for macro in decoded.macros}

    def place(self, at: int) -> int:
        """Returns where the block `at` lies, or the run's end past its last."""
        return self.places[at] if at < len(self.blocks) else self.end

    def jumps(self, at: int, head: bytes) -> bool:
        """Whether the block `at` starts with `head` and jumps (jumps.py)."""
        return (at < len(self.blocks) and self.blocks[at].startswith(head)
                and self.places[at] in self.landings)

    def reaches(self, place: int, target: int) -> bool:
        """Whether a jump to `place` reaches `target`: it is `target`, or a
        jump block lies there that goes on to it (threaded)."""
        at = self.index.get(place)
        return place == target or (at is not None and self.jumps(at, JUMP_START)
                                   and self.landings[place] == target)

    def statements(self, at: int, ends) -> tuple:
        """Returns (the statements from the block `at` up to the first
        block before which `ends(block)` holds, that block). Raises
        DecodeError when the run ends first."""
        found = []
        while not ends(at):
            if at >= len(self.blocks):
                raise DecodeError("a control statement without its end", self.end, b"")
            statement, at = self.statement(at)
            found.append(statement)
        return found, at

    def statement(self, at: int) -> tuple:
        """Returns (the statement at the block `at`, the block after it)."""
        block, place = self.blocks[at], self.places[at]
        if self.jumps(at, COMPARISON_HEAD):
            try:
                return self.control(at)
            except DecodeError:
                # A comparison's block that starts no statement is the
                # command i's, whose block it is too.
                return ("line", self.reader.command(block, place)), at + 1
        if self.jumps(at, JUMP_START):
            raise DecodeError("a jump block outside a control statement", place, block)
        if self.numbered(at, S_BLOCK_START):
            return ("line", self.label(at) + ":"), at + 1
        if self.numbered(at, GOTO_START):
            name = self.labels.get(_number_of(block))
            if name is None:
                raise DecodeError("a goto to no label of its run", place, block)
            return ("line", "goto " + name), at + 1
        if self.numbered(at, CALL_START):
            name = self.macros.get(_number_of(block))
            if name is None:
                raise DecodeError("a call of no macro", place, block)
            return ("line", "call " + name), at + 1
        return ("line", self.reader.line(block, place)), at + 1

    def numbered(self, at: int, head: bytes) -> bool:
        """Whether the block `at` is `head`, then a number: a label's, a
        goto's, or a call's (label_numbers.py)."""
        block = self.blocks[at]
        return (len(block) == len(head) + _OPERAND_SIZE and block.startswith(head)
                and block[len(head)] == VALUE_TAG)

    def label(self, at: int) -> str:
        """Returns the name of the label whose block is the block `at`."""
        return "label%d" % _number_of(self.blocks[at])

    def control(self, at: int) -> tuple:
        """Returns (the if or while whose condition starts at the block
        `at`, the block after it). It tries the longest condition first, as
        `if(a){if(b){...}}` gives the blocks of `if(a&&b){...}`. Raises
        DecodeError when no condition starts one."""
        most = at
        while self.jumps(most, COMPARISON_HEAD):
            most += 1
        for count in range(most - at, 0, -1):
            for join in (("&&", "||") if count > 1 else (None,)):
                if self.joined(at, count, join):
                    try:
                        return self.guarded(at, count, join)
                    except DecodeError:
                        continue
        raise DecodeError("comparisons that start no if or while", self.places[at],
                          self.blocks[at])

    def joined(self, at: int, count: int, join) -> bool:
        """Whether the `count` comparisons from the block `at` jump as a
        condition joined by `join` does."""
        # The last comparison's jump may land before the condition, when a
        # loop's jump back sends it on (threaded): guarded() finds where what
        # the condition guards ends.
        last = at + count - 1
        guarded, failed = self.place(last + 1), self.landings[self.places[last]]
        landings = [self.landings[self.places[number]] for number in range(at, last)]
        if join == "&&":
            return all(landing == failed for landing in landings)
        if join == "||":
            return all(self.reaches(guarded, landing) for landing in landings)
        return True

    def guarded(self, at: int, count: int, join) -> tuple:
        """Returns (the if or while of the condition of the `count`
        comparisons from the block `at`, joined by `join`, the block after
        it), by where what the condition guards ends (the module's
        docstring)."""
        last = at + count - 1
        condition = self.condition(at, count, join)
        start, failed = self.places[at], self.landings[self.places[last]]

        def lands_after(number: int) -> bool:
            # The condition's jump lands right after the block `number`.
            return self.reaches(self.place(number + 1), failed)

        def ends(number: int) -> bool:
            return (self.jumps(number, JUMP_START) and lands_after(number)
                    or self.reaches(self.place(number), failed))

        body, end = self.statements(last + 1, ends)
        if self.jumps(end, JUMP_START) and lands_after(end):
            landing = self.landings[self.places[end]]
            if landing == start:
                return ("while", condition, body), end + 1
            # A branch's jump past the rest of its if, which lands before it
            # when a loop's jump back sends it on.
            rest, after = self.statements(
                end + 1, lambda number: self.reaches(self.place(number), landing))
            if len(rest) == 1 and rest[0][0] == "if":
                return ("if", [(condition, body)] + rest[0][1], rest[0][2]), after
            return ("if", [(condition, body)], rest), after
        if not self.reaches(self.place(end), failed):
            raise DecodeError("a condition whose jump lands inside what it guards",
                              self.places[at], self.blocks[at])
        return ("if", [(condition, body)], None), end

    def condition(self, at: int, count: int, join) -> str:
        """Returns the condition of the `count` comparisons from the block
        `at`, joined by `join`. With `||`, each but the last is inverted."""
        written = [self.comparison(number, join == "||" and number < at + count - 1)
                   for number in range(at, at + count)]
        return (join or "").join(written)

    def comparison(self, at: int, inverted: bool) -> str:
        """Returns the comparison of the block `at`: its two operands around
        its operator, by its number, which `inverted` gives as 7 minus it."""
        block, place = self.blocks[at], self.places[at]
        # 09 00 04, the two operands between commas, then a comma, the
        # comparison's number, a comma, and the jump. The number holds no
        # comma, so the last one before it parts it from the operands.
        sides, _, number = block[len(COMPARISON_HEAD):-_OPERAND_SIZE - 1].rpartition(b",")
        operator = None
        if number.isdigit():
            operator = self.comparisons.get(INVERTED - int(number) if inverted
                                            else int(number))
        pieces = self.reader.pieces(sides, place)
        comma = next((number for number, piece in enumerate(pieces) if piece == (",", True)),
                     None)
        if operator is None or comma is None:
            raise DecodeError("a comparison the decoder cannot read", place, block)
        return ("".join(piece for piece, _ in pieces[:comma]) + operator
                + "".join(piece for piece, _ in pieces[comma + 1:]))


def _number_of(block: bytes) -> int:
    """Returns the number a label's, a goto's, or a call's block ends with."""
    return struct.unpack("<i", block[-4:])[0]


def _lines(statements: list, indent: str) -> list:
    """Returns the lines of `statements`, each body indented one level more
    than its statement, which the encoder reads alike."""
    lines = []
    for statement in statements:
        kind = statement[0]
        if kind == "line":
            lines.append(indent + statement[1])
        elif kind == "while":
            lines.append("%swhile(%s)" % (indent, statement[1]))
            lines += [indent + "{"] + _lines(statement[2], indent + _INDENT) + [indent + "}"]
        else:
            _, branches, otherwise = statement
            for number, (condition, body) in enumerate(branches):
                lines.append(("%sif(%s)" if number == 0 else "%s}else if(%s)")
                             % (indent, condition))
                lines += [indent + "{"] + _lines(body, indent + _INDENT)
            if otherwise is not None:
                lines += [indent + "}else", indent + "{"] + _lines(otherwise, indent + _INDENT)
            lines.append(indent + "}")
    return lines


def _number(value: int) -> str:
    """Returns how a line writes `value`, a number the encoder stored as 03
    and 4 bytes. Its decimal is the easiest form to read, and is written as
    it is when it has 4 characters or more. A shorter one came from a
    hexadecimal number, or from a decimal with zeros before it. So it is
    written with zeros up to 4 characters, which the encoder stores the same
    way: 18 is 0018, and -5 is -005."""
    written = str(value)
    if len(written) >= LONG_NUMBER:
        return written
    if value < 0:
        return "-" + str(-value).zfill(LONG_NUMBER - 1)
    return written.zfill(LONG_NUMBER)
