"""Adding resources to a source folder: pictures, fonts, animations, videos,
and sounds, each written where the folder keeps its kind (source_folder.py's
layout) and listed in app.toml after the others of its kind. A font is drawn
from a typeface file, or taken as a ready-made .zi file; an animation is
made from pictures; a video and a sound are converted, by ffmpeg where their
files need it. Removing a resource is resource_removal.py's.

Also here, as it makes pictures as add_animation reads them: writing the
picture files an external picture shows from an SD card
(write_card_pictures).
"""
from dataclasses import dataclass
from pathlib import Path
import tempfile

from nxwright import NxwrightError
from nxwright.language.resource_names import KIND_OF_LIST, NOUNS, check_names, font_header_name
from nxwright.project.ffmpeg import find_ffmpeg, sound_as_wav, video_as_pngs
from nxwright.project.font_drawing import code_points_of, draw_font_block, font_warning
from nxwright.project.media_files import (CARD_PICTURE_QUALITIES, animation_files,
                                          card_picture_file, check_video_rate, gmovmaker_frames,
                                          sound_file, video_file, video_frame)
from nxwright.project.pictures import (picture_problem, picture_size, read_picture,
                                       still_picture_size)
from nxwright.project.resources import PICTURE_SUFFIXES
from nxwright.project.truetype import TrueTypeFont
from nxwright.project.zi_font import (GRID_ENCODINGS, UTF8, decode_font, decodes, font_facts,
                                      turned_font)
from nxwright.source.device_keys import settings_from_keys
from nxwright.source.keyboards import noto_sans_covers
from nxwright.source.source_folder import (RESOURCE_FILES, app_text, drawn_font_name, name_part,
                                           parse_app, picture_paths, read_bytes, read_text)

# How long a frame of an animation's pictures shows when no duration is
# chosen, in milliseconds, as GmovMaker's default.
FRAME_DURATION = 50
# VideoBox's frame rate when none is chosen, and the rates a sound may be
# converted to: those the Editor was seen to take.
VIDEO_RATE = 12
SOUND_RATES = range(8000, 48001)


def add_pictures(source_folder: Path, files: list) -> list:
    """Copies picture files into the folder's pictures/, and lists them last
    in app.toml, in the order given. Each is named after its file, kept to
    the characters a name may have (name_part): "My Icon.jpg" gives MyIcon.
    Returns their names.

    Raises NxwrightError, before writing anything, for a file whose suffix
    is not a picture's, or that nxwright cannot read as one
    (pictures.picture_problem); a file whose name keeps no character; a
    name the folder has already, in any case, or that two files give; a
    name app.toml's pictures may not hold (check_names); and a file already
    there of a name it gives, under any picture suffix, as a picture has one
    file."""
    source_folder = Path(source_folder)
    app = parse_app(read_text(source_folder / "app.toml"))
    taken = {name.lower(): name for name in app["pictures"]}
    given = {}
    files_written = {}
    for file in map(Path, files):
        suffix = file.suffix.lower()
        if suffix not in PICTURE_SUFFIXES:
            raise NxwrightError("%s: a picture is a %s, or %s file" % (
                file.name, ", ".join(PICTURE_SUFFIXES[:-1]), PICTURE_SUFFIXES[-1]))
        data = read_bytes(file)
        problem = picture_problem(data)
        if problem:
            raise NxwrightError("%s: %s" % (file.name, problem))
        name = name_part(file.stem)
        if not name:
            raise NxwrightError("%s gives no name: a name keeps letters, digits, _ and -"
                                % file.name)
        if name.lower() in taken:
            raise NxwrightError("the folder has a picture named %s already"
                                % taken[name.lower()])
        if name.lower() in given:
            raise NxwrightError("%s and %s would both be named %s"
                                % (given[name.lower()].name, file.name, name))
        given[name.lower()] = file
        files_written["pictures/%s%s" % (name, suffix)] = data
    names = [name_part(file.stem) for file in given.values()]
    pictures = app["pictures"] + names
    check_names(pictures, "pictures")
    # A picture has one file, so a file of its name under any suffix is in the way.
    for relative in (path for name in names for path in picture_paths(name)):
        if (source_folder / relative).exists():
            raise NxwrightError("%s is already there, though app.toml does not list it"
                                % (source_folder / relative))
    for relative, content in files_written.items():
        (source_folder / relative).parent.mkdir(parents=True, exist_ok=True)
        (source_folder / relative).write_bytes(content)
    (source_folder / "app.toml").write_text(app_text(dict(app, pictures=pictures)),
                                           encoding="utf-8", newline="\n")
    return names


def add_font(source_folder: Path, font_file: Path, height: int, name: str = None,
             smoothed: bool = True, characters: str = None, full_table: bool = False) -> tuple:
    """Draws a font from a typeface file (font_drawing.py), `height` pixels
    tall, smoothed or not, in the source folder's encoding and turned to its
    rotation. In utf-8, it holds the code points `characters` gives, as
    code_points_of reads them, or else U+0000 to U+00FF, in a table of them
    and the space alone, or, as a `full_table`, in one of every code point
    (zi_font.encode_font). Writes it to fonts/<name>.zi, and lists it in
    app.toml after the folder's fonts. Its name is `name`, or else
    drawn_font_name's. Returns (the name, a warning or None): the warning
    says what characters the typeface file lacks, which the font leaves out
    (font_drawing.font_warning).

    Raises NxwrightError, before writing anything, for what check_drawn_font
    refuses, `characters` code_points_of refuses, a font draw_font refuses,
    and a full table in a folder not in utf-8.
    """
    source_folder, font_file = Path(source_folder), Path(font_file)
    typeface = TrueTypeFont(read_bytes(font_file))
    name = name or drawn_font_name(typeface.typeface_name(), font_file, height)
    app, settings, path = _drawn_font_place(source_folder, name)
    if full_table and settings.encoding != UTF8:
        raise NxwrightError("a font in %s holds every character of its encoding: a full table "
                            "is for a utf-8 folder" % settings.encoding)
    code_points = None if characters is None else code_points_of(characters)
    block = draw_font_block(name, typeface, height, settings.encoding, settings.rotation,
                            smoothed, code_points, full_table)
    _add_resource(source_folder, app, "fonts", name, [(path, block)])
    return name, font_warning(typeface, settings.encoding, code_points, full_table)


def check_drawn_font(source_folder: Path, name: str):
    """Raises NxwrightError where add_font would refuse a font named `name`
    for any reason but its typeface file and its characters: a folder without
    screen settings or in a two-byte encoding, a name the folder has, or a
    file already at the font's place."""
    _drawn_font_place(Path(source_folder), name)


def _drawn_font_place(source_folder: Path, name: str) -> tuple:
    """Returns (the folder's app.toml settings, its screen settings, the
    font's path) for a font named `name` to draw into it. Raises
    NxwrightError as check_drawn_font says."""
    app = parse_app(read_text(source_folder / "app.toml"))
    settings = font_settings(settings_from_keys(app))
    return app, settings, _new_resource_paths(source_folder, app, "fonts", name)[0]


@dataclass(frozen=True)
class ReadyMadeFont:
    """A ready-made font as add_font_file adds it to a folder: its name, its
    block, turned to the folder's rotation if it was stored at another,
    whether it was, and the warning, if any."""
    name: str
    block: bytes
    turned: bool
    warning: str = None


def add_font_file(source_folder: Path, font_file: Path, name: str = None) -> tuple:
    """Adds a ready-made font, a .zi file such as the Editor's font generator
    writes, to a source folder, as ready_made_font says: as fonts/<name>.zi,
    listed in app.toml after the folder's fonts. Returns (its name, the
    warning or None). Raises NxwrightError, before writing anything, where
    ready_made_font does."""
    source_folder = Path(source_folder)
    app, path, font = _ready_made(source_folder, Path(font_file), name)
    _add_resource(source_folder, app, "fonts", font.name, [(path, font.block)])
    return font.name, font.warning


def ready_made_font(source_folder: Path, font_file: Path, name: str = None) -> ReadyMadeFont:
    """Returns the ReadyMadeFont add_font_file would add to a source folder,
    writing nothing. A font at another rotation than the folder's is turned
    to it; one at the folder's rotation is copied as it is. Its name is
    `name`, or else ready_made_font_name's. The name stored in the font
    stays, as in a font renamed in a folder.

    The font may be in the folder's encoding, in ascii in an iso-8859-1
    folder, or in iso-8859-1 in a utf-8 folder or one whose keyboards take an
    iso-8859-1 font (encodings_taken). A font in iso-8859-1 in another
    folder comes with a warning that text beyond ascii shows garbled.

    Raises NxwrightError for a folder without screen settings, a file that
    is not a font, a damaged font of a kind nxwright decodes
    (zi_font.decodes), a font in another encoding, one at another rotation
    that nxwright cannot decode to turn it, a name the folder has, or a file
    already at the font's place.
    """
    return _ready_made(Path(source_folder), Path(font_file), name)[2]


def ready_made_font_name(block: bytes, font_file: Path) -> str:
    """Returns the name add_font_file gives a ready-made font when given
    none: the one stored in it, as extract names a new font, or else the
    file's."""
    return font_header_name(block) or name_part(Path(font_file).stem) or "font"


def _ready_made(source_folder: Path, font_file: Path, name: str) -> tuple:
    """Returns (the folder's app.toml settings, the font's path, the
    ReadyMadeFont) of a font file to add to a folder. Raises NxwrightError
    as ready_made_font says."""
    app = parse_app(read_text(source_folder / "app.toml"))
    settings = font_settings(settings_from_keys(app))
    block = read_bytes(font_file)
    try:
        facts = font_facts(block)
        # A font of a kind nxwright reads is read whole, so that a damaged one
        # is not copied in; of any other kind, only the header can be checked.
        if decodes(block):
            for character in decode_font(block).characters.values():
                character.coverages()
    except NxwrightError as error:
        raise NxwrightError("%s is not a font: %s" % (font_file, error)) from None
    accepted = encodings_taken(settings.encoding)
    if facts.encoding not in accepted:
        raise NxwrightError("the font is in %s, and a folder in %s takes fonts in %s"
                            % (facts.encoding, settings.encoding, " or ".join(accepted)))
    turned = facts.rotation != settings.rotation
    if turned:
        try:
            block = turned_font(block, settings.rotation)
        except NxwrightError as error:
            raise NxwrightError("the font is stored at rotation %d, where the folder's is %d, "
                                "and nxwright cannot turn it: %s"
                                % (facts.rotation, settings.rotation, error)) from None
    name = name or ready_made_font_name(block, font_file)
    path = _new_resource_paths(source_folder, app, "fonts", name)[0]
    warning = None
    if facts.encoding == "iso-8859-1" != settings.encoding:
        warning = ("the font %s is in iso-8859-1, not in the folder's %s: text in characters "
                   "beyond ascii shows garbled in it" % (name, settings.encoding))
    return app, path, ReadyMadeFont(name, block, turned, warning)


def folder_fonts(source_folder: Path) -> tuple:
    """Returns (the names of a source folder's fonts, in ID order, its screen
    settings or None), as app.toml gives them on disk. Raises NxwrightError
    for an app.toml that does not read."""
    app = parse_app(read_text(Path(source_folder) / "app.toml"))
    return list(app["fonts"]), settings_from_keys(app)


def encodings_taken(encoding: str) -> list:
    """Returns the encodings of the fonts a folder in `encoding` takes: its
    own; ascii in iso-8859-1, since the Editor itself adds its stock
    keyboard's ascii fonts to such a project; and iso-8859-1 where
    nxwright's keyboards took one before: in utf-8, in the two-byte
    encodings, and in the one-byte encodings Noto Sans lacks a character of.
    The Editor accepts such a font (docs/format.md)."""
    taken = [encoding]
    if encoding == "iso-8859-1":
        taken.append("ascii")
    if encoding == UTF8 or encoding in GRID_ENCODINGS or not noto_sans_covers(encoding):
        # Before nxwright wrote utf-8 fonts of chosen characters, two-byte
        # fonts, and one-byte fonts with a gap, its keyboards took an
        # iso-8859-1 font in such a folder, as folders made then still hold.
        taken.append("iso-8859-1")
    return taken


def font_settings(settings):
    """Returns a folder's screen settings, `settings`, as app.toml gives them
    (folder_fonts), which its fonts need for their rotation and encoding.
    Raises NxwrightError when `settings` is None, as app.toml gives none."""
    if settings is None:
        raise NxwrightError("app.toml gives no screen settings, so the rotation and encoding "
                            "of the folder's fonts are not known")
    return settings


def _media_rotation(app: dict) -> int:
    """Returns the rotation a folder's animations and videos are made for:
    its screen's, or 0, upright, when app.toml gives no screen settings.
    Raises NxwrightError for screen settings that are wrong."""
    settings = settings_from_keys(app)
    return 0 if settings is None else settings.rotation


def add_animation(source_folder: Path, pictures: list, duration: int = None,
                  name: str = None) -> str:
    """Makes an animation of `pictures`, a frame of each, in order, each
    lasting `duration` ms, FRAME_DURATION when it is None, as GmovMaker and
    the Editor's Gmov panel would. Writes its two files,
    animations/<name>.gmov and <name>.screen.gmov
    (media_files.animation_files), and lists it in app.toml after the
    folder's animations. Its name is `name`, or else the first picture's.
    The screen's form is made for the folder's rotation. Returns the name.

    `pictures` may instead be one file of GmovMaker's (.gmov), as the Gmov
    panel takes it: it is kept as it is, and the screen's form is made from
    its frames (media_files.gmovmaker_frames), whose durations are their own.

    The pictures may be of any kind Pillow reads, the first frame of a GIF
    taken. Raises NxwrightError, before writing anything, for a picture it
    cannot read, pictures of two sizes, a GmovMaker file with another file
    or a duration, one it cannot read, a name the folder has or may not
    have, or a file already where one would go."""
    source_folder = Path(source_folder)
    app = parse_app(read_text(source_folder / "app.toml"))
    rotation = _media_rotation(app)
    if not pictures:
        raise NxwrightError("an animation needs a picture")
    gmovmaker = any(Path(picture).suffix.lower() == ".gmov" for picture in pictures)
    if gmovmaker and len(pictures) > 1:
        raise NxwrightError("a GmovMaker file is given alone, without other files")
    if gmovmaker and duration is not None:
        raise NxwrightError("a GmovMaker file takes no duration: its frames have their own "
                            "durations")
    if gmovmaker:
        # Read first, so that a screen's form given by mistake is named so.
        path = Path(pictures[0])
        data = read_bytes(path)
        try:
            frames = gmovmaker_frames(data)
        except NxwrightError as error:
            raise NxwrightError("%s: %s" % (path.name, error)) from None
    name = name or name_part(Path(pictures[0]).stem) or "animation"
    paths = _new_resource_paths(source_folder, app, "animations", name)
    if gmovmaker:
        files = (data, animation_files(frames, rotation)[1])
    else:
        frames = [(_picture_at(Path(picture)), FRAME_DURATION if duration is None else duration)
                  for picture in pictures]
        files = animation_files(frames, rotation)
    _add_resource(source_folder, app, "animations", name, zip(paths, files))
    return name


def write_card_pictures(pictures: list, output: Path, quality: str = "very-high",
                        rotation: int = 0) -> list:
    """Writes, for each of `pictures`, the picture file an external picture
    shows from an SD card, as PictureBox writes it: <output>/<the picture's
    name>.xi (media_files.card_picture_file), at PictureBox's `quality`
    (CARD_PICTURE_QUALITIES), for a screen turned `rotation` degrees. The
    folder is made when it is missing. Returns the files' paths.

    The pictures may be of any kind Pillow reads, as add_animation's. Raises
    NxwrightError, before writing anything, for a quality or rotation there
    is not, a picture it cannot read, two pictures of one name, or a file
    already where one would go."""
    output = Path(output)
    if quality not in CARD_PICTURE_QUALITIES:
        raise NxwrightError("a quality is one of %s" % ", ".join(CARD_PICTURE_QUALITIES))
    if not pictures:
        raise NxwrightError("there is no picture to write")
    paths = [output / (Path(picture).stem + ".xi") for picture in pictures]
    seen = {}
    for picture, path in zip(pictures, paths):
        # Windows' file names ignore letter case.
        if path.name.lower() in seen:
            raise NxwrightError("%s and %s would both be written to %s"
                                % (seen[path.name.lower()], Path(picture).name, path.name))
        seen[path.name.lower()] = Path(picture).name
        if path.exists():
            raise NxwrightError("%s is already there" % path)
    contents = [card_picture_file(_picture_at(Path(picture)), CARD_PICTURE_QUALITIES[quality],
                                  rotation) for picture in pictures]
    output.mkdir(parents=True, exist_ok=True)
    for path, content in zip(paths, contents):
        path.write_bytes(content)
    return paths


def add_video(source_folder: Path, sources: list, rate: int = VIDEO_RATE, size: tuple = None,
              start: float = None, length: float = None, name: str = None,
              ffmpeg: Path = None) -> str:
    """Makes a video, as VideoBox does, `rate` frames a second, for the
    folder's rotation, and writes it to videos/<name>.video
    (media_files.video_file), listed in app.toml after the folder's videos.
    Its name is `name`, or else its first source's. Returns the name.

    `sources` is either one video file, which ffmpeg, the program `ffmpeg`
    names or the PATH finds, cuts into frames, from `start` seconds in, for
    `length` seconds, scaled to `size`, (width, height), as VideoBox has
    ffmpeg do; or still pictures of any kind Pillow reads, a frame of each,
    in order, taken as they are. Raises NxwrightError, before writing
    anything, for a rate the file cannot keep, a source that cannot be
    read, frames of two sizes, a name the folder has or may not have, or a
    file already where the video would go."""
    source_folder, sources = Path(source_folder), [Path(source) for source in sources]
    app = parse_app(read_text(source_folder / "app.toml"))
    rotation = _media_rotation(app)
    check_video_rate(rate)
    if not sources:
        raise NxwrightError("a video needs a video file or pictures")
    name = name or name_part(sources[0].stem) or "video"
    paths = _new_resource_paths(source_folder, app, "videos", name)
    with tempfile.TemporaryDirectory() as cut:
        # A still picture is a frame. Any other file, such as an animated GIF
        # or a video, is a video file for ffmpeg to cut.
        sizes = [still_picture_size(source) for source in sources]
        if None not in sizes:
            if (size, start, length) != (None, None, None):
                raise NxwrightError("a size, a start, and a length cut a video file; pictures "
                                    "are taken as they are")
            frames = sources
        elif len(sources) == 1:
            found = _needed_ffmpeg(ffmpeg, "%s is no still picture nxwright reads: nxwright cuts "
                                           "a video file into frames through ffmpeg"
                                   % sources[0].name)
            frames = video_as_pngs(found, sources[0], Path(cut), rate, size, start, length)
            sizes = [picture_size(frame) for frame in frames]
        else:
            raise NxwrightError("%s is not a still picture; a video is made of one video file, "
                                "or of still pictures" % sources[sizes.index(None)].name)
        for frame, frame_size in zip(frames, sizes):
            if frame_size != sizes[0]:
                raise NxwrightError("%s is %d by %d, where a video's frames must all be %d by %d, "
                                    "as its first" % (frame.name, *frame_size, *sizes[0]))
        pictures = [video_frame(_picture_at(frame), rotation) for frame in frames]
    _add_resource(source_folder, app, "videos", name,
                  zip(paths, [video_file(*sizes[0], rate, pictures, rotation)]))
    return name


def add_sound(source_folder: Path, sound: Path, name: str = None, rate: int = None,
              mono: bool = False, ffmpeg: Path = None) -> str:
    """Adds a sound: written to sounds/<name>.wav in the form the Editor
    writes, its samples as they are (media_files.sound_file), and listed in
    app.toml after the folder's sounds. Its name is `name`, or else the
    file's. Returns the name.

    A WAV file of PCM samples of 8 or 16 bits, mono or stereo, is taken as
    it is. Any other sound file, and any to be made `rate` samples a second
    or `mono`, goes through ffmpeg, the program `ffmpeg` names or the PATH
    finds, which makes its samples 16-bit. Raises NxwrightError, before
    writing anything, for a rate outside 8,000 to 48,000, the rates the
    Editor was seen to take, a file neither nxwright nor ffmpeg reads, a
    name the folder has or may not have, or a file already where the sound
    would go."""
    source_folder, sound = Path(source_folder), Path(sound)
    app = parse_app(read_text(source_folder / "app.toml"))
    if rate is not None and rate not in SOUND_RATES:
        raise NxwrightError("a sound's rate must be from 8,000 to 48,000 samples a second")
    name = name or name_part(sound.stem) or "sound"
    paths = _new_resource_paths(source_folder, app, "sounds", name)
    # hmic holds the name of the sound's file in the folder, without its
    # extension, as the Editor's holds that of the file it was given.
    stored = name.split("/")[-1]
    data = read_bytes(sound)
    if rate is None and not mono:
        try:
            content = sound_file(data, stored)
        except NxwrightError as error:
            content, why = None, "%s: %s: nxwright converts others through ffmpeg" % (
                sound.name, error)
    else:
        content, why = None, "converting %s needs ffmpeg" % sound.name
    if content is None:
        found = _needed_ffmpeg(ffmpeg, why)
        with tempfile.TemporaryDirectory() as converted:
            content = sound_file(sound_as_wav(found, sound, Path(converted), rate, mono), stored)
    _add_resource(source_folder, app, "sounds", name, zip(paths, [content]))
    return name


def _new_resource_paths(source_folder: Path, app: dict, listed: str, name: str) -> list:
    """Returns the paths of the files of a new font, animation, video, or
    sound named `name`, of the kind app.toml lists in `listed`. Raises
    NxwrightError for a name the folder has or may not have, or a file
    already at one of the paths."""
    taken = {known.lower(): known for known in app[listed]}
    if name.lower() in taken:
        raise NxwrightError("the folder has %s %s named %s" % (
            "an" if listed == "animations" else "a", NOUNS[KIND_OF_LIST[listed]],
            taken[name.lower()]))
    check_names(app[listed] + [name], listed)
    paths = [source_folder / listed / (name + suffix) for suffix in RESOURCE_FILES[listed]]
    for path in paths:
        if path.exists():
            raise NxwrightError("%s is already there, though app.toml does not list it" % path)
    return paths


def _add_resource(source_folder: Path, app: dict, listed: str, name: str, files):
    """Writes the files (path, content) of a new font, animation, video, or
    sound named `name`, and lists it in app.toml, in `listed`, after the
    others."""
    for path, content in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (source_folder / "app.toml").write_text(app_text(dict(app, **{listed: app[listed] + [name]})),
                                            encoding="utf-8", newline="\n")


def _picture_at(path: Path):
    """Returns the picture file at `path` as an RGBA image
    (pictures.read_picture): of any kind Pillow reads, the first frame of a
    GIF. Raises NxwrightError, naming the file, for one it cannot read."""
    data = read_bytes(path)
    try:
        return read_picture(data)
    except NxwrightError as error:
        raise NxwrightError("%s: %s" % (path.name, error)) from None


def _needed_ffmpeg(given: Path, why: str) -> str:
    """Returns the ffmpeg program find_ffmpeg finds, or raises NxwrightError,
    saying `why` it is needed, when there is none."""
    found = find_ffmpeg(given)
    if found is None:
        raise NxwrightError("%s, which is not on the PATH; install it, or name it with --ffmpeg"
                            % why)
    return found
