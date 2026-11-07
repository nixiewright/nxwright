"""Switching the events of a page to nxlang (switch_events_to_nxlang)."""
from dataclasses import replace

from nxwright import NxwrightError
from nxwright.language.code_lines import split_line
from nxwright.language.code_preprocessor import Owner, with_own_attributes
from nxwright.language.editor_code import editor_equivalent, keep_editor_meaning
from nxwright.language.nxlang import ProgramNames
from nxwright.language.resource_names import ResourceNames
from nxwright.project.device_settings import TextCodec
from nxwright.source.nx_files import event_blocks, with_end
from nxwright.source.page_source import (compile_nxlang_page, editor_code_of_block, page_nx_path,
                                         preprocess_compiled)


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
