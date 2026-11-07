"""Merging the Nextion Editor's code into a source folder's .nx files, when
a project is extracted into an existing folder in strict Nextion syntax. Each
event keeps the source text the folder has for it while that text still builds
to the Nextion Editor's code. keep_comfortable_events does this through
keep_comfortable_blocks, which the macros share (macros_source.py).

This module also switches a page's events to nxlang (switch_events_to_nxlang)."""
from dataclasses import replace

from nxwright import NxwrightError
from nxwright.language.code_lines import split_line
from nxwright.language.code_preprocessor import Owner, with_own_attributes
from nxwright.language.editor_code import editor_equivalent, keep_editor_meaning
from nxwright.language.nxlang import ProgramNames
from nxwright.language.resource_names import ResourceNames, UnknownNameError
from nxwright.project.device_settings import TextCodec
from nxwright.source.nx_files import EVENT_COMMENT_MARKER, event_blocks, event_heading, with_end
from nxwright.source.page_source import (compile_nxlang_page, editor_code_of_block, page_nx_path,
                                         preprocess_compiled)


def keep_comfortable_events(fresh_events: str, old_events: str, page_name: str,
                            names: ResourceNames, object_names: list) -> str:
    """Returns `fresh_events`, a .nx text made by import, with each event's
    block taken from `old_events` instead when the old block's code turns into
    the same Editor code. This keeps comfortable syntax and blank lines in
    events the Editor did not change.

    An old block that names a picture or font the app no longer lists counts
    as changed. `object_names` are the page's, in ID order, the page's
    first: an event's code may name its own object's attributes
    (code_preprocessor.with_own_attributes).

    Raises NxwrightError when any old block's code cannot be preprocessed for
    another reason.
    """
    path = page_nx_path(page_name)
    old_end = []
    old = event_blocks(old_events, path, end=old_end)
    return keep_comfortable_blocks(event_blocks(fresh_events, path), old,
                                   lambda key, block: editor_code_of_block(
                                       block, page_name, names, Owner.among(key[0], object_names)),
                                   lambda key: event_heading(*key), old_end)


def keep_comfortable_blocks(fresh: dict, old: dict, editor_code, heading, old_end: list) -> str:
    """Returns the text of `fresh`'s blocks, {key: EventBlock}, made by
    import, each block taken from `old` instead when the old block's code
    turns into the same Editor code, `editor_code(key, block)`; or the old block's
    code under the fresh comment, when only the comment changed. An old block
    that names a picture or font the app no longer lists counts as changed.
    `heading(key)` writes a block's heading. Shared by events and macros
    (macros_source.py). The comments above no heading of the old file stay:
    each before its block, and `old_end`, the old file's end, at the end."""
    old_code = {}
    for key, block in old.items():
        try:
            old_code[key] = editor_code(key, block)
        except UnknownNameError:
            old_code[key] = None
    out = []
    for key, block in fresh.items():
        code = [text for _, text in block.code_lines()]
        chosen = block if key not in old else replace(block, detached=old[key].detached)
        if old_code.get(key) == block.marked_comment() + code:
            chosen = old[key]
        elif old_code.get(key) is not None and _without_comment(old_code[key]) == code:
            # Only the comment changed: the code keeps its source.
            chosen = replace(old[key], comment=block.comment)
        out.append(chosen.text(heading(key)))
    return with_end("\n".join(out), old_end)


def _without_comment(code: list) -> list:
    """Returns Editor code without the marked comment lines it starts with."""
    start = 0
    while start < len(code) and code[start].startswith(EVENT_COMMENT_MARKER):
        start += 1
    return code[start:]


def switch_events_to_nxlang(events: str, page_name: str, names: ResourceNames,
                            component_names: list, program: ProgramNames,
                            object_types: dict = None, codec: TextCodec = None) -> str:
    """Returns a page's .nx text for nxlang: each line
    nxlang would read differently rewritten by keep_editor_meaning.
    `object_types` gives the types of the pages' objects nxlang compiles
    with, {page: {name: type}}, and `codec` the project's encoding
    (nxlang.compile_page).

    Raises NxwrightError when the result would not build to the same code.
    """
    page_path = page_nx_path(page_name)
    end = []
    blocks = event_blocks(events, page_path, end=end)
    chosen, editor = {}, {}
    for key, block in blocks.items():
        owner = Owner.among(key[0], component_names)
        editor[key] = editor_equivalent(
            _as_built(editor_code_of_block(block, page_name, names, owner), owner))
        chosen[key] = replace(block, lines=keep_editor_meaning(block.lines))
    if all(block.lines == chosen[key].lines for key, block in blocks.items()):
        text = events
    else:
        text = with_end("\n".join(block.text() for block in chosen.values()), end)
    compiled = compile_nxlang_page(text, page_name, component_names, program,
                                   object_types=object_types, codec=codec)
    _check_compiled(compiled, page_name, names, editor)
    return text


def _as_built(code: list, owner: Owner) -> list:
    """Returns an event's lines of Editor code with the form '&name&'
    replaced in each line's code part by `owner`, as nxlang builds them: the
    Nextion Editor's code holds the form as written. Without an owner, the
    lines are as they are. The comments are left alone."""
    if owner is None:
        return code
    out = []
    for text in code:
        indent, body, comment = split_line(text, 0)
        out.append(indent + with_own_attributes(body, owner) + comment)
    return out


def _check_compiled(compiled, page_name: str, names: ResourceNames, editor: dict):
    """Raises NxwrightError, naming the first line that differs, unless each
    event `editor` lists compiled to the Editor code `editor` gives for it."""
    got_all = preprocess_compiled(compiled, page_name, names)
    for key, want in editor.items():
        got = got_all[key]
        if got != want:
            # The first differing line; past the end of the shorter one, "".
            padded = max(len(got), len(want))
            first = next(pair for pair in zip(got + [""] * padded, want + [""] * padded)
                         if pair[0] != pair[1])
            path = compiled.sources.get(key, page_nx_path(page_name))
            raise NxwrightError("%s: %s.%s would not build to the same code in the nxlang "
                                "language (%r instead of %r)" % (path, *key, *first))
