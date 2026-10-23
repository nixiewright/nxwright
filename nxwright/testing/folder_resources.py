"""A source folder's fonts and pictures, as working out a list component's
layout reads them (list_working.py), in tests and in the simulator alike:
a font's glyphs, its height, and a picture's size, each by its ID in
app.toml. A font is decoded once while its file stays unchanged, as one in
utf-8 takes some 20 ms to decode; a picture's size is read each time, so
that a picture changed while the app runs counts.
"""
from pathlib import Path

from nxwright import NxwrightError
from nxwright.project.pictures import picture_size
from nxwright.project.zi_font import decode_font, read_font_header
from nxwright.source import source_folder as folders


class FolderResources:
    """The fonts and pictures of the source folder `source_folder`, whose
    app.toml settings are `app`. `decoded`, when given, keeps the fonts
    decoded, {path: ((modified time, size), Font)}, as one simulation's
    starts share it."""

    def __init__(self, source_folder: Path, app: dict, decoded: dict = None):
        self.source_folder, self.app = Path(source_folder), app
        self._decoded = {} if decoded is None else decoded

    def font(self, font):
        """The folder's font of ID `font`, decoded (zi_font.Font), or None
        when it has none such or it cannot be read."""
        path = self._font_path(font)
        if path is None:
            return None
        try:
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            kept = self._decoded.get(path)
            if kept is None or kept[0] != stamp:
                kept = self._decoded[path] = stamp, decode_font(path.read_bytes())
            return kept[1]
        except (OSError, NxwrightError):
            return None

    def font_height(self, font) -> int:
        """The height of the folder's font of ID `font`, or 0 when there is
        none such or it cannot be read. Its header alone is read."""
        path = self._font_path(font)
        if path is None:
            return 0
        try:
            return read_font_header(path).height
        except (OSError, NxwrightError):
            return 0

    def picture_size(self, picture):
        """The (width, height) of the folder's picture of ID `picture`, or
        None when there is none such or it cannot be read."""
        pictures = self.app["pictures"]
        if not isinstance(picture, int) or not 0 <= picture < len(pictures):
            return None
        path = folders.picture_file(pictures[picture],
                                    lambda relative: (self.source_folder / relative).is_file())
        try:
            return picture_size(self.source_folder / path)
        except NxwrightError:
            return None

    def _font_path(self, font):
        fonts = self.app["fonts"]
        if not isinstance(font, int) or not 0 <= font < len(fonts):
            return None
        return self.source_folder / "fonts" / (fonts[font] + ".zi")
