"""Drawing an animation (gmov) or a video, as the Editor's simulator shows
them: the frame its `tim` falls on, at the component's top left corner, at
the frame's own size, in its JPEG picture's own colours, not the screen's 16
bits (project/media_files.py says which frame). It showed a red frame as
(253, 1, 0), a colour of no 16-bit pixel.

The page preview, which runs nothing, draws the frame at the page file's
`tim`, the first by default, as the screen shows it as the page opens. A
simulation moves `tim` as the component plays (testing/media_players.py).

A file made for a turned screen stores each frame padded, then turned
(project/media_files.py). Its frame's shape carries the file's own
rotation, which the webview turns it back by, before cutting it to the
frame's size. The Editor's simulator showed a frame upright so, whether its
file was made for the screen's rotation or for an upright one, in a project
and on an SD card, at 90, 180, and 270 degrees
(tests/fixtures/drawing-assumptions/turned/).

An animation whose `from` is 1 has no `vid`, and plays the project's
first animation, as the Editor's simulator played it (played_animation).

A video whose `from` is 1 plays the file its `path` names on an SD card.
It is drawn when the file can be read, from a card given a folder
(resources.card_frames), and otherwise not, as an external picture is not.
A `vid` of 65535, none, draws nothing; one the folder has no animation or
video of, or a file whose frames cannot be read, is outlined with a note
saying why.
"""
from nxwright import NxwrightError
from nxwright.language.resource_names import ANIMATION, NOUNS, VIDEO
from nxwright.project.editor_limits import lacked_attributes
from nxwright.project.media_files import FROM_CARD
from nxwright.project.pictures import data_url

# A `vid` meaning none.
_NONE = 65535


def played_animation(value_of):
    """Returns the ID of the animation an animation component plays,
    `value_of(attribute)` giving its values: its `vid`, or 0, the project's
    first animation, while it lacks its `vid` (its `from` is 1)
    (editor_limits.lacked_attributes). None when it has no `vid` at all."""
    if "vid" in lacked_attributes("gmov", value_of):
        return 0
    return value_of("vid")


def paint_animation(painter):
    """Paints an animation's frame."""
    _paint_frame(painter, ANIMATION, media_id=played_animation(painter.values.get))


def paint_video(painter):
    """Paints a video's frame, from the project or from an SD card."""
    if painter.values.get("from", 0) == FROM_CARD:
        _paint_frame(painter, VIDEO, card_path=painter.values.get("path", ""))
    else:
        _paint_frame(painter, VIDEO, media_id=painter.values.get("vid"))


def _paint_frame(painter, kind: str, card_path: str = None, media_id: int = None):
    """Paints the frame of the animation or video (`kind`) of the ID
    `media_id`, or of the file `card_path` names on a card."""
    values = painter.values
    try:
        if card_path is not None:
            frames = painter.resources.card_frames(card_path)
        elif media_id is None or media_id == _NONE:
            return
        else:
            frames = painter.resources.frames(kind, media_id)
            if frames is None:
                painter.note("vid %d is not %s of the folder" % (media_id, _a(kind)))
                painter.add("outline", label=painter.component.name)
                return
    except NxwrightError as error:
        painter.note("its %s cannot be shown: %s" % (NOUNS[kind], error))
        painter.add("outline", label=painter.component.name)
        return
    if frames is None or not frames.pictures:
        return
    picture = frames.pictures[frames.at(values.get("tim", 0))]
    box = painter.box
    turned = {"rotation": frames.rotation} if frames.rotation else {}
    painter.add("text", {"x": box["x"], "y": box["y"], "w": frames.width, "h": frames.height},
                image=data_url(picture, "image/jpeg"), **turned)


def _a(kind: str) -> str:
    """The kind's noun after its article: "an animation", "a video"."""
    noun = NOUNS[kind]
    return ("an " if noun[0] in "aeiou" else "a ") + noun
