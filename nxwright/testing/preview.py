"""The page preview's drawings, for the language server's nxwright/pageDrawing
request, and for the debugger's panel of a simulation and the pictures an
agent asks for of it (drawing/screen_pictures.py).

A drawing (drawing/page_drawing.py) is of the page whose .page.toml or .nx file is
asked about, from its page file as the editor has it, saved or not. The
page's code plays no part: a page whose code does not build still draws.
Decoded fonts and the sizes of pictures are kept between drawings until
their file changes, since a page redraws at each pause in typing.
"""
import os
from pathlib import Path
import re

from nxwright import NxwrightError
from nxwright.drawing.page_drawing import DrawingResources, draw_page
from nxwright.language.resource_names import ANIMATION, LISTS
from nxwright.project.media_files import (animation_frames, is_card_picture, read_card_picture,
                                          video_frames)
from nxwright.project.pictures import (data_url, exif_orientation, picture_size, read_picture,
                                       write_png)
from nxwright.project.screen_copy import FORMAT_COMPRESSED, OPAQUE
from nxwright.project.screen_models import model_named
from nxwright.project.zi_font import decode_font, read_font_header
from nxwright.source.page_source import page_toml_path
from nxwright.source.source_folder import picture_file, played_file, read_page_components
from nxwright.testing.sd_cards import CardRefusal

# A page's own files: pages/<name>.page.toml and pages/<name>.nx.
_PAGE_FILE = re.compile(r"pages/([^/]+)\.(?:page\.toml|nx)")
# The EXIF orientations that ask a viewer to turn or flip a picture.
_TURNING_ORIENTATIONS = range(2, 9)


class Previews:
    """Draws pages, keeping what it read from pictures and fonts until their
    file changes."""

    def __init__(self):
        # {(full path, the reading's module, its name): ((modification time,
        # size), what was read)}
        self._kept = {}

    def drawing(self, root: Path, path: str, read):
        """Returns the drawing of the page whose file is `path`, within the
        source folder `root`, whose files `read(path)` returns: the drawing's
        dict with "page" and "pictureFiles", {picture name: what the webview
        loads it from (_FolderResources.picture_file)}.
        When the page's files cannot be read: {"page", "error"}. Returns None
        when `path` is not a page's own file."""
        page = page_of_file(path)
        if page is None:
            return None
        try:
            read(page_toml_path(page))
        except NxwrightError:
            return None     # such as a .nx file of pages/ that no page owns
        try:
            app, components = read_page_components(read, page)
        except NxwrightError as error:
            return {"page": page, "error": str(error)}
        if page not in app["pages"]:
            return None
        drawing = self.drawing_of(root, app, components)
        drawing["page"] = page
        return drawing

    def drawing_of(self, root: Path, app: dict, components: list, painted=(),
                   spacing: tuple = (0, 0), hidden=(), waves: dict = None,
                   pressed: str = None, listings: dict = None,
                   select_moves: dict = None, cards=None, scrolled: dict = None) -> dict:
        """Returns the drawing of `components`, as a simulation has them,
        with what drawing commands `painted` (page_drawing.py), and the
        files of its pictures under "pictureFiles". `app` is the source
        folder's app.toml; `hidden`, the components `vis` hid; `waves`, the
        points of its waveforms; `pressed`, the component held down;
        `listings`, the entries of its file browsers; `select_moves`, how far
        a press has moved a select's lines; `cards`, its SD cards given
        folders (testing/sd_cards.py), whose files external pictures show;
        `scrolled`, where its scrolling texts have moved their texts."""
        resources = _FolderResources(root, app, self, cards)
        drawing = draw_page(components, resources, painted, spacing, hidden, waves, pressed,
                            listings, select_moves, scrolled)
        pictures = {shape["picture"] for shape in drawing["shapes"] if shape["kind"] == "picture"}
        drawing["pictureFiles"] = {name: resources.picture_file(name) for name in pictures}
        return drawing

    def simulation_drawing(self, simulation, inputs) -> dict:
        """Returns the drawing of what `simulation`'s screen shows, from
        `inputs`, the DrawingInputs that simulation.drawing_inputs() gave:
        after a page change while `ref_stop` holds, the page before, until
        `ref_star`. Beside drawing_of's, it gives "page", the page shown;
        "dim" and "asleep", the screen's brightness and sleep, which are its
        own, not the page's; and "start" and "entry", which start of the
        screen and which entry of the page it belongs to. The panel draws a
        page without background over what the screen showed when the page
        was entered, and over black after a start
        (drawing/screen_pictures.py)."""
        drawing = self.drawing_of(simulation.source_folder, simulation.app, inputs.components,
                                  inputs.painted, inputs.spacing, inputs.hidden, inputs.waves,
                                  inputs.pressed, inputs.listings, inputs.select_moves,
                                  simulation.cards, inputs.scrolled)
        drawing.update({"page": inputs.page, "dim": simulation.globals.get("dim", 100),
                        "asleep": simulation.asleep, "start": simulation.starts,
                        "entry": inputs.entry})
        return drawing

    def kept(self, path: Path, read):
        """Returns read(path), or what it returned before while the file is
        unchanged. An NxwrightError it raises is kept and raised again. A
        file read two ways, such as a card's file that an external picture
        shows and a video plays, is kept once for each: by `read`'s name, a
        lambda's being that of the place it is written."""
        try:
            status = os.stat(path)
            stamp = (status.st_mtime_ns, status.st_size)
        except OSError:
            raise NxwrightError("%s cannot be read" % path.name) from None
        key = (path, read.__module__, read.__qualname__)
        kept = self._kept.get(key)
        if kept is None or kept[0] != stamp:
            try:
                kept = (stamp, read(path))
            except NxwrightError as error:
                kept = (stamp, error)
            except OSError as error:
                kept = (stamp, NxwrightError("%s cannot be read (%s)" % (path.name, error)))
            self._kept[key] = kept
        if isinstance(kept[1], NxwrightError):
            raise kept[1]
        return kept[1]


def page_of_file(path: str):
    """Returns the page whose own .page.toml or .nx file is `path`, a path within
    the source folder, or None."""
    found = _PAGE_FILE.fullmatch(path)
    return found[1] if found else None


class _FolderResources(DrawingResources):
    """The pictures, fonts, animations, and videos of a source folder, as
    page_drawing needs them, and the files of a simulation's SD cards given
    folders, `cards`."""

    def __init__(self, root: Path, app: dict, previews: Previews, cards=None):
        self.root, self.app, self.previews, self.cards = root, app, previews, cards
        self.encoding = app.get("encoding", DrawingResources.encoding)
        self.rotation = app.get("rotation", DrawingResources.rotation)
        try:
            self.opaque_pictures = \
                model_named(app.get("screen", "")).picture_format != FORMAT_COMPRESSED
        except NxwrightError:
            pass    # a screen nxwright does not know, which the build refuses
        # The cards' files the drawing shows, by the name its shapes give
        # them: their full path, which no picture of the folder is named.
        self._card_files = {}

    def card_picture(self, path: str):
        """The file `path` names on a card given a folder, found through the
        cards' own checks, or None for none such, and for a picture file of
        PictureBox's (.xi) that cannot be read: nothing is drawn, as for a
        missing file."""
        local = self._card_file(path)
        if local is None:
            return None
        try:
            self.previews.kept(local, _card_picture_parts)
        except NxwrightError:
            return None
        self._card_files[str(local)] = local
        return str(local)

    def card_frames(self, path: str):
        """The frames of the video file `path` names on a card given a
        folder, or None for none such."""
        local = self._card_file(path)
        return None if local is None else self.previews.kept(
            local, lambda file: video_frames(file.read_bytes()))

    def _card_file(self, path: str):
        """The file of the computer that `path` names on a card given a
        folder, found through the cards' own checks, or None for none such."""
        if self.cards is None or not self.cards.owns(path):
            return None
        try:
            local = self.cards.local(path)
            return local if local.is_file() else None
        except (CardRefusal, OSError):
            return None

    def frames(self, kind: str, media_id: int):
        names = self.app[LISTS[kind]]
        if not isinstance(media_id, int) or not 0 <= media_id < len(names):
            return None
        read = animation_frames if kind == ANIMATION else video_frames
        return self.previews.kept(self.root / played_file(kind, names[media_id]),
                                  lambda file: read(file.read_bytes()))

    def picture(self, picture_id: int):
        pictures = self.app["pictures"]
        return pictures[picture_id] if picture_id < len(pictures) else None

    def picture_file(self, name: str) -> dict:
        """What the webview loads the picture `name` from: "path", its file;
        or, for a card's picture file of PictureBox's (.xi), "data", its JPEG
        picture's data URL, and "mask", a PNG data URL of its transparency,
        when it has some (_card_picture_parts); or, for a project's picture
        whose file asks to be turned, "data", its pixels as they are stored
        (_unturned_picture). And "version", the file's
        modification time: the webview keeps pictures by their address, and
        the version gives a changed file a new one."""
        path = self.picture_path(name)
        found = {"version": _modified(path)}
        parts = None
        try:
            parts = self.previews.kept(path, _card_picture_parts if name in self._card_files
                                       else _unturned_picture)
        except NxwrightError:
            # A file missing or damaged goes by its path: it does not load,
            # and nothing is drawn.
            parts = None
        if parts is None:
            found["path"] = str(path)
        else:
            found["data"] = parts[0]
            if parts[1] is not None:
                found["mask"] = parts[1]
        return found

    def picture_path(self, name: str) -> Path:
        if name in self._card_files:
            return self._card_files[name]
        return self.root / picture_file(name, lambda path: (self.root / path).is_file())

    def picture_size(self, picture_id: int):
        name = self.picture(picture_id)
        if name is None:
            return None
        try:
            return self.previews.kept(self.picture_path(name), picture_size)
        except NxwrightError:
            return None

    def font(self, font_id: int):
        return self.previews.kept(self._font_path(font_id),
                                  lambda file: decode_font(file.read_bytes()))

    def font_height(self, font_id: int):
        try:
            return self.previews.kept(self._font_path(font_id), read_font_header).height
        except NxwrightError:
            return None

    def _font_path(self, font_id: int) -> Path:
        """The file of the folder's font `font_id`. Raises NxwrightError when
        the folder has none such."""
        fonts = self.app["fonts"]
        if font_id >= len(fonts):
            raise NxwrightError("the folder has no font %d" % font_id)
        return self.root / "fonts" / (fonts[font_id] + ".zi")


def _card_picture_parts(file: Path):
    """Returns (its JPEG picture, its mask or None), both as data URLs, of a
    card's picture file of PictureBox's (media_files.read_card_picture): the
    mask a PNG picture of the JPEG's size, white, as transparent as the file
    keeps each pixel. None for a file of another kind, such as a PNG or a
    JPEG, which the webview loads as it is. Raises NxwrightError for a .xi
    file that cannot be read."""
    data = file.read_bytes()
    if not is_card_picture(data):
        return None
    picture = read_card_picture(data)
    mask = None
    if picture.alphas is not None:
        # The file keeps 7 bits of alpha: 127 is opaque.
        mask = data_url(write_png(*picture.stored_size, bytes(
            value for alpha in picture.alphas
            for value in (255, 255, 255, (alpha * 255 + OPAQUE // 2) // OPAQUE))))
    return data_url(picture.jpeg, "image/jpeg"), mask


def _unturned_picture(file: Path):
    """Returns (a PNG data URL of the picture's pixels as stored, None) for a
    picture file whose EXIF orientation asks a viewer to turn it, as a
    phone's JPEG may: the Editor does not turn it, and the webview's browser
    would. None for any other file, which the webview loads as it is, or
    one Pillow does not read."""
    if exif_orientation(file) not in _TURNING_ORIENTATIONS:
        return None
    picture = read_picture(file.read_bytes())
    return data_url(write_png(picture.width, picture.height, picture.tobytes())), None


def _modified(path: Path) -> str:
    """Returns a file's modification time in nanoseconds, or "0" when it
    cannot be read. As text: JSON numbers that large lose digits in JavaScript."""
    try:
        return str(os.stat(path).st_mtime_ns)
    except OSError:
        return "0"

