"""The language server's answer for nxwright's media viewer in VS Code
(editors/vscode/src/mediaViewer.ts): the frames of an animation or a video
file, each a JPEG picture as a data: URL, as stored, padded and turned for
the screen's rotation the file was made for, and when each starts showing
(project/media_files.py, Frames). The viewer turns them back and plays them.
"""
from pathlib import Path

from nxwright import NxwrightError
from nxwright.project.media_files import animation_frames, video_frames
from nxwright.project.pictures import data_url

# The suffixes of an animation's two files: GmovMaker's, and the screen's
# form, which holds the frames (project/resources.py, ANIMATIONS).
_GMOV = ".gmov"
_SCREEN_GMOV = ".screen.gmov"
_VIDEO = ".video"


def media_frames(media_file: Path) -> dict:
    """Returns {"width", "height", "rotation", "pictures", "starts", "length"}
    of an animation or a video file, as Frames holds them, each picture a
    data: URL. An animation in GmovMaker's form plays the screen's form
    beside it, of the same name, which holds the frames. Raises
    NxwrightError for a file that cannot be read, or that is neither."""
    media_file = Path(media_file)
    name = media_file.name.lower()
    if name.endswith(_SCREEN_GMOV):
        frames = animation_frames(_read(media_file))
    elif name.endswith(_GMOV):
        screen = media_file.with_name(media_file.name[:-len(_GMOV)] + _SCREEN_GMOV)
        if not screen.is_file():
            raise NxwrightError("%s is GmovMaker's form of an animation, whose frames %s holds, "
                                "which is not beside it" % (media_file.name, screen.name))
        frames = animation_frames(_read(screen))
    elif name.endswith(_VIDEO):
        frames = video_frames(_read(media_file))
    else:
        raise NxwrightError("%s is neither an animation nor a video" % media_file.name)
    return {"width": frames.width, "height": frames.height, "rotation": frames.rotation,
            "pictures": [data_url(picture, "image/jpeg") for picture in frames.pictures],
            "starts": list(frames.starts), "length": frames.length}


def _read(path: Path) -> bytes:
    """Returns a file's bytes. Raises NxwrightError when it cannot be read."""
    try:
        return path.read_bytes()
    except OSError as error:
        raise NxwrightError("%s: %s" % (path.name, error.strerror)) from None
