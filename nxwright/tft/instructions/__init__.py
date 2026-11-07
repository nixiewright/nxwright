"""The control statements and the families of commands nxwright compiles, one
module each, named for what it covers: if_statement.py for `if` with its
`else if` and `else`, while_statement.py for `while`, for_statement.py for
`for`, drawing_commands.py for the drawing commands.

Each module has MATCHED, the list of what it matched with probes
(matching.py). A module of commands also has COMMANDS: {series' letter:
{command's name: statements.Command}}, where the statement encoder
(statements.py) finds each command a line starts with.

A module of a control statement, which spans several lines, has:

  - starts_statement(line) -> bool: whether `line` starts one;
  - encode_statement(lines, start, place, context, encode_run) -> (blocks,
    end): the blocks of the statement that starts at lines[start], and the
    index of the line after it. `context` is the compile's CompileContext
    (compile_context.py). `encode_run` is statements.encode_code, called
    with a list of lines, the place, and the context, which gives the
    blocks of the statement's bodies.

statements.encode_code asks each such module, in turn, whether a line
starts its statement. What the control statements share, their conditions,
bodies, and jumps, is in control_statements.py, outside this package, as
every module here keeps a MATCHED list.
"""
