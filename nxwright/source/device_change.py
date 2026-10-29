"""Changing a source folder's screen model, rotation, and encoding,
`app.toml`'s `screen`, `rotation`, and `encoding`, and the files that depend
on them, as the Nextion Editor's Device window changes a project's. The
Editor 1.68.2 gave each page the new screen's size, at its rotation, and
kept every component's place and size, and every picture, animation, and
video. For a new rotation, it turned each font. For a new encoding, it kept
each text's bytes and each font (docs/commands.md, device).

Beyond the Editor: a video is made for one rotation. The Editor's compile
refuses one made for another, so the build does too. The video's source is
not kept, so each one is made again from its own frames
(media_files.turned_video). A source folder keeps its texts as characters,
which the build stores in the folder's encoding, so its fonts are converted
to the new encoding, each glyph keyed by its character
(zi_font.converted_font), where the Editor keeps the old bytes and fonts. A
source folder keeps every font in its encoding and at its rotation, so a
font nxwright cannot convert or turn, one it does not read, refuses the
change.

After a change, the folder's checks say what the build then refuses, such as
a component past a smaller screen's edge, a type the new series lacks, or a
text the new encoding cannot store.
"""
from dataclasses import dataclass, replace
from pathlib import Path

from nxwright import NxwrightError
from nxwright.source.folder_index import APP_FILE, FolderIndex, text_on_disk
from nxwright.source.page_edits import attribute_edits, edited_text
from nxwright.project.device_settings import encoding_code
from nxwright.project.media_files import turned_video, video_frames, video_rotation
from nxwright.project.screen_copy import ROTATIONS
from nxwright.project.screen_models import model_named
from nxwright.project.zi_font import converted_font, font_facts, turned_font
from nxwright.source.device_keys import settings_from_keys
from nxwright.source.folder_check import check_folder
from nxwright.source.page_source import page_toml_path
from nxwright.source.source_folder import (app_text, folder_byte_reader, folder_reader, read_app,
                                           read_bytes, resource_paths)
from nxwright.source.resource_adding import encodings_taken

# A note names at most this many runs of the characters a converted font
# leaves out, and counts the rest. A one-byte font leaves out at most some
# 50 runs, all named. A gb2312 font made one-byte leaves out thousands,
# scattered over Unicode.
_MOST_RUNS_NAMED = 64


@dataclass
class DeviceChange:
    """What change_device did: the paths it wrote, `app.toml` last; its
    notes, as of a video made again or a font converted; and the refusals,
    each error the folder's checks then find, as "pages/home.page.toml line
    9: ..."."""
    written: list
    notes: list
    refusals: list


def change_device(source_folder: Path, screen: str = None, rotation: int = None,
                  encoding: str = None, told=None) -> DeviceChange:
    """Changes the source folder's screen model to the one named `screen`,
    its rotation to `rotation` degrees, and its encoding to the one named
    `encoding`, each when given, as the module's docstring says, then checks
    the folder. A setting given its present value changes nothing. Raises
    NxwrightError, writing nothing, as device_change_files does.

    `told`, when given, is called with a line saying what is being done, as
    each step starts: each page resized, each font turned or converted, each
    video made again, the writing, and the check. A video takes longest."""
    told = told or (lambda line: None)
    source_folder = Path(source_folder)
    files, notes = device_change_files(source_folder, screen, rotation, encoding, told)
    if files:
        told("Writing %d file(s)" % len(files))
    # app.toml comes last, so the folder keeps its old settings until the
    # files that depend on them are written.
    for path, data in files.items():
        (source_folder / path).write_bytes(data)
    refusals = []
    if files:
        told("Checking the project for what the build will refuse")
        check = check_folder(folder_reader(source_folder), _exists(source_folder),
                             read_bytes=folder_byte_reader(source_folder))
        refusals = ["%s: %s" % (finding.place, finding.message) for finding in check.errors()]
    return DeviceChange(list(files), notes, refusals)


def device_change_files(source_folder: Path, screen: str = None, rotation: int = None,
                        encoding: str = None, told=None) -> tuple:
    """Returns ({path: new bytes}, notes) of the files change_device writes,
    `app.toml` last, without writing them; {} when the settings given are
    the folder's own. Raises NxwrightError for no setting given, a screen
    model, a rotation, or an encoding there is not, a folder without device
    settings, and a font nxwright cannot convert or turn, or a file it
    cannot read, naming it. `told` is as change_device's."""
    if screen is None and rotation is None and encoding is None:
        raise NxwrightError("give a screen model, a rotation, or an encoding")
    if rotation is not None and rotation not in ROTATIONS:
        raise NxwrightError("rotation %r is not one of %s"
                            % (rotation, ", ".join(map(str, ROTATIONS))))
    if encoding is not None:
        encoding_code(encoding)
    source_folder = Path(source_folder)
    app = read_app(source_folder)
    old = settings_from_keys(app)
    if old is None:
        raise NxwrightError("app.toml holds no device settings to change")
    new = replace(old, model=old.model if screen is None else model_named(screen),
                  rotation=old.rotation if rotation is None else rotation,
                  encoding=old.encoding if encoding is None else encoding)
    if new == old:
        return {}, []
    told = told or (lambda line: None)
    files = _page_files(source_folder, app, new.page_size, told)
    notes = []
    if (new.rotation, new.encoding) != (old.rotation, old.encoding):
        fonts, notes = _changed_fonts(source_folder, app, old, new, told)
        files.update(fonts)
    if new.rotation != old.rotation:
        videos = _turned_videos(source_folder, app, new.rotation, told)
        files.update(videos)
        notes += ["%s: made again for %d degrees, its frames coded again, which loses a "
                  "little of each" % (path, new.rotation) for path in videos]
    files[APP_FILE] = app_text(dict(app, screen=new.model.name, rotation=new.rotation,
                                    encoding=new.encoding)).encode("utf-8")
    return files, notes


def _page_files(source_folder: Path, app: dict, page_size: tuple, told) -> dict:
    """Returns {path: new bytes} of each page file whose page's `w` and `h`
    are not `page_size`, those two values edited, as the Attributes section
    edits a value. `told` hears of each page resized, and of no other."""
    index = FolderIndex(source_folder, text_on_disk)
    read = folder_reader(source_folder)
    width, height = page_size
    files = {}
    for number, page in enumerate(app["pages"], 1):
        path = page_toml_path(page)
        # The edits count lines as the index reads them.
        edits = attribute_edits(index, read, page, page, {"w": width, "h": height})
        text = "\n".join(index.lines(path))
        edited = edited_text(text, edits)
        if edited != text:
            told("Resizing page %d of %d to %d x %d: %s"
                 % (number, len(app["pages"]), width, height, path))
            # The index reads LF line endings; a file of CRLF ones keeps them.
            if b"\r\n" in read_bytes(source_folder / path):
                edited = edited.replace("\n", "\r\n")
            files[path] = edited.encode("utf-8")
    return files


def _changed_fonts(source_folder: Path, app: dict, old, new, told) -> tuple:
    """Returns ({path: new bytes}, notes) of the folder's fonts changed for
    the settings `new`, from `old`: when the encoding changes, converted to
    the new one (zi_font.converted_font), at the new rotation, if in the old
    encoding or in one the new does not take (resource_adding.encodings_taken);
    else turned to the new rotation (zi_font.turned_font). So a keyboard's
    iso-8859-1 font in a utf-8 folder stays in iso-8859-1 when the folder is
    made iso-8859-1. Raises NxwrightError, naming the font, for one nxwright
    cannot convert or turn. `told` hears of each font changed."""
    files, notes = {}, []
    taken = encodings_taken(new.encoding)
    for number, name in enumerate(app["fonts"], 1):
        for path in resource_paths("fonts", name, _exists(source_folder)):
            block = read_bytes(source_folder / path)
            try:
                facts = font_facts(block)
            except NxwrightError as error:
                raise NxwrightError("%s: %s" % (path, error)) from None
            # A font in another encoding than the folder's, as an extracted
            # project may hold, stays in it while the folder's encoding stays.
            converted = new.encoding != old.encoding and facts.encoding != new.encoding and (
                facts.encoding == old.encoding or facts.encoding not in taken)
            if converted:
                told("Converting font %d of %d to %s: %s"
                     % (number, len(app["fonts"]), new.encoding, path))
                try:
                    files[path], left_out = converted_font(block, new.encoding, new.rotation)
                except NxwrightError as error:
                    raise NxwrightError("%s: nxwright cannot convert it to %s, and a source "
                                        "folder keeps every font in its encoding: %s"
                                        % (path, new.encoding, error)) from None
                note = "%s: converted to %s" % (path, new.encoding)
                if left_out:
                    note += (", leaving out %s, which %s lacks, or which come before the "
                             "space. A one-byte font starts at the space, as a two-byte "
                             "font's ascii does" % (_code_points(left_out), new.encoding))
                notes.append(note)
            elif facts.rotation != new.rotation:
                told("Rotating font %d of %d to %d degrees: %s"
                     % (number, len(app["fonts"]), new.rotation, path))
                try:
                    files[path] = turned_font(block, new.rotation)
                except NxwrightError as error:
                    raise NxwrightError("%s: nxwright cannot turn it to %d degrees, and a source "
                                        "folder keeps every font at its rotation: %s"
                                        % (path, new.rotation, error)) from None
    return files, notes


def _code_points(codes: list) -> str:
    """Code points as a note lists them, a run as a range: "U+0000 to
    U+001F, U+00F1". Past _MOST_RUNS_NAMED runs, the rest are counted:
    "U+0101, ..., U+25B2 to U+25B3, and 7125 more characters"."""
    runs = []
    for code in sorted(codes):
        if runs and code == runs[-1][1] + 1:
            runs[-1][1] = code
        else:
            runs.append([code, code])
    named = ", ".join("U+%04X" % first if first == last else "U+%04X to U+%04X" % (first, last)
                      for first, last in runs[:_MOST_RUNS_NAMED])
    rest = sum(last - first + 1 for first, last in runs[_MOST_RUNS_NAMED:])
    if rest == 0:
        return named
    return "%s, and %d more %s" % (named, rest, "character" if rest == 1 else "characters")


def _turned_videos(source_folder: Path, app: dict, rotation: int, told) -> dict:
    """Returns {path: new bytes} of each video of the folder made for another
    rotation than `rotation`, made again for it (media_files.turned_video).
    Raises NxwrightError, naming the video, for one it cannot read. `told`
    hears of each video made again, with its number of frames, as each
    frame is coded again."""
    files = {}
    for number, name in enumerate(app["videos"], 1):
        for path in resource_paths("videos", name, _exists(source_folder)):
            video = read_bytes(source_folder / path)
            try:
                if video_rotation(video) != rotation:
                    told("Rotating video %d of %d to %d degrees, %d frames: %s"
                         % (number, len(app["videos"]), rotation,
                            len(video_frames(video).pictures), path))
                turned = turned_video(video, rotation)
            except NxwrightError as error:
                raise NxwrightError("%s: %s" % (path, error)) from None
            if turned is not video:
                files[path] = turned
    return files


def _exists(source_folder: Path):
    """Whether the folder holds a file, by its path within the folder."""
    return lambda path: (source_folder / path).is_file()
