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
from nxwright.source.source_folder import export_dump, folder_device_settings, import_dump


def build(source_folder: Path, output: Path, refuse_by_table: bool = True):
    """Writes the project file `output` from `source_folder` alone. Returns
    the project's memory, as the Editor's compile counts it, a
    page_memory.ProjectMemory.

    An existing project file at `output` is replaced, but only once the new
    one is written in full and checked. The new file is written beside it
    first, so a failed build leaves it as it was.

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
        raise NxwrightError("%s has no device settings in its app.toml (screen, rotation, "
                            "encoding); extract the project into it, or start the folder with "
                            "nxwright new" % source_folder)
    with held_by_the_nextion_editor(output), written_beside(output) as written, \
            tempfile.TemporaryDirectory() as name:
        dump = Path(name) / "dump"
        pictures, memory = export_dump(source_folder, dump, refuse_by_table)
        try:
            write_new_project(dump, settings, written)
        except NxwrightError as error:
            # A picture refused as it is decoded, named by its dump's file.
            if error.file not in pictures:
                raise
            raise NxwrightError("%s: %s" % (pictures[error.file], error.reason)) from None
    return memory


def extract(project: Path, source_folder: Path) -> list:
    """Extracts `project` into `source_folder`, a new, empty, or existing
    source folder. A new one names the app after the project file. An
    existing one keeps its name, its picture and font names, and its code as
    written, wherever the project did not change them. Returns the warnings
    of what the source files leave out (source_folder.import_dump)."""
    with tempfile.TemporaryDirectory() as name:
        dump = Path(name) / "dump"
        with held_by_the_nextion_editor(Path(project)):
            ProjectDumper(project, dump).dump()
        return import_dump(dump, source_folder, Path(project).stem.strip())


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
