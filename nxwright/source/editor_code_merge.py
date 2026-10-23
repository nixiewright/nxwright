"""Merging the Nextion Editor's code into a source folder's .nx files, when
a project is extracted into an existing folder. Each event keeps the source
text the folder has for it while that still builds to the Editor's code.

In the Editor's own language, keep_comfortable_events does it, through
keep_comfortable_blocks, which the macros share (macros_source.py). In
nxlang, an event the Editor changed is merged into the .nx file holding it,
which several pages may include (nxlang_import_changes,
merge_nxlang_imports, check_nxlang_imports).

Also switching a page's events to nxlang (switch_events_to_nxlang), which
checks its result as the merge does."""
from dataclasses import dataclass, field, replace

from nxwright import NxwrightError
from nxwright.language.code_lines import split_line
from nxwright.language.code_preprocessor import Owner, with_own_attributes
from nxwright.language.editor_code import (editor_equivalent, keep_editor_meaning, uses_generated,
                                           without_touch_off)
from nxwright.language.nxlang import ProgramNames
from nxwright.language.resource_names import ResourceNames, UnknownNameError
from nxwright.source.nx_files import (EVENT_COMMENT_MARKER, PageFiles, event_blocks,
                                      read_page_files, render, with_end)
from nxwright.source.page_source import (compile_nxlang_page, compile_page_files,
                                         editor_code_of_block, page_nx_path, preprocess_compiled)


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
                                   lambda key: "on %s.%s:" % key, old_end)


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


# A page's vote, in merge_nxlang_imports, to leave an event as it is.
_KEPT = "kept"


@dataclass
class ImportChanges:
    """What extracting changes in one page's .nx files to take in the Editor's
    code. The first fields are what check_nxlang_imports needs to compile the
    page again."""
    page_name: str
    page_files: PageFiles
    component_names: list
    program: ProgramNames
    page_id: int
    object_types: dict                           # the pages' object types nxlang compiles with
    changes: dict = field(default_factory=dict)  # {file: {key: EventBlock, or None to remove it}}
    kept: dict = field(default_factory=dict)     # {file: {keys of events left as they are}}
    editor: dict = field(default_factory=dict)   # {key: the Editor's code of an event it changed}


def nxlang_import_changes(fresh_events: str, page_name: str, page_files: PageFiles,
                          names: ResourceNames, component_names: list, program: ProgramNames,
                          generated_events: dict, page_id: int,
                          object_types: dict = None) -> ImportChanges:
    """Returns what extracting changes in one page's .nx files in nxlang: the
    counterpart of keep_comfortable_events. An event keeps its source when
    that compiles to the Editor's code. An event the Editor changed takes the
    Editor's code, with keep_editor_meaning's parentheses, in the file holding
    it. One the Editor emptied is removed there; one it added goes into the
    page's own file.
    `generated_events` holds the code of the generated components' events
    (strip_generated): the functions' bodies. `page_id` is the page's number
    when the project was built. `object_types` gives the types of the
    pages' objects nxlang compiles with, {page: {name: type}}
    (nxlang.compile_page).

    Raises NxwrightError when the Editor changed a function's body, or an
    event that names a generated component or global (both were compiled
    from nxlang, so the change must be made in the source folder).
    """
    page_path = page_nx_path(page_name)
    result = ImportChanges(page_name, page_files, component_names, program, page_id,
                           object_types)
    old_code, compiled = {}, None
    try:
        compiled = compile_page_files(page_files, page_name, component_names, program, page_id,
                                      object_types)
        old_code = preprocess_compiled(compiled, page_name, names, unknown_as_none=True)
    except UnknownNameError:
        pass    # it names a picture or font the app no longer lists: every event counts as changed
    hotspots = {}
    for name, function in (compiled.functions if compiled else {}).items():
        hotspots.setdefault(function.hotspot, []).append(name)
    for hotspot, function_names in hotspots.items():
        old_body = old_code.get((hotspot, "down"))
        # A body naming a picture or font the app no longer lists cannot be
        # compared; the build reports the missing name.
        if old_body is not None and generated_events.get((hotspot, "down")) != old_body:
            raise NxwrightError("%s: the Nextion Editor changed function %s (the event of %s); "
                                "make the change in the source folder instead"
                                % (page_path, " or ".join(function_names), hotspot))
    fresh = event_blocks(fresh_events, page_path)
    for key, block in fresh.items():
        code = [text for _, text in block.code_lines()]
        fresh_code = block.marked_comment() + code
        home = page_files.homes.get(key)
        path = home.path if home else page_path
        if old_code.get(key) == fresh_code:
            # An event with no block in the source is a load event holding only
            # the build's tsw lines: there is nothing to keep.
            if home:
                result.kept.setdefault(path, set()).add(key)
            continue
        if home and old_code.get(key) is not None and _without_comment(old_code[key]) == code:
            # Only the comment changed: the code keeps its source.
            result.changes.setdefault(path, {})[key] = replace(home.blocks[key],
                                                               comment=block.comment)
            result.editor[key] = editor_equivalent(
                _as_built(fresh_code, Owner.among(key[0], component_names)))
            continue
        lines = block.lines
        if key == (page_name, "load"):
            # The build adds the tsw lines at its start again; the rest is the
            # Editor's code.
            kept = without_touch_off(code)
            lines = _drop_code_lines(lines, len(code) - len(kept))
            fresh_without = kept
        else:
            fresh_without = code
        generated = uses_generated(fresh_without)
        if generated:
            raise NxwrightError("%s: the Nextion Editor changed %s.%s, which was compiled from "
                                "nxlang (it uses the generated variable %s); make "
                                "the change in the source folder instead"
                                % (path, *key, generated))
        # The comment above no heading before the old block stays before it.
        old = home.blocks.get(key) if home else None
        result.changes.setdefault(path, {})[key] = replace(
            block, lines=keep_editor_meaning(lines), detached=old.detached if old else [])
        result.editor[key] = editor_equivalent(
            _as_built(fresh_code, Owner.among(key[0], component_names)))
    for key, home in page_files.homes.items():
        if key[0] is not None and key not in fresh:
            result.changes.setdefault(home.path, {})[key] = None
    return result


def merge_nxlang_imports(pages: list) -> dict:
    """Returns {file: new text} for the .nx files the pages' ImportChanges
    change. A file several pages include changes only where they all agree.

    Raises NxwrightError when the Editor left one event of a shared file
    different between the pages including it: writing either version would
    change the other pages' build.
    """
    files, votes = {}, {}
    for page in pages:
        for nx_file in page.page_files.files:
            files.setdefault(nx_file.path, nx_file)
        for path, keys in page.kept.items():
            for key in keys:
                votes.setdefault(path, {}).setdefault(key, []).append((page.page_name, _KEPT))
        for path, blocks in page.changes.items():
            for key, block in blocks.items():
                votes.setdefault(path, {}).setdefault(key, []).append((page.page_name, block))
    texts = {}
    for path, by_key in votes.items():
        blocks, changed = dict(files[path].blocks), False
        for key, page_votes in by_key.items():
            forms = {_vote_form(vote) for _, vote in page_votes}
            if len(forms) > 1:
                page_names = " and ".join(sorted(page for page, _ in page_votes))
                raise NxwrightError("%s: the Nextion Editor left %s.%s different between pages "
                                    "%s; make the change in the source folder instead"
                                    % (path, *key, page_names))
            vote = page_votes[0][1]
            if vote is _KEPT:
                continue
            changed = True
            if vote is None:
                blocks.pop(key, None)
            else:
                blocks[key] = vote
        if changed:
            texts[path] = render(files[path], blocks)
    return texts


def _vote_form(vote) -> str:
    """Returns a page's vote in a form that compares across pages: _KEPT,
    "removed", or the block's text."""
    if vote is _KEPT:
        return _KEPT
    return "removed" if vote is None else vote.text()


def check_nxlang_imports(pages: list, texts: dict, read, names: ResourceNames):
    """Checks that each page still builds with the new texts of its .nx files,
    and builds every event it took from the Editor to the Editor's code.
    `texts` holds the files that change; `read` gives the others. Every page
    is checked, since a file it shares may have changed for another page's
    sake.

    Raises NxwrightError naming the file at fault.
    """
    def read_new(path: str) -> str:
        return texts[path] if path in texts else read(path)
    for page in pages:
        path = page_nx_path(page.page_name)
        page_files = read_page_files(path, read_new(path), read_new)
        compiled = compile_page_files(page_files, page.page_name, page.component_names,
                                      page.program, page.page_id, page.object_types)
        _check_compiled(compiled, page.page_name, names, page.editor)


def _drop_code_lines(lines: list, count: int) -> list:
    """Returns a block's lines without its first `count` code lines."""
    out = []
    for number, text in lines:
        if count and text.strip():
            count -= 1
            continue
        out.append((number, text))
    return out


def switch_events_to_nxlang(events: str, page_name: str, names: ResourceNames,
                            component_names: list, program: ProgramNames,
                            object_types: dict = None) -> str:
    """Returns a page's .nx text for nxlang: each line
    nxlang would read differently rewritten by keep_editor_meaning.
    `object_types` gives the types of the pages' objects nxlang compiles
    with, {page: {name: type}} (nxlang.compile_page).

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
                                   object_types=object_types)
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
