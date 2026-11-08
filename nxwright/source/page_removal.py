"""Deleting a page from a source folder (`nxwright remove <folder> page`): its
page file, its `.nx` file, and its entry in app.toml's `pages`. A file the
page includes stays, since other pages may include it too.

The deletion is rejected, and nothing is written, while a file other than
the page's own uses the page by name, or gives its ID or a later page's ID
as a number:
  - by name, wherever Find All References finds it, such as `page settings`
    or `settings.t0.txt` (references.py);
  - by number, as the argument of `page`, or given to `dp` or compared with
    it (resource_numbers.page_numbers).
Later IDs count because a page's ID is its place in `pages`, so deleting a
page lowers the ID of each later page. Code that names a later page still
reaches it, but a number would then stand for another page. A number that
code computes, or keeps in a variable, is not found.

The deletion is also rejected for the folder's only page, and when the
folder's checks find an error before or after the deletion. An error found
before the deletion could hide a use.

remove_page_keeping_ids instead leaves an empty slot page in the deleted
page's place: a blank page named `empty_slot_1`, or `empty_slot_2` and so on
if that name is taken, so that no page's ID changes. It then rejects the
deletion only while the folder uses the page itself, by name or by its own
ID. page_removal_report returns what a deletion would affect, in the form of
resource_removal.removal_report, and writes nothing.
"""
import dataclasses
from pathlib import Path
import re

from nxwright import NxwrightError
from nxwright.language.code_lines import split_line
from nxwright.source.folder_check import check_folder
from nxwright.source.folder_index import APP_FILE, FolderIndex, text_on_disk
from nxwright.source.page_source import page_nx_path, page_toml_path
from nxwright.source.references import references
from nxwright.source.resource_numbers import code_lines, page_numbers
from nxwright.source.resource_removal import use_at
from nxwright.source.source_folder import (app_text_in, delete_files, folder_file_exists,
                                           folder_lister, folder_reader, new_page_files,
                                           put_back, read_app, read_folder_source)

# The name of an empty slot page, where %d is its number. It has underscores so that
# code can use it, as in `page empty_slot_1`.
EMPTY_SLOT_NAME = "empty_slot_%d"


def page_uses(source_folder: Path, page: str) -> tuple:
    """Returns (the folder's pages, a ResourceUse record for each use of the
    page `page` that the module's docstring lists).

    Raises NxwrightError for a page the folder does not have, and for a
    folder whose checks find an error."""
    source_folder = Path(source_folder)
    pages = read_app(source_folder)["pages"]
    if page not in pages:
        raise NxwrightError("the folder has no page named %s" % page)
    read = folder_reader(source_folder)
    errors = check_folder(read, folder_file_exists(source_folder),
                          listed=folder_lister(source_folder)).errors()
    if errors:
        raise NxwrightError("cannot find every use of the page %s, because the folder has an "
                            "error: %s: %s" % (page, errors[0].place, errors[0].message))
    index = FolderIndex(source_folder, text_on_disk)
    own_files = {page_toml_path(page), page_nx_path(page)}
    uses = []
    own = index.page_objects[page][0].place
    for place in references(index, own.path, own.line, own.start, with_declarations=False):
        if place.path not in own_files and place.path != APP_FILE:
            uses.append(use_at(index, place.path, place.line + 1, "name", "itself"))
    ids = range(pages.index(page), len(pages))
    for (path, number), found in code_lines(read_folder_source(read), index).items():
        if not number or path in own_files:
            continue
        # A line of a file that several pages include is a use only when a page
        # other than the deleted one includes the file.
        values = {value for reader, code in found if reader != page
                  for value in page_numbers(split_line(code, 0)[1].strip()) if value in ids}
        if values:
            uses.append(use_at(index, path, number, "number",
                               "itself" if ids.start in values else "later"))
    return pages, uses


def page_removal_report(source_folder: Path, page: str) -> dict:
    """Returns what deleting the page `page` would affect, writing nothing,
    in the form of resource_removal.removal_report: {"kind": "page", "name",
    "id", "encoding" (the folder's), "last" (whether it is the last page),
    "later" (the names of the later pages), "uses"}. Raises NxwrightError as
    for a page the folder does not have, for a folder whose checks find an
    error, and for the folder's only page."""
    pages, uses = page_uses(source_folder, page)
    _check_not_only(pages, page)
    place = pages.index(page)
    return {"kind": "page", "name": page, "id": place,
            "encoding": read_app(Path(source_folder)).get("encoding"),
            "last": place == len(pages) - 1, "later": pages[place + 1:],
            "uses": [dataclasses.asdict(use) for use in uses]}


def remove_page(source_folder: Path, page: str) -> tuple:
    """Deletes the page `page` and its files. Returns (the paths deleted, a
    sentence "path: why" for each file that could not be deleted). Raises
    NxwrightError, and writes nothing, when the module's docstring says the
    deletion is rejected. The error lists each use."""
    pages, uses = page_uses(source_folder, page)
    _check_not_only(pages, page)
    _reject_for(page, uses)
    return _replace_page(Path(source_folder), pages, page, None)


def remove_page_keeping_ids(source_folder: Path, page: str) -> tuple:
    """Deletes the page `page`, and writes an empty slot page in its place,
    so that no page's ID changes. Returns (the empty slot page's name, the
    paths deleted, a sentence "path: why" for each file that could not be
    deleted). Raises NxwrightError, and writes nothing, in the same cases as
    remove_page, except that only uses of the page itself count, by name or
    by its own ID. Also raises it for a page that is an empty slot page
    already."""
    pages, uses = page_uses(source_folder, page)
    _check_not_only(pages, page)
    if re.fullmatch(EMPTY_SLOT_NAME.replace("%d", "[1-9][0-9]*"), page):
        raise NxwrightError("the page %s is an empty slot page already" % page)
    _reject_for(page, [use for use in uses if use.of == "itself"])
    # The empty slot page's name must differ from the name of every page and
    # every component.
    index = FolderIndex(Path(source_folder), text_on_disk)
    taken = {entry.name.lower() for objects in index.page_objects.values() for entry in objects
             if entry.name != page}
    number = 1
    while (EMPTY_SLOT_NAME % number).lower() in taken:
        number += 1
    name = EMPTY_SLOT_NAME % number
    deleted, left = _replace_page(Path(source_folder), pages, page, name)
    return name, deleted, left


def _check_not_only(pages: list, page: str):
    """Raises NxwrightError when `page` is the folder's only page."""
    if pages == [page]:
        raise NxwrightError("the page %s is the folder's only page, and a project needs one"
                            % page)


def _reject_for(page: str, uses: list):
    """Raises NxwrightError listing each of `uses`, if there are any."""
    if uses:
        raise NxwrightError("the page %s is used, so it stays:\n%s"
                            % (page, "\n".join("  %s" % use for use in uses)))


def _replace_page(source_folder: Path, pages: list, page: str, empty_slot) -> tuple:
    """Takes the page `page` out of app.toml's `pages`, or puts the empty
    slot page `empty_slot` in its place, then deletes the page's own files.
    The empty slot page's files are written first, then app.toml, so that
    app.toml never lists a page whose files are missing. Returns (the paths
    deleted, a sentence for each that could not be). Raises NxwrightError,
    writing nothing, if a file is already where one of the empty slot page's
    files would go, and for a folder whose checks would find an error after the deletion."""
    app = read_app(source_folder)
    new_pages = [empty_slot if known == page else known for known in pages
                 if known != page or empty_slot is not None]
    new_files = new_page_files(app, empty_slot) if empty_slot is not None else {}
    for path in new_files:
        if (source_folder / path).exists():
            raise NxwrightError("cannot write the empty slot page: %s is already there, "
                                "though app.toml does not list it" % (source_folder / path))
    app_text = app_text_in(source_folder, dict(app, pages=new_pages))
    gone = [path for path in (page_toml_path(page), page_nx_path(page))
            if (source_folder / path).is_file()]
    texts = {path: data.decode("utf-8") for path, data in new_files.items()}
    _check_after(source_folder, dict(texts, **{APP_FILE: app_text}), gone)
    app_path = source_folder / APP_FILE
    written = [(app_path, app_path.read_bytes())]
    try:
        for path, data in new_files.items():
            written.append((source_folder / path, None))
            (source_folder / path).write_bytes(data)
        app_path.write_text(app_text, encoding="utf-8", newline="\n")
    except Exception:
        put_back(written)
        raise
    return delete_files(source_folder, gone)


def _check_after(source_folder: Path, texts: dict, gone: list):
    """Raises NxwrightError when the folder's checks would find an error
    after each file of `texts`, {path: text}, is written with its text, and
    each file of `gone` is deleted."""
    read, exists = folder_reader(source_folder), folder_file_exists(source_folder)
    lister = folder_lister(source_folder)

    def read_after(path: str) -> str:
        if path in gone and path not in texts:
            raise NxwrightError("%s is deleted" % path)
        return texts[path] if path in texts else read(path)

    def exists_after(path: str) -> bool:
        return path in texts or (path not in gone and exists(path))

    def list_after(folder: str) -> list:
        names = [file for file in lister(folder) if "%s/%s" % (folder, file) not in gone]
        names += [path.rpartition("/")[2] for path in texts if path.rpartition("/")[0] == folder]
        return sorted(set(names))

    errors = check_folder(read_after, exists_after, listed=list_after).errors()
    if errors:
        raise NxwrightError("the folder would not build after the deletion: %s: %s"
                            % (errors[0].place, errors[0].message))

