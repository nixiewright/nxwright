"""The language server's answer for nxwright's picture editor in VS Code
(editors/vscode/src/pictureView.ts): an SVG picture of a source folder as
nxwright draws it (source/svg_pictures.py), from the files as open in the
editor, unsaved changes included, with the defaults of app.toml's defines.
"""
from pathlib import Path

from nxwright import NxwrightError
from nxwright.project.pictures import data_url
from nxwright.source.folder_index import find_source_folder
from nxwright.source.source_folder import folder_byte_reader, folder_defines
from nxwright.source.svg_pictures import SvgPictureError, drawn_svg_picture, prepared_svg_picture


def svg_picture_view(file: Path, texts) -> dict:
    """Returns, for the SVG picture file `file`, {"picture": its PNG picture
    as a data: URL, "width", "height", "files": the full paths of the files
    it reads, its own first, and app.toml, whose defines it takes}, or
    {"error": why it cannot be drawn, "files": those it tried to read}.
    `texts` is the server's FileTexts, which gives the open files' text."""
    root = find_source_folder(file, texts.read)
    if root is None:
        return {"error": "%s is not in a source folder" % file.name, "files": [str(file)]}
    read = texts.folder_reader(root)
    path = file.relative_to(root).as_posix()
    files = [str(file), str(root / "app.toml")]
    try:
        drawing = prepared_svg_picture(path, read, folder_byte_reader(root), folder_defines(read))
    except SvgPictureError as error:
        return {"error": str(error), "files": files + _full(root, error.files)}
    except NxwrightError as error:
        return {"error": str(error), "files": files}
    files += _full(root, drawing.files)
    try:
        png = drawn_svg_picture(drawing)
    except NxwrightError as error:
        return {"error": str(error), "files": files}
    return {"picture": data_url(png), "width": drawing.width, "height": drawing.height,
            "files": files}


def _full(root: Path, paths) -> list:
    """Returns the full paths of `paths`, within the source folder `root`,
    but the picture's own, the first, which the answer gives already."""
    return [str(root / path) for path in paths[1:]]
