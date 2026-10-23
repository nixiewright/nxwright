"""Answers a code editor speaking the Language Server Protocol, through pygls.

pygls carries the protocol: the messages and their framing; initialize,
shutdown, and exit; the files open in the editor, and their changes; the
editor's units of a column, which it agrees with the editor; and the
routing of each request to its answer. The server answers:
  - the notifications textDocument/didOpen, didChange, and didClose, and
    workspace/didChangeWatchedFiles, by which the editor tells of changes on
    disk: once changes pause, the server checks what they may affect, and
    sends textDocument/publishDiagnostics (live_checks.py).
  - textDocument/definition, with the places defining the name at a
    position (source/definitions.py), and textDocument/references, with
    the places using it (source/references.py).
  - textDocument/documentSymbol, with a file's outline, and
    workspace/symbol, with the names found across the source folders of
    the open files (symbols.py).
  - textDocument/hover (hovers.py), textDocument/completion, and
    textDocument/signatureHelp (completion.py).
  - textDocument/formatting, which formats a .nx file (source/formatting.py),
    and textDocument/rename (rename.py).
  - nxwright's own requests, each named nxwright/ and a word, for what
    nxwright adds to the editor: a page's measures against the build's
    limits, the Editor code a .nx file compiles to, the page preview, the
    properties panel and the page's editing, the Fonts panel, the font and
    media viewers, the panel switching to nxlang, and the side bar's
    sections.
    NxwrightServer.__init__'s table lists them, each with the method
    answering it, whose docstring says what it answers.
A request refused, as a rename that would break the build, gets the
protocol's "request failed" error, whose message the editor shows; one before
initialize, "server not initialized"; one for anything else, "method not
found". An unexpected error in answering a request gets "internal error",
its trace going to standard error, which editors show in their log; one in a
notification, pygls shows in the editor.

nxwright's own code counts a line's columns in Python's characters. The
server takes and gives them in the editor's units, UTF-16 unless the editor
offers another.

Each request reads the source folder afresh: its open files as the editor
has them, the others from disk (file_texts.py). So a change made outside the
editor, such as an extract, is always seen.
"""
import asyncio
from pathlib import Path

import attrs
from lsprotocol import types
from lsprotocol.converters import get_converter
from pygls.exceptions import JsonRpcException, JsonRpcServerNotInitialized
from pygls.lsp.server import LanguageServer
from pygls.protocol import LanguageServerProtocol

from nxwright import NxwrightError, installed_version

from nxwright.language_server.completion import completions, signature
from nxwright.source.definitions import definitions
from nxwright.language_server.file_texts import FileTexts, path_of, uri_of
from nxwright.source.folder_index import FolderIndex, Place, find_source_folder
from nxwright.language_server.font_panel import (FontPanelAnswers, font_file_details,
                                                 font_file_sample, requested_font_file,
                                                 typeface_sample)
from nxwright.language_server.font_panel import add as add_font_to_folder
from nxwright.language_server.hovers import hover
from nxwright.language_server.live_checks import LiveChecks
from nxwright.language_server.media_viewer import media_frames
from nxwright.language_server.nxlang_switch import nxlang_switch
from nxwright.language_server.page_editing import (component_events, default_event,
                                                   key_binding, properties)
from nxwright.source.page_edits import attribute_edits
from nxwright.language_server.page_components import (add_component, clear_events,
                                                       component_types, copy_components,
                                                       delete_components, group_components,
                                                       lock_components, paste_components,
                                                       paste_parts, place_components,
                                                       reorder_components)
from nxwright.testing.preview import Previews, page_of_file
from nxwright.language_server.quick_fixes import quick_fix
from nxwright.source.references import references
from nxwright.language_server.symbols import file_symbols, folder_symbols
from nxwright.language_server.rename import rename
from nxwright.source.formatting import format_folder
from nxwright.source.page_source import page_toml_path
from nxwright.project.device_settings import DEFAULT_ENCODING, ENCODINGS, DeviceSettings
from nxwright.project.screen_copy import ROTATIONS
from nxwright.project.screen_models import MODELS, model_named
from nxwright.language.nxlang_samples import MORE_FEATURES, panel_sections
from nxwright.language.resource_names import LISTS
from nxwright.source.source_folder import (LANGUAGES, NXLANG, SOURCE_FORMAT, add_page, app_name,
                                           new_source_folder, read_app, read_folder_source)
from nxwright.source.keyboard_adding import add_keyboard, chinese_keyboard_fonts
from nxwright.source.upgrade import folder_format

# How long changes must pause, in seconds, before the server checks them.
CHECK_PAUSE = 0.5
# The start of the names of nxwright's own requests.
_OWN = "nxwright/"
# Turns the protocol's objects, such as a problem a request gives, back into data.
_CONVERTER = get_converter()


class RequestFailed(JsonRpcException):
    """A request refused for a reason the editor shows, as a rename that
    would break the build."""
    CODE = types.LSPErrorCodes.RequestFailed


@attrs.define
class _OwnRequest:
    """One of nxwright's own requests, its params kept as JSON gives them,
    dicts and lists, which its answers read. pygls would read those of a
    request it has no type for into objects of its own."""
    id: int | str
    method: str
    jsonrpc: str
    params: dict = attrs.field(factory=dict)


class _Protocol(LanguageServerProtocol):
    """pygls's protocol, reading nxwright's own requests, those the server
    registers, as _OwnRequest; its own notifications, such as
    nxwright/checked, it sends as pygls sends any."""

    def get_message_type(self, method: str):
        if method.startswith(_OWN) and method in self.fm.features:
            return _OwnRequest
        return super().get_message_type(method)


class NxwrightServer(LanguageServer):
    """The language server: pygls's, with nxwright's answers. `shut_down` is
    True once the editor has asked it to shut down, as the protocol asks
    before it exits."""

    def __init__(self):
        super().__init__("nxwright", installed_version(), protocol_cls=_Protocol)
        self._texts = FileTexts(lambda: self.workspace)
        self._checks = LiveChecks(self._texts, self, self._units)
        self._previews = Previews()
        self._font_panel = FontPanelAnswers()
        self._initialized = False
        self.shut_down = False
        self._pause = None          # the checks to run once changes pause

        self._follows(types.INITIALIZE, self._on_initialize)
        self._follows(types.SHUTDOWN, self._on_shutdown)
        for notification in (types.TEXT_DOCUMENT_DID_OPEN, types.TEXT_DOCUMENT_DID_CHANGE,
                             types.TEXT_DOCUMENT_DID_CLOSE):
            self._follows(notification, self._on_document_change)
        self._follows(types.WORKSPACE_DID_CHANGE_WATCHED_FILES, self._on_files_change)

        self._answers(types.TEXT_DOCUMENT_DEFINITION, self._definition)
        self._answers(types.TEXT_DOCUMENT_REFERENCES, self._references)
        self._answers(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL, self._document_symbols)
        self._answers(types.WORKSPACE_SYMBOL, self._workspace_symbols)
        self._answers(types.TEXT_DOCUMENT_HOVER, self._hover)
        self._answers(types.TEXT_DOCUMENT_COMPLETION, self._completion,
                      types.CompletionOptions(trigger_characters=[".", '"']))
        self._answers(types.TEXT_DOCUMENT_SIGNATURE_HELP, self._signature_help,
                      types.SignatureHelpOptions(trigger_characters=["(", ","]))
        self._answers(types.TEXT_DOCUMENT_FORMATTING, self._formatting)
        self._answers(types.TEXT_DOCUMENT_RENAME, self._rename)
        self._answers(types.TEXT_DOCUMENT_CODE_ACTION, self._code_actions,
                      types.CodeActionOptions(code_action_kinds=[types.CodeActionKind.QuickFix]))
        for method, answer in {"limits": self._limits,
                               "editorCode": self._editor_code,
                               "pageDrawing": self._page_drawing,
                               "pageObjects": self._page_objects,
                               "componentProperties": self._component_properties,
                               "setAttributes": self._set_attributes,
                               "defaultEvent": self._default_event,
                               "componentEvents": self._component_events,
                               "keyBinding": self._key_binding,
                               "addKeyboard": self._add_keyboard,
                               "chineseKeyboardFonts": self._chinese_keyboard_fonts,
                               "componentTypes": self._component_types,
                               "addComponent": self._add_component,
                               "deleteComponents": self._delete_components,
                               "clearEvents": self._clear_events,
                               "copyComponents": self._copy_components,
                               "pasteComponents": self._paste_components,
                               "pasteParts": self._paste_parts,
                               "placeComponents": self._place_components,
                               "reorderComponents": self._reorder_components,
                               "lockComponents": self._lock_components,
                               "groupComponents": self._group_components,
                               "fonts": self._fonts,
                               "typefaces": self._typefaces,
                               "fontSample": self._font_sample,
                               "fontFile": self._font_file,
                               "mediaFrames": self._media_frames,
                               "nxlangSamples": self._nxlang_samples,
                               "nxlangMoreFeatures": self._nxlang_more_features,
                               "nxlangSwitch": self._nxlang_switch,
                               "addFont": self._add_font,
                               "project": self._project,
                               "addPage": self._add_page,
                               "newFolderChoices": self._new_folder_choices,
                               "newSourceFolder": self._new_source_folder}.items():
            self._answers(_OWN + method, answer)

    def checks_waiting(self) -> bool:
        """True when a change waits to be checked."""
        return self._checks.waiting()

    def run_checks(self):
        """Checks the changes that wait, and sends their findings."""
        self._pause = None
        self._checks.run()

    def _follows(self, method: str, follow):
        """Registers `follow(params)` to run on the message `method`, after
        what pygls does with it: a notification, or initialize and shutdown,
        which pygls answers. pygls takes plain functions, on which it notes
        what it registers."""
        def following(params):
            follow(params)
        self.feature(method)(following)

    def _answers(self, method: str, answer, options=None):
        """Registers `answer(params)` as the server's answer to the request
        `method`, refusing it before initialize, and with the protocol's
        "request failed" when it raises NxwrightError."""
        def answering(params):
            if not self._initialized:
                raise JsonRpcServerNotInitialized()
            try:
                return answer(params)
            except NxwrightError as error:
                raise RequestFailed(str(error)) from None
        self.feature(method, options)(answering)

    def _on_initialize(self, params):
        self._initialized = True

    def _on_shutdown(self, params):
        self.shut_down = True

    def _on_document_change(self, params):
        # The file on disk may differ from the text the editor had, as when closed.
        self._mark(params.text_document.uri)

    def _on_files_change(self, params):
        for change in params.changes:
            self._mark(change.uri)

    def _mark(self, uri: str):
        """Notes a change of the file `uri`, when it belongs to a source folder,
        to be checked once changes pause."""
        path = path_of(uri)
        root = find_source_folder(path, self._texts.read) if path else None
        if root is not None:
            self._checks.mark(root, path.relative_to(root).as_posix())
            self._check_after_pause()

    def _check_after_pause(self):
        """Runs the checks once changes pause for CHECK_PAUSE seconds, each
        change starting the wait again, on pygls's event loop, between
        messages. Driven message by message without one, as by a test, the
        server leaves them waiting for run_checks."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._pause is not None:
            self._pause.cancel()
        self._pause = loop.call_later(CHECK_PAUSE, self.run_checks)

    def _units(self, text: str) -> int:
        """Returns the editor's units in `text`, as the part of a line before
        a column."""
        return self.workspace.position_codec.client_num_units(text)

    def _folder(self, uri: str):
        """Returns (FolderIndex, path within the folder) of the file `uri`, or
        None outside a source folder."""
        path = path_of(uri)
        root = find_source_folder(path, self._texts.read) if path else None
        if root is None:
            return None
        return FolderIndex(root, self._texts.read), path.relative_to(root).as_posix()

    def _folder_of(self, params: dict):
        """Returns (FolderIndex, path within the folder) of the file of one of
        nxwright's own requests, or None outside a source folder."""
        return self._folder(params["textDocument"]["uri"])

    def _position(self, params):
        """Returns (FolderIndex, path, line, Python column) of a request's
        position, or None outside a source folder or past the file's end."""
        found = self._folder(params.text_document.uri)
        if found is None:
            return None
        index, path = found
        lines = index.lines(path)
        if lines is None or params.position.line >= len(lines):
            return None
        position = self.workspace.position_codec.position_from_client_units(
            lines, params.position)
        return index, path, position.line, position.character

    def _definition(self, params):
        """Returns the protocol's Locations of the definitions of the name at
        the request's position."""
        position = self._position(params)
        if position is None:
            return None
        return [self._location(position[0], place) for place in definitions(*position)]

    def _references(self, params):
        """Returns the protocol's Locations of the places using the name at
        the request's position."""
        position = self._position(params)
        if position is None:
            return None
        return [self._location(position[0], place)
                for place in references(*position, params.context.include_declaration)]

    def _document_symbols(self, params):
        """Returns the protocol's DocumentSymbols of the file's outline."""
        found = self._folder(params.text_document.uri)
        if found is None:
            return None
        index, path = found
        return [self._document_symbol(index, symbol) for symbol in file_symbols(index, path)]

    def _workspace_symbols(self, params) -> list:
        """Returns the protocol's SymbolInformation of the names holding the
        query, from the source folders of the open files."""
        roots = {find_source_folder(path, self._texts.read)
                 for path in self._texts.open_paths()} - {None}
        found = []
        for root in sorted(roots):
            index = FolderIndex(root, self._texts.read)
            for symbol, container in folder_symbols(index, params.query):
                found.append({"name": symbol.name, "kind": symbol.kind,
                              "location": self._location(index, symbol.place),
                              "containerName": container})
        return found

    def _hover(self, params):
        """Returns the protocol's Hover for the name at the request's position, or None."""
        position = self._position(params)
        text = hover(*position) if position else None
        return {"contents": {"kind": "markdown", "value": text}} if text else None

    def _completion(self, params) -> list:
        """Returns the protocol's CompletionItems for the request's position."""
        position = self._position(params)
        if position is None:
            return []
        return [self._completion_item(position[0], item) for item in completions(*position)]

    def _signature_help(self, params):
        """Returns the protocol's SignatureHelp for the call holding the
        request's position, or None."""
        position = self._position(params)
        found = signature(*position) if position else None
        if found is None:
            return None
        return {"signatures": [{"label": found.label,
                                "parameters": [{"label": parameter}
                                               for parameter in found.parameters]}],
                "activeSignature": 0, "activeParameter": found.active}

    def _formatting(self, params):
        """Returns the protocol's TextEdits formatting the request's .nx file:
        one replacing its whole text, or none when its layout is right.
        Raises NxwrightError when formatting is refused."""
        found = self._folder(params.text_document.uri)
        if found is None or not found[1].endswith(".nx"):
            return []
        index, path = found
        changed = format_folder(self._texts.folder_reader(index.root), only=[path])
        if path not in changed:
            return []
        lines = index.lines(path)
        end = {"line": len(lines) - 1, "character": self._units(lines[-1])}
        return [{"range": {"start": {"line": 0, "character": 0}, "end": end},
                 "newText": changed[path]}]

    def _rename(self, params):
        """Returns the protocol's WorkspaceEdit renaming the name at the
        request's position. Raises NxwrightError when the rename is refused."""
        position = self._position(params)
        if position is None:
            raise NxwrightError("only names of a source folder can be renamed")
        index = position[0]
        edits = rename(*position, params.new_name, self._texts.folder_reader(index.root),
                       lambda path: (index.root / path).is_file())
        return {"changes": {uri_of(index.root / file): [{"range": self._range(index, place),
                                                       "newText": new_text}
                                                      for place, new_text in file_edits]
                            for file, file_edits in edits.items()}}

    def _code_actions(self, params):
        """Returns the protocol's CodeActions of the request's problems that
        carry a quick fix (quick_fixes.py), each fixing its problem, worked out
        from the folder's files as the server holds them."""
        found = self._folder(params.text_document.uri)
        if found is None:
            return []
        index, path = found
        read = self._texts.folder_reader(index.root)
        actions = []
        for problem in params.context.diagnostics:
            if problem.source != "nxwright" or not isinstance(problem.data, dict):
                continue
            made = quick_fix(index, read, path, problem.range.start.line, problem.data)
            if made is not None:
                title, edits, preferred = made
                actions.append({"title": title, "kind": types.CodeActionKind.QuickFix.value,
                                "diagnostics": [_CONVERTER.unstructure(problem)],
                                "isPreferred": preferred,
                                "edit": self._workspace_edit(index, edits)})
        return actions

    def _editor_code(self, params: dict):
        """Returns the Editor code of the request's .nx file, as the first page
        using it compiles it: {"page", "text", "sourceLines"}, `sourceLines`
        giving for each line of `text` the file's line it comes from, counted
        from 0, or -1. When the code does not build: {"page", "error"}.
        Returns None outside a page's code."""
        found = self._folder_of(params)
        pages = found[0].pages_using(found[1]) if found else []
        if not pages:
            return None
        index, path = found
        try:
            folder = read_folder_source(self._texts.folder_reader(index.root))
            # The build's checks first, such as of references, which compiling skips.
            folder.build_page(folder.app["pages"].index(pages[0]), [])
            sections = folder.editor_code(pages[0], path)
        except NxwrightError as error:
            return {"page": pages[0], "error": str(error)}
        lines, sources = [], []
        for title, code in sections:
            lines.append("// " + title)
            sources.append(-1)
            for number, text in code:
                lines.append(text)
                sources.append(number - 1 if number else -1)
        return {"page": pages[0], "text": "\n".join(lines) + "\n", "sourceLines": sources}

    def _page_drawing(self, params: dict):
        """Returns the drawing of the page of the request's file (testing/preview.py),
        or None when the file is not a page's own."""
        found = self._folder_of(params)
        if found is None:
            return None
        index, path = found
        return self._previews.drawing(index.root, path, self._texts.folder_reader(index.root))

    def _page_objects(self, params: dict):
        """Returns the objects of the page of the request's file, the page
        first, with the lines of their tables, so that the cursor in a table
        selects its object; or None when the file is not a page's own. Read
        line by line, so a half-typed page file still lists its objects."""
        found = self._folder_of(params)
        page = found and page_of_file(found[1])
        if not page or page not in found[0].pages:
            return None
        return {"page": page,
                "objects": [{"name": entry.name, "type": entry.type,
                             "firstLine": entry.first_line, "lastLine": entry.last_line}
                            for entry in found[0].page_objects[page]]}

    def _page_object(self, params: dict) -> tuple:
        """Returns (FolderIndex, page, object name) of a request about an
        object of the page of its file. Raises NxwrightError outside a page."""
        return *self._page_of(params), params["name"]

    def _page_of(self, params: dict) -> tuple:
        """Returns (FolderIndex, page) of a request about the page of its
        file. Raises NxwrightError outside a page."""
        found = self._folder_of(params)
        page = found and page_of_file(found[1])
        if not page:
            raise NxwrightError("only a page's .page.toml or .nx file has a page")
        return found[0], page

    def _component_types(self, params: dict) -> dict:
        """Returns {"types"}: the types a component of the page can have
        (page_components.component_types)."""
        index, page = self._page_of(params)
        return {"types": component_types(self._texts.folder_reader(index.root), page)}

    def _add_component(self, params: dict) -> dict:
        """Returns {"edit", "name"}: the protocol's WorkspaceEdit adding a
        component of the type `type` to the page, at `point`, {"x", "y"},
        or (0, 0) without one, and its name. Raises NxwrightError when the
        addition is refused."""
        index, page = self._page_of(params)
        point = params.get("point") or {"x": 0, "y": 0}
        found = add_component(index, self._texts.folder_reader(index.root),
                              lambda path: (index.root / path).is_file(), page, params["type"],
                              point["x"], point["y"])
        return {"edit": self._workspace_edit(index, found["edits"]), "name": found["name"]}

    def _delete_components(self, params: dict) -> dict:
        """Returns {"edit", "namedElsewhere"}: the protocol's WorkspaceEdit
        deleting the components `names` of the page, and the places, {"uri",
        "line"}, where code that stays names one of them. Raises
        NxwrightError when the delete is refused."""
        index, page = self._page_of(params)
        found = delete_components(index, self._texts.folder_reader(index.root), page,
                                  params["names"])
        return {"edit": self._workspace_edit(index, found["edits"]),
                "namedElsewhere": [{"uri": uri_of(index.root / place["path"]),
                                    "line": place["line"]}
                                   for place in found["namedElsewhere"]]}

    def _clear_events(self, params: dict) -> dict:
        """Returns the protocol's WorkspaceEdit removing the code of the
        events of the components `names` of the page, without changes when
        none of them has code. Raises NxwrightError when it is refused."""
        index, page = self._page_of(params)
        edits = clear_events(index, self._texts.folder_reader(index.root), page,
                             params["names"])
        return self._workspace_edit(index, edits)

    def _copy_components(self, params: dict) -> dict:
        """Returns {"text", "code"}: the tables of the components `names` of
        the page, as the clipboard holds them, and their events' code, a text
        per event (page_components.copy_components)."""
        index, page = self._page_of(params)
        return copy_components(index, self._texts.folder_reader(index.root), page,
                               params["names"])

    def _place_components(self, params: dict) -> dict:
        """Returns the protocol's WorkspaceEdit placing several components
        of the page at once, `places` being {name: {"x", "y", "w", "h"}}."""
        index, page = self._page_of(params)
        edits = place_components(index, self._texts.folder_reader(index.root), page,
                                 params["places"])
        return self._workspace_edit(index, {page_toml_path(page): edits})

    def _reorder_components(self, params: dict) -> dict:
        """Returns the protocol's WorkspaceEdit moving the components `names`
        of the page `direction`: one place "forward" or "backward", or to the
        "front" or the "back" (page_components.reorder_components)."""
        index, page = self._page_of(params)
        edits = reorder_components(index, self._texts.folder_reader(index.root), page,
                                   params["names"], params["direction"])
        return self._workspace_edit(index, {page_toml_path(page): edits})

    def _lock_components(self, params: dict) -> dict:
        """Returns the protocol's WorkspaceEdit locking the components `names`
        of the page, or unlocking them, as `locked` says."""
        index, page = self._page_of(params)
        edits = lock_components(index, self._texts.folder_reader(index.root), page,
                                params["names"], params["locked"] is True)
        return self._workspace_edit(index, {page_toml_path(page): edits})

    def _group_components(self, params: dict) -> dict:
        """Returns the protocol's WorkspaceEdit giving the components `names`
        of the page a new group of their own, or taking them out of theirs,
        as `grouped` says."""
        index, page = self._page_of(params)
        edits = group_components(index, self._texts.folder_reader(index.root), page,
                                 params["names"], params["grouped"] is True)
        return self._workspace_edit(index, {page_toml_path(page): edits})

    def _paste_components(self, params: dict) -> dict:
        """Returns {"edit", "names"}: the protocol's WorkspaceEdit pasting the
        tables of `text`, with `code`, the code that came with them, into the
        page, and their new names. They go to the point `at`, {"x", "y"}, or
        where they were copied from with `inPlace` true, else where
        page_components.paste_components puts them. Raises NxwrightError when
        the paste is refused."""
        index, page = self._page_of(params)
        at = params.get("at")
        found = paste_components(index, self._texts.folder_reader(index.root),
                                 lambda path: (index.root / path).is_file(), page,
                                 params["text"], params.get("code") or [],
                                 at=(at["x"], at["y"]) if at else None,
                                 in_place=params.get("inPlace") is True)
        return {"edit": self._workspace_edit(index, found["edits"], found["created"]),
                "names": found["names"]}

    def _paste_parts(self, params: dict) -> dict:
        """Returns {"edit", "notes"}: the protocol's WorkspaceEdit applying
        `parts` of the one component whose table `text` holds, with `code`,
        the code that came with it, to the components `names` of the page,
        and what was left out. Raises NxwrightError when the paste is
        refused."""
        index, page = self._page_of(params)
        found = paste_parts(index, self._texts.folder_reader(index.root),
                            lambda path: (index.root / path).is_file(), page, params["names"],
                            params["text"], params.get("code") or [], params["parts"])
        return {"edit": self._workspace_edit(index, found["edits"], found["created"]),
                "notes": found["notes"]}

    def _component_properties(self, params: dict) -> dict:
        """Returns what the properties panel shows of the object `name` of
        the page (page_editing.properties)."""
        index, page, name = self._page_object(params)
        return properties(index, self._texts.folder_reader(index.root), page, name)

    def _set_attributes(self, params: dict) -> dict:
        """Returns the protocol's WorkspaceEdit setting `values`, {attribute:
        value as typed}, of the object `name`, each colour the nearest the
        screen holds when `nearestColours` is true, as for a picked one.
        Raises NxwrightError for a value the build would refuse."""
        index, page, name = self._page_object(params)
        edits = attribute_edits(index, self._texts.folder_reader(index.root), page, name,
                                params["values"],
                                nearest_colours=params.get("nearestColours") is True)
        return self._workspace_edit(index, {page_toml_path(page): edits})

    def _key_binding(self, params: dict) -> dict:
        """Returns what setting the `key` of the object `name` to `key`
        means (page_editing.key_binding)."""
        index, page, name = self._page_object(params)
        return key_binding(index, self._texts.folder_reader(index.root), page, name,
                           params["key"])

    def _add_keyboard(self, params: dict) -> dict:
        """Adds nxwright's keyboard page `keyboard` to the source folder of the
        request's file, writing its files (keyboard_adding.add_keyboard), and
        returns {"page", "font", "warning"}. The Chinese keyboard's font is
        drawn from the typeface file `typeface`, or is the folder's font
        named `font`."""
        root = self._rewritable_folder(params, "adding a keyboard")
        page, font, warning = add_keyboard(root, params["keyboard"], params.get("typeface"),
                                           params.get("font"))
        return {"page": page, "font": font, "warning": warning}

    def _chinese_keyboard_fonts(self, params: dict) -> dict:
        """Returns {"fonts"}, the fonts of the source folder `folder` that its
        Chinese keyboard takes (keyboard_adding.chinese_keyboard_fonts)."""
        folder = Path(params["folder"])
        return {"fonts": chinese_keyboard_fonts(folder, read_app(folder))}

    def _project(self, params: dict) -> dict | None:
        """Returns what the side bar shows of the source folder `folder`:
        {"format", "currentFormat"}, and in the current format, from its
        app.toml, "language", "pages", and "resources", each kind's names by
        its list's name, as "fonts", and with screen settings, "screen", its
        "size" as "800 x 480", "rotation", and "encoding". The format is read
        first, as app.toml's other keys are read only in the current format.
        Returns None when the format cannot be read."""
        folder = Path(params["folder"])
        try:
            found = folder_format(folder)
        except NxwrightError:
            return None
        project = {"format": found, "currentFormat": SOURCE_FORMAT}
        if found != SOURCE_FORMAT:
            return project
        try:
            app = read_app(folder)
        except NxwrightError:
            return project
        project.update(name=app_name(app, folder), language=app["language"],
                       pages=app["pages"],
                       resources={listed: app[listed] for listed in LISTS.values()})
        if "screen" in app:
            model = model_named(app["screen"])
            project.update(screen=model.name, size="%d x %d" % (model.width, model.height),
                           rotation=app["rotation"], encoding=app["encoding"])
        return project

    def _add_page(self, params: dict) -> dict:
        """Adds a blank page named `name`, or the first free pageN without
        one, to the source folder of the request's file, writing its files
        (source_folder.add_page), and returns {"page", "file"}, its name and
        the path of its page file."""
        root = self._rewritable_folder(params, "adding a page")
        page = add_page(root, params.get("name"))
        return {"page": page, "file": str(root / page_toml_path(page))}

    def _new_folder_choices(self, params) -> dict:
        """Returns the choices `nxwright new` asks for: {"models", each
        {"name", "size"}, "rotations", "encodings", "languages", "defaults"},
        the defaults those of `nxwright new`; a screen model has none."""
        return {"models": [{"name": model.name, "size": "%d x %d" % (model.width, model.height)}
                           for model in MODELS],
                "rotations": list(ROTATIONS),
                "encodings": list(ENCODINGS.values()),
                "languages": list(LANGUAGES),
                "defaults": {"rotation": 0, "encoding": DEFAULT_ENCODING, "language": NXLANG}}

    def _new_source_folder(self, params: dict) -> dict:
        """Writes a new source folder at `folder`, of the `screen` model at
        `rotation`, in `encoding` and `language`, as `nxwright new` does
        (source_folder.new_source_folder), and returns {"file", "warning"}:
        the path of its first page's file, and what its font lacks, or None."""
        folder = Path(params["folder"])
        settings = DeviceSettings(model_named(params["screen"]), params["rotation"],
                                  params["encoding"])
        warning = new_source_folder(folder, settings, params["language"], params.get("name"))
        return {"file": str(folder / page_toml_path("page0")), "warning": warning}

    def _fonts(self, params: dict) -> dict:
        """Returns the folder's fonts, with samples of the request's "text" in
        its "colour" (font_panel.FontPanelAnswers.fonts)."""
        return self._font_panel.fonts(self._source_folder(params), params["text"],
                                      _colour(params))

    def _typefaces(self, params: dict) -> dict:
        """Returns the typefaces nxwright can draw a font from in the folder's
        encoding (font_panel.FontPanelAnswers.typefaces)."""
        return self._font_panel.typefaces(self._source_folder(params))

    def _font_file(self, params: dict) -> dict:
        """Returns one font file's details and a sample of the request's
        "text" in its "colour", for the font viewer
        (font_panel.font_file_details)."""
        return font_file_details(Path(params["file"]), params["text"], _colour(params))

    def _media_frames(self, params: dict) -> dict:
        """Returns the frames of the animation or video file "file", for the
        media viewer (media_viewer.media_frames)."""
        return media_frames(Path(params["file"]))

    def _nxlang_samples(self, params) -> list:
        """Returns the sections of the panel explaining the switch to nxlang
        that show code: what nxlang adds, each in nxlang and, when there is a
        usual way, in strict Nextion syntax (nxlang_samples.panel_sections)."""
        return panel_sections()

    def _nxlang_more_features(self, params) -> list:
        """Returns what else nxlang lets you do, as the panel explaining the
        switch to nxlang lists it under "And more", each item's code between
        backticks (nxlang_samples.MORE_FEATURES)."""
        return list(MORE_FEATURES)

    def _nxlang_switch(self, params: dict) -> dict:
        """Returns the files the switch to nxlang writes in the source folder
        "folder", and the lines of code it changes, for the panel making it
        (nxlang_switch.nxlang_switch)."""
        return nxlang_switch(Path(params["folder"]))

    def _font_sample(self, params: dict) -> dict:
        """Returns a sample of a font about to be added, and what adding it
        would do: of the font drawn from the typeface file "typeface"
        (font_panel.typeface_sample), or of the ready-made font file "file"
        (font_panel.font_file_sample)."""
        root, colour = self._source_folder(params), _colour(params)
        if "typeface" in params:
            return typeface_sample(root, Path(params["typeface"]), params.get("height"),
                                   bool(params.get("smoothed", True)), params.get("name"),
                                   params["text"], colour, params.get("characters"),
                                   bool(params.get("fullTable", False)))
        return font_file_sample(root, requested_font_file(params), params.get("name"),
                                params["text"], colour)

    def _add_font(self, params: dict) -> dict:
        """Adds a font to the folder, writing its file (font_panel.add), and
        returns {"name", "warning"}."""
        return add_font_to_folder(self._rewritable_folder(params, "adding a font"), params)

    def _source_folder(self, params: dict) -> Path:
        """Returns the source folder of the request's file. Raises
        NxwrightError outside a source folder."""
        found = self._folder_of(params)
        if not found:
            raise NxwrightError("the file is not in a source folder")
        return found[0].root

    def _rewritable_folder(self, params: dict, what: str) -> Path:
        """Returns the source folder of the request's file, whose app.toml
        `what` rewrites, from disk. Raises NxwrightError outside a source
        folder, or while app.toml has unsaved changes, which it would lose."""
        root = self._source_folder(params)
        if self._texts.unsaved(root / "app.toml"):
            raise NxwrightError("save or revert the changes to app.toml first; %s rewrites it"
                                % what)
        return root

    def _default_event(self, params: dict) -> dict | None:
        """Returns {"uri", "line", "character"} of the code of the object's
        event `event`, else of its default event, and "edit", the
        WorkspaceEdit adding its heading when it has no code, or None; or
        None when its type has no events. Raises NxwrightError for an event
        its type lacks."""
        index, page, name = self._page_object(params)
        found = default_event(index, self._texts.folder_reader(index.root), page, name,
                              params.get("event"))
        if found is None:
            return None
        uri = uri_of(index.root / found["path"])
        lines = index.lines(found["path"]) or []
        cursor = self._client_position(lines, found)
        return {"uri": uri, "line": cursor["line"], "character": cursor["character"],
                "edit": {"changes": {uri: self._client_edits(lines, [found["edit"]])}}
                if found["edit"] else None}

    def _component_events(self, params: dict) -> list:
        """Returns the object's events in its type's order, each {"event",
        "uri"}: that of the file holding its code, or None when it has none."""
        index, page, name = self._page_object(params)
        return [{"event": found["event"],
                 "uri": uri_of(index.root / found["path"]) if found["path"] else None}
                for found in component_events(index, self._texts.folder_reader(index.root),
                                              page, name)]

    def _limits(self, params: dict):
        """Returns the measures of the page of the request's file, or None."""
        found = self._folder_of(params)
        return self._checks.limits(found[0].root, found[1]) if found else None

    def _workspace_edit(self, index: FolderIndex, edits: dict, created=()) -> dict:
        """Returns the protocol's WorkspaceEdit of `edits`, {path within the
        folder: [TextEdit], their columns Python's}, making the files
        `created` first."""
        edits = {path: self._client_edits(index.lines(path) or [], file_edits)
                 for path, file_edits in edits.items()}
        if not created:
            return {"changes": {uri_of(index.root / path): file_edits
                                for path, file_edits in edits.items()}}
        return {"documentChanges": [{"kind": "create", "uri": uri_of(index.root / path)}
                                    for path in created]
                + [{"textDocument": {"uri": uri_of(index.root / path), "version": None},
                    "edits": file_edits} for path, file_edits in edits.items()]}

    def _client_edits(self, lines: list, edits: list) -> list:
        """Returns the TextEdits `edits` of a file of `lines`, their columns
        turned from Python's into the editor's units."""
        return [dict(edit, range={"start": self._client_position(lines, edit["range"]["start"]),
                                  "end": self._client_position(lines, edit["range"]["end"])})
                for edit in edits]

    def _client_position(self, lines: list, position: dict) -> dict:
        """Returns the protocol's Position of `position`, its column Python's,
        in a file of `lines`; a line past them, as one an edit adds, keeps it."""
        line, column = position["line"], position["character"]
        if line < len(lines):
            column = self._units(lines[line][:column])
        return {"line": line, "character": column}

    def _location(self, index: FolderIndex, place: Place) -> dict:
        """Returns the protocol's Location of a place."""
        return {"uri": uri_of(index.root / place.path), "range": self._range(index, place)}

    def _range(self, index: FolderIndex, place: Place) -> dict:
        """Returns the protocol's Range of a place, in the editor's units."""
        start = end = 0
        # A file's start needs no columns. Reading the file for them would fail for a picture.
        if place.end > 0:
            text = index.lines(place.path)[place.line]
            start, end = self._units(text[:place.start]), self._units(text[:place.end])
        return {"start": {"line": place.line, "character": start},
                "end": {"line": place.line, "character": end}}

    def _document_symbol(self, index: FolderIndex, symbol) -> dict:
        """Returns the protocol's DocumentSymbol of a Symbol, spanning its lines."""
        last_line = index.lines(symbol.place.path)[symbol.last_line]
        lines_range = {"start": {"line": symbol.first_line, "character": 0},
                       "end": {"line": symbol.last_line, "character": self._units(last_line)}}
        return {"name": symbol.name, "detail": symbol.detail, "kind": symbol.kind,
                "range": lines_range, "selectionRange": self._range(index, symbol.place),
                "children": [self._document_symbol(index, child) for child in symbol.children]}

    def _completion_item(self, index: FolderIndex, item) -> dict:
        """Returns the protocol's CompletionItem of a completion Item, with its
        documentation as Markdown, when it has some, and the text it replaces,
        when that is not the word at the cursor."""
        found = {"label": item.label, "kind": item.kind, "detail": item.detail}
        if item.documentation:
            found["documentation"] = {"kind": "markdown", "value": item.documentation}
        if item.replaces is not None:
            found["textEdit"] = {"range": self._range(index, item.replaces),
                                 "newText": item.label}
        return found


def serve(input_stream, output_stream) -> int:
    """Answers the messages read from the binary `input_stream`, writing the
    replies to `output_stream`, until the exit notification or the end of
    the input. Returns the exit code the protocol asks for: 0 after shutdown
    and exit, else 1."""
    server = NxwrightServer()
    server.start_io(input_stream, output_stream)
    return 0 if server.shut_down else 1


def _colour(params: dict) -> tuple:
    """Returns the RGB colour a request's "colour" gives, [red, green, blue]
    from 0 to 255, or white."""
    colour = params.get("colour")
    if (isinstance(colour, list) and len(colour) == 3
            and all(isinstance(value, int) and 0 <= value <= 255 for value in colour)):
        return tuple(colour)
    return (255, 255, 255)
