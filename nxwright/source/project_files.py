"""Going between a project file (.HMI) and its source folder.

Each goes through a dump in a temporary folder:
  - build: source folder to dump, then a new project file written from the
    dump and the folder's device settings (new_project.py);
  - extract: project file to dump, then the dump imported into the source
    folder, as `nxwright dump` and `nxwright import` would one after the other;
  - defaults: project file to dump, then its newly added components written
    as a component defaults file, which lists what page files leave out.

A project file given to read is only read. The build replaces an existing
project file at its output (project/replacing.py); the other outputs must
not exist yet.
"""
from pathlib import Path
import tempfile

from nxwright import NxwrightError
from nxwright.project.dump_folder import page_text_files
from nxwright.project.dumper import ProjectDumper
from nxwright.project.page_text import page_from_text
from nxwright.project.new_project import write_new_project
from nxwright.project.component_defaults import defaults_from_pages, defaults_to_toml
from nxwright.project.replacing import held_by_the_nextion_editor, is_project_file, written_beside
from nxwright.source.source_folder import (NXLANG, export_dump, folder_device_settings,
                                           import_dump, read_app, refuse_unless_new_folder)
from nxwright.source.unknown_content import MAY_BE_LOST, checked, unknown_in_project_file


def build(source_folder: Path, output: Path, refuse_by_table: bool = True,
          keep_backup: bool = False, lock_pages: bool = False):
    """Writes the project file `output` from `source_folder` alone. Returns
    the project's memory, as the Editor's compile counts it, a
    page_memory.ProjectMemory.

    An existing project file at `output` is replaced, but only once the new
    one is written in full and checked. The new file is written beside it
    first, so a failed build leaves it as it was. With `keep_backup`, an old
    file that changed since nxwright wrote it is kept as a backup
    (replacing.written_beside). With `lock_pages`, the project file has its
    pages locked, which shows in the Nextion Editor that it is not meant for
    editing (page_header.with_lock).

    Raises NxwrightError when `output` exists and is not a project file, the
    folder's app.toml has no device settings (extracting a project, or
    nxwright new, writes them), or the folder holds something the build
    cannot write, or the Editor's compile would refuse, a page past the
    screen's memory among them. Without `refuse_by_table`, the pages are not
    checked against the memory table (source_folder.FolderSource.refuse_by_table).
    """
    output = Path(output)
    # Replacing only a project file guards against a mistyped output, such
    # as a file of the source folder.
    if output.exists() and not is_project_file(output):
        raise NxwrightError("%s exists and is not a project file; the build replaces only a "
                            "project file" % output)
    settings = folder_device_settings(source_folder)
    if settings is None:
        advice = ("add them to it" if read_app(source_folder)["language"] == NXLANG
                  else "extract the project into it, or start the folder with nxwright new")
        raise NxwrightError("%s has no device settings in its app.toml (screen, rotation, "
                            "encoding); %s" % (source_folder, advice))
    with held_by_the_nextion_editor(output), \
            written_beside(output, keep_backup) as written, \
            tempfile.TemporaryDirectory() as name:
        dump = Path(name) / "dump"
        pictures, memory = export_dump(source_folder, dump, refuse_by_table, lock_pages)
        try:
            write_new_project(dump, settings, written)
        except NxwrightError as error:
            # A picture refused as it is decoded, named by its dump's file.
            if error.file not in pictures:
                raise
            raise NxwrightError("%s: %s" % (pictures[error.file], error.reason)) from None
    return memory


def extract(project: Path, source_folder: Path, continue_with_unknown: bool = False,
            app_name: str = None) -> list:
    """Extracts `project` into `source_folder`, a new or empty folder, and
    names the app `app_name`, or else after the project file. Any other folder is rejected before
    anything else (source_folder.refuse_unless_new_folder). Returns the warnings
    of what the source files leave out (source_folder.import_dump). Notes on
    the content nxwright does not know come before the warnings: one for
    each thing that is kept exactly or written otherwise, and one for each
    thing that may be lost, if extracting went on past it.

    Before it writes anything, the function raises NxwrightError for content
    nxwright cannot keep. It raises UnknownContentError for content the next
    build may lose, unless `continue_with_unknown` is true
    (source/unknown_content.py)."""
    project, source_folder = Path(project), Path(source_folder)
    refuse_unless_new_folder(source_folder)
    with held_by_the_nextion_editor(project):
        found = unknown_in_project_file(project)
    lost = [each for each in found if each.sort == MAY_BE_LOST]
    notes = checked(project, found, continue_with_unknown, project)
    with tempfile.TemporaryDirectory() as name:
        dump = Path(name) / "dump"
        with held_by_the_nextion_editor(project):
            # Content that may be lost reaches this point only if the user
            # chose to go on past it. In that case, the dump leaves out the
            # blocks of a kind nxwright does not handle. It also writes a page
            # as text even when the text does not rebuild the page's bytes.
            ProjectDumper(project, dump, leave_out_unknown_blocks=bool(lost),
                          write_differing_pages=bool(lost)).dump()
        # The dump's unknown content was checked above, as part of the project's.
        name = app_name if app_name is not None else project.stem.strip()
        warnings = import_dump(dump, source_folder, name, check_unknown=False)
    return notes + warnings


def write_defaults(sample: Path, output: Path):
    """Writes the component defaults of `sample` to the new file `output`.

    The sample is a project made in the Nextion Editor with one newly added
    component of each type, left as the Editor created it.
    """
    if output.exists():
        raise NxwrightError("%s already exists" % output)
    with tempfile.TemporaryDirectory() as name:
        dump = Path(name) / "dump"
        ProjectDumper(sample, dump).dump()
        pages = [page_from_text(path.read_text(encoding="utf-8"))
                 for _, path in sorted(page_text_files(dump).items())]
    header = ("Defaults of newly added components, per type: what a source folder leaves out.\n"
              "Written by nxwright defaults from %s." % sample.name)
    text = defaults_to_toml(defaults_from_pages(pages), header)
    with open(output, "x", encoding="utf-8", newline="\n") as out:
        out.write(text)
