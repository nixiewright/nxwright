"""The page preview's drawings, for the language server's nxwright/pageDrawing
request, and for the debugger's panel of a simulation and the pictures an
agent takes of it (drawing/screen_pictures.py).

A drawing (drawing/page_drawing.py) shows the page whose .page.toml or .nx
file is asked about, from its page file as the editor has it, saved or not.
The page's code plays no part, so a page whose code does not build still
draws.

A page is drawn again at each pause in typing, so decoded fonts, the sizes of
pictures, and what each component painted are kept between drawings. A font
or a size is kept until its file changes, and a painting until something it
depends on changes (drawing/kept_paintings.py).
"""
import os
from pathlib import Path
import re

from nxwright import NxwrightError
from nxwright.drawing.kept_paintings import KeptPaintings
from nxwright.drawing.page_drawing import DrawingResources, draw_page
from nxwright.language.resource_names import ANIMATION, LISTS
from nxwright.project.media_files import (animation_frames, is_card_picture, read_card_picture,
                                          video_frames)
from nxwright.project.page_file_names import page_of_file_stem
from nxwright.project.pictures import data_url, drawing_png, exif_orientation, read_picture
from nxwright.project.screen_copy import FORMAT_COMPRESSED, OPAQUE
from nxwright.project.screen_models import model_named
from nxwright.project.zi_font import decode_font, read_font_header
from nxwright.source.page_source import page_header_of_text, page_toml_path
from nxwright.source.source_folder import (folder_byte_reader, folder_reader, is_svg_picture,
                                           picture_file, picture_file_size, played_file,
                                           read_page_components)
from nxwright.source.svg_pictures import svg_picture_data_url
from nxwright.testing.sd_cards import CardRefusal

# A page's own files: pages/<name>.page.toml and pages/<name>.nx.
_PAGE_FILE = re.compile(r"pages/([^/]+)\.(?:page\.toml|nx)")
# The EXIF orientations that ask a viewer to turn or flip a picture.
_TURNING_ORIENTATIONS = range(2, 9)


class Previews:
    """Draws pages. Between drawings it keeps what it read from pictures and
    fonts, until their file changes, and what each component painted in the
    latest drawing of its page, until something that painting depends on
    changes."""

    def __init__(self):
        # {(full path, the reading's module, its name): ((modification time,
        # size), what was read)}
        self._kept = {}
        # {source folder: its KeptPaintings}
        self._paintings = {}

    def drawing(self, root: Path, path: str, read):
        """Returns the drawing of the page whose file is `path`, within the
        source folder `root`, whose files `read(path)` returns: the drawing's
        dict with "page" and "pictureFiles", {picture name: what the webview
        loads it from (_FolderResources.picture_file)}, and "locked", true,
        when the page file locks the page.
        When the page's files cannot be read: {"page", "error"}. Returns None
        when `path` is not a page's own file."""
        page = page_of_file(path)
        if page is None:
            return None
        try:
            text = read(page_toml_path(page))
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
        try:
            if page_header_of_text(text, page, app["defines"]).locked:
                drawing["locked"] = True
        except NxwrightError:
            pass    # the build's message comes with the edits the preview sends
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
                            listings, select_moves, scrolled,
                            self._paintings.setdefault(root, KeptPaintings()))
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

    def kept(self, path: Path, read, stamp: tuple = None):
        """Returns read(path), or what it returned before while the file is
        unchanged. An NxwrightError it raises is kept and raised again. A
        file read two ways, such as a card's file that an external picture
        shows and a video plays, is kept once for each way. The ways are
        told apart by the name of `read`, or, for a lambda, by the function
        it is written in. A caller that already has the file's file_stamp
        can pass it as `stamp`."""
        stamp = stamp or file_stamp(path)
        if stamp is None:
            raise NxwrightError("%s cannot be read" % path.name)
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
    the source folder, or None. The file's name encodes the characters that
    Windows refuses in a file name, and this function decodes them
    (page_file_names.py)."""
    found = _PAGE_FILE.fullmatch(path)
    return page_of_file_stem(found[1]) if found else None


class _FolderResources(DrawingResources):
    """The pictures, fonts, animations, and videos of a source folder, as
    page_drawing needs them, and the files of a simulation's SD cards given
    folders, `cards`. Each instance serves a single drawing, during which it
    looks up what each number or name stands for, and the state of each file,
    only once. While recording (DrawingResources.start_recording), it notes
    what a painting reads in a _Reads."""

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
        # them. That name is the file's full path, so it cannot be the name
        # of a picture of the folder.
        self._card_files = {}
        # {(finding function, its arguments): what it found}, and {file: its
        # file_stamp}, for this drawing.
        self._found, self._stamps = {}, {}
        self._reads = None      # the _Reads being recorded, if any

    def start_recording(self) -> bool:
        self._reads = _Reads()
        return True

    def stop_recording(self):
        reads, self._reads = self._reads, None
        return reads

    def unchanged(self, reads) -> bool:
        return (all(self._resolved(find, *arguments) == found
                    for (find, arguments), found in reads.resolved.items())
                and all(self._stamp(file) == stamp for file, stamp in reads.files.items()))

    def record_again(self, reads):
        self._card_files.update(reads.card_files)

    def _resolved(self, find, *arguments):
        """Returns find(self, *arguments), which is what a number or a name
        stands for. The answer is looked up once per drawing, and is also
        added to the _Reads while recording. `find` must be one of the
        class's own functions, so that the resources of a later drawing can
        call it again."""
        key = (find, arguments)
        if key not in self._found:
            self._found[key] = find(self, *arguments)
        if self._reads is not None:
            self._reads.resolved[key] = self._found[key]
        return self._found[key]

    def _stamp(self, file: Path):
        """Returns the file_stamp of `file`, taken once per drawing."""
        if file not in self._stamps:
            self._stamps[file] = file_stamp(file)
        return self._stamps[file]

    def _kept(self, file: Path, read):
        """Returns Previews.kept(file, read). While recording, it also
        records the file's stamp, even when the file is missing and
        Previews.kept raises."""
        stamp = self._stamp(file)
        if self._reads is not None:
            self._reads.files[file] = stamp
        return self.previews.kept(file, read, stamp)

    def card_picture(self, path: str):
        """Returns the name under which picture shapes show the file that
        `path` names on a card given a folder, and remembers the file for
        picture_file. The file is found through the cards' own checks.
        Returns None, so that nothing is drawn, when there is no such file,
        or when it is a PictureBox picture file (.xi) that cannot be read."""
        local = self._resolved(_FolderResources._card_file, path)
        if local is None:
            return None
        try:
            self._kept(local, _card_picture_parts)
        except NxwrightError:
            return None
        self._card_files[str(local)] = local
        if self._reads is not None:
            self._reads.card_files[str(local)] = local
        return str(local)

    def card_frames(self, path: str):
        """The frames of the video file `path` names on a card given a
        folder, or None for none such."""
        local = self._resolved(_FolderResources._card_file, path)
        return None if local is None else self._kept(
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
        file = self._resolved(_FolderResources._media_file, kind, media_id)
        if file is None:
            return None
        read = animation_frames if kind == ANIMATION else video_frames
        return self._kept(file, lambda file: read(file.read_bytes()))

    def _media_file(self, kind: str, media_id: int):
        """The file of the folder's animation or video `media_id`, or None
        when the folder has none such."""
        names = self.app[LISTS[kind]]
        if not isinstance(media_id, int) or not 0 <= media_id < len(names):
            return None
        return self.root / played_file(kind, names[media_id])

    def picture(self, picture_id: int):
        return self._resolved(_FolderResources._picture_name, picture_id)

    def _picture_name(self, picture_id: int):
        """The name of the folder's picture `picture_id`, or None."""
        pictures = self.app["pictures"]
        return pictures[picture_id] if picture_id < len(pictures) else None

    def picture_file(self, name: str) -> dict:
        """What the webview loads the picture `name` from: "path", its file;
        or, for a card's picture file of PictureBox's (.xi), "data", its JPEG
        picture's data URL, and "mask", a PNG data URL of its transparency,
        when it has some (_card_picture_parts); or, for a project's picture
        whose file asks to be turned, "data", its pixels as they are stored
        (_unturned_picture); or, for an SVG picture, "data", the PNG picture
        drawn from it (_svg_picture). And "version", the file's
        modification time: the webview keeps pictures by their address, and
        the version gives a changed file a new one."""
        path = self.picture_path(name)
        if name not in self._card_files and is_svg_picture(path.name):
            return self._svg_picture(path)
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

    def _svg_picture(self, path: Path) -> dict:
        """What the webview loads the SVG picture whose file is `path` from:
        "data", the PNG picture drawn from it, and "version", the key of its
        drawing, which changes with any file it reads, not only its own. For
        a picture that cannot be drawn, it gives neither data nor a path, so
        nothing is drawn, the same as for a damaged file. It never gives a
        path, because the webview's browser would then draw the SVG file
        itself."""
        relative = path.relative_to(self.root).as_posix()
        try:
            data, key = svg_picture_data_url(relative, folder_reader(self.root),
                                             folder_byte_reader(self.root), self.app["defines"])
        except NxwrightError:
            return {"version": "0"}
        return {"data": data, "version": key}

    def picture_path(self, name: str) -> Path:
        if name in self._card_files:
            return self._card_files[name]
        return self._resolved(_FolderResources._picture_file_path, name)

    def _picture_file_path(self, name: str) -> Path:
        """The file of the folder's picture `name`, with the first picture
        suffix whose file exists (source_folder.picture_file)."""
        return self.root / picture_file(name, lambda path: (self.root / path).is_file())

    def picture_size(self, picture_id: int):
        name = self.picture(picture_id)
        if name is None:
            return None
        try:
            return self._kept(self.picture_path(name), picture_file_size)
        except NxwrightError:
            return None

    def font(self, font_id: int):
        return self._kept(self._font_path(font_id), lambda file: decode_font(file.read_bytes()))

    def font_height(self, font_id: int):
        try:
            return self._kept(self._font_path(font_id), read_font_header).height
        except NxwrightError:
            return None

    def _font_path(self, font_id: int) -> Path:
        """The file of the folder's font `font_id`. Raises NxwrightError when
        the folder has none such."""
        file = self._resolved(_FolderResources._font_file, font_id)
        if file is None:
            raise NxwrightError("the folder has no font %d" % font_id)
        return file

    def _font_file(self, font_id: int):
        """The file of the folder's font `font_id`, or None when the folder
        has none such."""
        fonts = self.app["fonts"]
        return self.root / "fonts" / (fonts[font_id] + ".zi") if font_id < len(fonts) else None


class _Reads:
    """What a painting read through _FolderResources:
      - resolved: {(finding function, its arguments): what it found};
      - files: {file: its file_stamp, or None when missing};
      - card_files: {name: file}, the card files its picture shapes show,
        by the name the shapes give them."""

    def __init__(self):
        self.resolved, self.files, self.card_files = {}, {}, {}


def file_stamp(file: Path):
    """Returns (modification time, size) of `file`, or None when it cannot
    be read. Two stamps that differ show that the file changed."""
    try:
        status = os.stat(file)
    except OSError:
        return None
    return status.st_mtime_ns, status.st_size


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
        mask = data_url(drawing_png(*picture.stored_size, bytes(
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
    return data_url(drawing_png(picture.width, picture.height, picture.tobytes())), None


def _modified(path: Path) -> str:
    """Returns a file's modification time in nanoseconds, or "0" when it
    cannot be read. As text: JSON numbers that large lose digits in JavaScript."""
    try:
        return str(os.stat(path).st_mtime_ns)
    except OSError:
        return "0"

