"""What differs between a source folder and a project file, or between two project
files: nxwright diff.

Both sides are extracted the same way into temporary folders, which are then compared.
So the same pages and assets get the same names on both sides, and only real
differences show. A source folder is built first, the same way nxwright build builds it. The
code shown is the code extract writes, not the folder's own spacing, which the first
line of the output says.
"""
import difflib
from pathlib import Path
import tempfile

from nxwright import NxwrightError
from nxwright.project.replacing import is_project_file
from nxwright.source.project_files import build, extract

# The files compared as text. Any other file is compared by its bytes.
_TEXT_SUFFIXES = (".toml", ".nx")
# The name both sides are extracted under, so that the names of the two files do not
# show as a difference.
_APP_NAME = "compared"
_FIRST_LINE = "Both sides are shown as nxwright extract writes them."


def diff_projects(first: Path, second: Path, lock_pages: bool = True) -> tuple:
    """Returns (the lines of the diff between `first` and `second`, or [] when they do
    not differ; the warnings about content nxwright does not know, each starting with
    its side). Each side is a source folder or a project file. A source folder is
    built with its pages locked if `lock_pages`, and without checking them against the
    memory table. Raises NxwrightError for a path that is neither, and for content
    nxwright cannot keep."""
    first, second = Path(first), Path(second)
    with tempfile.TemporaryDirectory(prefix="nxwright-diff-") as work:
        work = Path(work)
        warnings = []
        folders = []
        for number, side in enumerate((first, second)):
            project = _project_of(side, work / ("%d.HMI" % number), lock_pages)
            folder = work / str(number)
            warnings += ["%s: %s" % (side, warning) for warning in extract(
                project, folder, continue_with_unknown=True, app_name=_APP_NAME)]
            folders.append(folder)
        lines = _folder_diff(folders[0], folders[1], str(first), str(second))
    return ([_FIRST_LINE] + lines if lines else []), warnings


def _project_of(side: Path, built: Path, lock_pages: bool) -> Path:
    """Returns the project file of `side`: `side` itself, or the file `built`, which
    this function builds from the source folder `side`."""
    if (side / "app.toml").is_file():
        build(side, built, refuse_by_table=False, lock_pages=lock_pages)
        return built
    if is_project_file(side):
        return side
    raise NxwrightError("%s is neither a source folder nor a project file" % side)


def _folder_diff(first: Path, second: Path, first_label: str, second_label: str) -> list:
    """Returns the lines of a unified diff of each file that differs between the
    folders `first` and `second`. Each file's path is given under the label of its
    side."""
    files = {side: {path.relative_to(folder).as_posix(): path
                    for path in folder.rglob("*") if path.is_file()}
             for side, folder in ((0, first), (1, second))}
    lines = []
    for relative in sorted(set(files[0]) | set(files[1])):
        paths = (files[0].get(relative), files[1].get(relative))
        contents = [path.read_bytes() if path else None for path in paths]
        if contents[0] == contents[1]:
            continue
        labels = ("%s/%s" % (first_label, relative), "%s/%s" % (second_label, relative))
        if relative.endswith(_TEXT_SUFFIXES):
            texts = [content.decode("utf-8").splitlines() if content is not None else []
                     for content in contents]
            changed = list(difflib.unified_diff(texts[0], texts[1], *labels, lineterm=""))
            # Files can differ with no line that does, such as in a final line end.
            lines += changed or ["Files %s and %s differ" % labels]
        elif None in contents:
            lines.append("Only in %s: %s" % ((first_label, second_label)[contents.index(None) ^ 1],
                                             relative))
        else:
            lines.append("Binary files %s and %s differ" % labels)
    return lines
