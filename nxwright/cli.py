"""The nxwright command, with one subcommand per tool.

Installed, it runs as `nxwright <subcommand>`; from a checkout, as
`python run.py <subcommand>`, or `python -m nxwright <subcommand>`.
`nxwright <subcommand> --help` describes each subcommand.

Exit codes: 0 when the subcommand succeeded, 1 when it failed (the message
says why), and 2 when its arguments are wrong.
"""
import argparse
import json
from pathlib import Path
import sys
import unittest

from nxwright import NxwrightError, installed_version
from nxwright.debug_adapter import adapter as debug_adapter
from nxwright.language_server.server import serve
from nxwright.mcp_server import server as mcp_server
from nxwright.project.device_settings import (DEFAULT_ENCODING, ENCODINGS, DeviceSettings,
                                              password_hash)
from nxwright.project.dumper import ProjectDumper
from nxwright.project.media_files import CARD_PICTURE_QUALITIES
from nxwright.project.page_file import write_page_file
from nxwright.project.project_writer import ProjectWriter
from nxwright.project.replacing import is_page_file, is_project_file
from nxwright.project.screen_copy import ROTATIONS
from nxwright.project.screen_models import MODELS, model_named
from nxwright.project.zi_font import GRID_ENCODINGS, font_facts
from nxwright.source.device_change import change_device
from nxwright.source.folder_check import check_folder
from nxwright.source.formatting import format_folder
from nxwright.source.lint import ERROR
from nxwright.source.project_files import build, extract, write_defaults
from nxwright.source.keyboards import KEYBOARD_PAGES
from nxwright.source.resource_removal import KINDS, remove_resource
from nxwright.source.source_folder import (LANGUAGES, NXLANG, add_page, folder_byte_reader,
                                           folder_reader, import_dump, new_source_folder,
                                           switch_to_nxlang)
from nxwright.source.resource_adding import (VIDEO_RATE, add_animation, add_font, add_font_file,
                                             add_pictures, add_sound, add_video,
                                             write_card_pictures)
from nxwright.source.keyboard_adding import add_keyboard
from nxwright.source.upgrade import upgrade
from nxwright.testing.reports import RecordingResult, results, test_ids


def _run_build(arguments) -> str:
    if not arguments.overwrite:
        refuse_unless_replacing(arguments.output, _terminal_asker())
    memory = build(arguments.source_folder, arguments.output)
    if memory.warning is not None:
        print("nxwright build: warning: %s" % memory.warning, file=sys.stderr)
    # Each page's memory, as the Editor's compile lists it. Counted without
    # what the table did not measure, it is a lower bound.
    at_least = "at least " if memory.unmeasured is not None else ""
    for page, total in memory.totals.items():
        print("%s: %s%d of %d bytes" % (page, at_least, total, memory.memory))
    return "Wrote %s" % arguments.output


def refuse_unless_replacing(output: Path, ask, kind: str = "project file",
                            made: str = "built"):
    """Raises NxwrightError unless a command may write `output`: it is no
    `kind` of file ("project file" or "page file", which _REPLACEABLE tells
    apart), or `ask(question)` answers that it may be replaced. Otherwise
    nothing was `made`, as "built" or "written". Without `ask` (nobody at
    the terminal), or once its input ends, it is refused, naming
    --overwrite. A file of another kind is left to the command, which
    refuses it."""
    if not _REPLACEABLE[kind](output):
        return
    while ask is not None:
        try:
            answer = ask("Replace the %s %s? [y/N]: " % (kind, output)).strip().lower()
        except EOFError:
            break
        if answer in ("y", "yes"):
            return
        if answer in ("", "n", "no"):
            raise NxwrightError("%s was not replaced; nothing was %s" % (output, made))
        print("Not one of the choices: y, n")
    raise NxwrightError("%s exists; pass --overwrite to replace it" % output)


# The kinds of file a command replaces, and how each is told from another file.
_REPLACEABLE = {"project file": is_project_file, "page file": is_page_file}


def _terminal_asker():
    """Returns `input`, to ask the user, or None when the command's input or
    output is not a terminal. input writes its question to the output, so
    with the output sent to a file, the question would not be seen."""
    return input if sys.stdin.isatty() and sys.stdout.isatty() else None


def _run_check(arguments) -> str:
    folder = arguments.source_folder
    if not (folder / "app.toml").is_file():
        raise NxwrightError("%s has no app.toml" % folder)
    result = check_folder(folder_reader(folder), lambda path: (folder / path).is_file(),
                          read_bytes=folder_byte_reader(folder))
    findings = result.findings()
    for finding in findings:
        print("%s: %s" % (finding.place, finding.severity) if finding.place
              else finding.severity, finding.message, sep=": ")
    errors = sum(finding.severity == ERROR for finding in findings)
    summary = "%d errors, %d warnings" % (errors, len(findings) - errors)
    if errors:
        raise NxwrightError(summary)
    return summary


def _run_format(arguments) -> str:
    folder = arguments.source_folder
    if not (folder / "app.toml").is_file():
        raise NxwrightError("%s has no app.toml" % folder)
    changed = format_folder(folder_reader(folder))
    if arguments.check:
        for path in sorted(changed):
            print(path)
        if changed:
            raise NxwrightError("%d files would change" % len(changed))
        return "no file would change"
    for path, text in changed.items():
        (folder / path).write_text(text, encoding="utf-8", newline="\n")
    return "\n".join("Formatted %s" % path for path in sorted(changed)) or "no file changed"


def _run_new(arguments) -> str:
    ask = _terminal_asker()
    settings, language = new_folder_settings(arguments, ask)
    name = new_folder_name(arguments, ask, arguments.source_folder)
    warning = new_source_folder(arguments.source_folder, settings, language, name)
    if warning:
        print("nxwright new: warning: %s" % warning, file=sys.stderr)
    return "Started %s: %s at %d degrees, %s, in %s" % (
        arguments.source_folder, settings.model.name, settings.rotation, settings.encoding,
        language)


def new_folder_settings(arguments, ask) -> tuple:
    """Returns (DeviceSettings, language) for nxwright new, from the options,
    and from `ask(question)` for those left out. Without `ask` (nobody at the
    terminal), or once its input ends, the rotation, encoding, and language
    left out take their defaults, and a missing screen model is refused."""
    screen = arguments.screen or _asked(
        ask, "Screen model, such as NX8048P050: ", None, [model.name for model in MODELS])
    if screen is None:
        raise NxwrightError("no screen model: give one with --screen")
    rotation = arguments.rotation if arguments.rotation is not None else int(_asked(
        ask, "Rotation in degrees [0]: ", "0", [str(degrees) for degrees in ROTATIONS]))
    encoding = arguments.encoding or _asked(
        ask, "Character encoding [%s]: " % DEFAULT_ENCODING, DEFAULT_ENCODING,
        list(ENCODINGS.values()))
    language = arguments.language or _asked(
        ask, "Language, nxlang, or nextion for strict Nextion syntax [nxlang]: ", NXLANG,
        list(LANGUAGES))
    return DeviceSettings(model_named(screen), rotation, encoding), language


def new_folder_name(arguments, ask, source_folder: Path) -> str:
    """Returns the app's name for nxwright new: --name, or the answer to
    `ask(question)`, the folder's name by default, as without `ask`."""
    if arguments.name is not None:
        return arguments.name
    default = Path(source_folder).resolve().name
    if ask is not None:
        try:
            return ask("App name [%s]: " % default).strip() or default
        except EOFError:
            pass
    return default


def _asked(ask, question: str, default, choices: list):
    """Returns the answer to `question`, asked again until it is one of
    `choices`. An empty answer is `default`, when there is one. Without
    `ask`, or once its input ends, returns `default`."""
    while ask is not None:
        try:
            answer = ask(question).strip() or default
        except EOFError:
            break
        if answer in choices:
            return answer
        print("Not one of the choices: %s" % ", ".join(choices))
    return default


def _run_font(arguments) -> str:
    # A font file is added as it is: it has its height and smoothing already.
    if arguments.font_file.suffix.lower() == ".zi":
        if (arguments.height is not None or arguments.no_smoothing
                or arguments.characters is not None or arguments.full_table):
            raise NxwrightError("a font file (.zi) is added as it is; give no height, no "
                                "--no-smoothing, no --characters, and no --full-table")
        name, warning = add_font_file(arguments.source_folder, arguments.font_file,
                                      arguments.name)
        if warning:
            print("nxwright font: warning: %s" % warning, file=sys.stderr)
        return "Added the font %s to %s" % (name, arguments.source_folder)
    if arguments.height is None:
        raise NxwrightError("a font drawn from a typeface file needs a height")
    name, warning = add_font(arguments.source_folder, arguments.font_file, arguments.height,
                             arguments.name, not arguments.no_smoothing, arguments.characters,
                             arguments.full_table)
    if warning:
        print("nxwright font: warning: %s" % warning, file=sys.stderr)
    added = "Added the font %s to %s" % (name, arguments.source_folder)
    if arguments.full_table:
        # Its table has an entry for every code point to U+FFFF.
        added += (". A font in utf-8 of a full table is at least 655 KB, whatever characters "
                  "it contains.")
    return added


def _run_animation(arguments) -> str:
    name = add_animation(arguments.source_folder, arguments.pictures, arguments.duration,
                         arguments.name)
    return "Added the animation %s to %s" % (name, arguments.source_folder)


def _run_video(arguments) -> str:
    name = add_video(arguments.source_folder, arguments.sources, arguments.rate, arguments.size,
                     arguments.start, arguments.length, arguments.name, arguments.ffmpeg)
    return "Added the video %s to %s" % (name, arguments.source_folder)


def _run_sd_picture(arguments) -> str:
    paths = write_card_pictures(arguments.pictures, arguments.output, arguments.quality,
                                arguments.rotation)
    return "Wrote %s" % ", ".join(str(path) for path in paths)


def _run_sound(arguments) -> str:
    name = add_sound(arguments.source_folder, arguments.sound, arguments.name, arguments.rate,
                     arguments.mono, arguments.ffmpeg)
    return "Added the sound %s to %s" % (name, arguments.source_folder)


def _run_keyboard(arguments) -> str:
    page, font, warning = add_keyboard(arguments.source_folder, arguments.kind,
                                       arguments.typeface, arguments.font)
    if warning:
        print("nxwright keyboard: warning: %s" % warning, file=sys.stderr)
    # A font in a two-byte encoding holds every character of its grid, which
    # makes it large, so its size is said.
    block = (Path(arguments.source_folder) / "fonts" / (font + ".zi")).read_bytes()
    if font_facts(block).encoding in GRID_ENCODINGS:
        font = "%s (%d KB)" % (font, round(len(block) / 1024))
    return "Added the keyboard page %s, with the font %s, to %s" % (page, font,
                                                                     arguments.source_folder)


def _run_picture(arguments) -> str:
    names = add_pictures(arguments.source_folder, arguments.pictures)
    return "Added the picture%s %s to %s" % ("s" if len(names) > 1 else "", ", ".join(names),
                                             arguments.source_folder)


def _run_remove(arguments) -> str:
    removed, left = remove_resource(arguments.source_folder, arguments.kind, arguments.name)
    lines = ["Removed the %s %s from %s: %s" % (arguments.kind, arguments.name,
                                               arguments.source_folder,
                                               ", ".join(removed) or "it had no files")]
    lines += ["warning: %s could not be deleted, and stays, though no list names it: %s"
              % tuple(problem.split(": ", 1)) for problem in left]
    return "\n".join(lines)


def _run_device(arguments) -> str:
    # Each step as it starts, at once: a video can take a while.
    change = change_device(arguments.source_folder, arguments.screen, arguments.rotation,
                           arguments.encoding, told=lambda line: print(line, flush=True))
    if not change.written:
        return "%s already has these settings; nothing written" % arguments.source_folder
    lines = ["Wrote %s" % path for path in change.written] + change.notes
    if change.refusals:
        lines += ["The build now refuses:"] + ["  " + refusal for refusal in change.refusals]
    return "\n".join(lines)


def _run_new_page(arguments) -> str:
    page = add_page(arguments.source_folder, arguments.name)
    return "Added the page %s to %s" % (page, arguments.source_folder)


def _run_extract(arguments) -> str:
    for warning in extract(arguments.project, arguments.source_folder):
        print("nxwright extract: warning: %s" % warning, file=sys.stderr)
    return "Extracted %s into %s" % (arguments.project, arguments.source_folder)


def _run_dump(arguments) -> str:
    ProjectDumper(arguments.project, arguments.output_folder).dump()
    return "Wrote %s" % arguments.output_folder


def _run_import(arguments) -> str:
    for warning in import_dump(arguments.dump_folder, arguments.source_folder):
        print("nxwright import: warning: %s" % warning, file=sys.stderr)
    return "Wrote %s" % arguments.source_folder


def _run_write(arguments) -> str:
    if not arguments.overwrite:
        refuse_unless_replacing(arguments.output, _terminal_asker(), "project file", "written")
    changed = ProjectWriter(arguments.project, arguments.dump_folder, arguments.output).write()
    if not changed:
        return "Nothing in the dump differs from the project; nothing written."
    return "\n".join(changed)


def _run_page(arguments) -> str:
    if not arguments.overwrite:
        refuse_unless_replacing(arguments.output, _terminal_asker(), "page file", "written")
    write_page_file(arguments.dump_folder, arguments.page_id, arguments.output)
    return "Wrote %s" % arguments.output


def _run_password_hash(arguments) -> str:
    return password_hash(arguments.password).hex()


def _run_defaults(arguments) -> str:
    write_defaults(arguments.sample, arguments.output)
    return "Wrote %s" % arguments.output


def _run_language(arguments) -> str:
    switch_to_nxlang(arguments.source_folder)
    return "%s now uses the nxwright language" % arguments.source_folder


def _run_upgrade(arguments) -> str:
    reached = upgrade(arguments.source_folder)
    if not reached:
        return "%s is already in the current source format" % arguments.source_folder
    return "%s is now in source format %d" % (arguments.source_folder, reached[-1])


def _run_test(arguments) -> str:
    folder = arguments.folder.resolve()
    if not folder.is_dir():
        raise NxwrightError("%s is not a folder" % arguments.folder)
    loader = unittest.TestLoader()
    if arguments.k:
        # As with unittest's own -k, a pattern without "*" matches anywhere in the name.
        loader.testNamePatterns = [pattern if "*" in pattern else "*%s*" % pattern
                                   for pattern in arguments.k]
    # The folder is the top of the import path. So its tests import its other
    # modules by name alone, such as `from screen import SCREEN`, with no package.
    suite = loader.discover(str(folder), top_level_dir=str(folder))
    if suite.countTestCases() == 0:
        # Without the patterns, the folder may have tests none of them matches.
        if arguments.k and unittest.TestLoader().discover(
                str(folder), top_level_dir=str(folder)).countTestCases():
            raise NxwrightError("no test of %s matches %s"
                                % (arguments.folder, " or ".join(arguments.k)))
        raise NxwrightError("%s has no tests" % arguments.folder)
    if arguments.list:
        return "\n".join(test_ids(suite))
    result = unittest.TextTestRunner(resultclass=RecordingResult).run(suite)
    if arguments.report:
        arguments.report.write_text(json.dumps(results(result, folder), indent=1),
                                    encoding="utf-8")
    if not result.wasSuccessful():
        raise NxwrightError("%d failed, %d stopped with an error"
                            % (len(result.failures), len(result.errors)))
    return ""


def _run_debug_adapter(arguments) -> str:
    debug_adapter.serve(sys.stdin.buffer, sys.stdout.buffer)
    return ""


def _run_mcp(arguments) -> str:
    mcp_server.serve(sys.stdin.buffer, sys.stdout.buffer)
    return ""


def _run_lsp(arguments) -> str:
    if serve(sys.stdin.buffer, sys.stdout.buffer) != 0:
        raise NxwrightError("the editor ended the session without a shutdown request")
    return ""


def _page_id(text: str) -> int:
    """Returns the page ID typed on the command line. Only decimal digits are
    accepted, so "-1" or "+1" is refused rather than read as a number."""
    if not (text.isascii() and text.isdigit()):
        raise argparse.ArgumentTypeError("not a page ID: %r" % text)
    return int(text)


def _size(text: str) -> tuple:
    """A width and a height, as "320,240"."""
    parts = text.split(",")
    if len(parts) != 2 or not all(part.isascii() and part.isdigit() and int(part) > 0
                                  for part in parts):
        raise argparse.ArgumentTypeError("not a width and a height, as 320,240: %r" % text)
    return int(parts[0]), int(parts[1])


# Each subcommand: its name, the function running it (which returns the message
# to print, or ""), a one-line summary, a fuller description, and its arguments
# as (name, options for argparse's add_argument).
_SUBCOMMANDS = [
    ("build", _run_build, "build a project file from a source folder",
     "Writes a new project file from the source folder alone: its pages, code, pictures, "
     "fonts, and device settings. An existing project file at the output is replaced, once "
     "the new one is written in full. The command asks first, unless --overwrite is given, "
     "and refuses when there is no terminal to ask at. Any other file there is refused.",
     [("source_folder", {"type": Path, "help": "the source folder"}),
      ("output", {"type": Path, "help": "the project file (.HMI) to write"}),
      ("--overwrite", {"action": "store_true",
                       "help": "replace an existing project file at the output without "
                               "asking"})]),
    ("check", _run_check, "check a source folder as the build does, writing nothing",
     "Prints each error the build would stop at, the first of each page, and warnings about "
     "likely mistakes the build accepts, as `<file> line <n>: error: <message>`. Exits with 1 "
     "when there is an error.",
     [("source_folder", {"type": Path, "help": "the source folder"})]),
    ("format", _run_format, "lay a source folder's code out in nxwright's one style",
     "Formats every .nx file of the folder, as docs/commands.md describes. A file is "
     "formatted only if the pages using it, or the macros of macros.nx, build to the same code in "
     "strict Nextion syntax as before, apart from spaces at the start and end of lines; nothing "
     "is written unless every file passes, and nothing when the folder does not build.",
     [("source_folder", {"type": Path, "help": "the source folder"}),
      ("--check", {"action": "store_true",
                   "help": "write nothing; list the files that would change, and exit with 1 "
                           "when there is one"})]),
    ("new", _run_new, "start a source folder for a new project",
     "Writes a source folder with one blank page the size of the screen, and one font, Noto "
     "Sans at 24 pixels, so that a first text builds. "
     "It warns of the characters of the encoding Noto Sans lacks, which the font leaves out. "
     "It asks for the screen model, "
     "rotation, encoding, language, and app's name that "
     "the options leave out. Without a terminal to ask at, the defaults apply and --screen "
     "is required.",
     [("source_folder", {"type": Path, "help": "the folder to write; it must be new or empty"}),
      ("--screen", {"help": "the screen model, such as NX8048P050"}),
      ("--rotation", {"type": int, "choices": ROTATIONS, "help": "in degrees (default 0)"}),
      ("--encoding", {"help": "the character encoding (default iso-8859-1)"}),
      ("--language", {"choices": LANGUAGES, "help": "the code's language (default nxlang)"}),
      ("--name", {"help": "the app's name, as nxwright shows it (default: the folder's)"})]),
    ("font", _run_font,
     "add a font to a source folder, drawn from a typeface file or ready-made",
     "Draws the characters of the folder's encoding from a typeface file, turned to the folder's "
     "rotation, and adds the font after the folder's other fonts. Its name is the typeface's and "
     "the height, such as NotoSans20, unless --name gives one. In a utf-8 folder, it draws the "
     "characters --characters gives, U+0000 to U+00FF by default, and the space, in a table of "
     "them alone, as the Nextion Editor's generator writes its \"Specified character\"; "
     "--full-table writes one of every code point to U+FFFF instead, at least 655 KB, whatever it "
     "contains. Characters the file lacks are left out, and the command warns of them. In a "
     "two-byte encoding, such as gb2312 or big5, the font contains every character of the "
     "encoding, and one the file lacks is left empty. A file that has none of the characters, "
     "or a name the folder has, is refused, and nothing is written. A ready-made font file "
     "(.zi), such as the Nextion Editor's font generator writes, is added as it is, turned to the "
     "folder's rotation, "
     "and named as it names itself unless --name gives one. It may be in the folder's encoding, "
     "in ascii in an iso-8859-1 folder, or in iso-8859-1 in a folder whose encoding Noto Sans "
     "does not cover, such as utf-8, with a warning.",
     [("source_folder", {"type": Path, "help": "the source folder"}),
      ("font_file", {"type": Path,
                     "help": "the typeface file (.ttf, .otf, or .ttc) to draw from, or a "
                             "font file (.zi)"}),
      ("height", {"type": int, "nargs": "?",
                  "help": "in pixels, from 12 to 254; only for a typeface file"}),
      ("--name", {"help": "the font's name (default: the typeface's and the height, "
                          "or the one a font file stores)"}),
      ("--no-smoothing", {"action": "store_true",
                          "help": "make each pixel empty or full, as the Nextion Editor's "
                                  "generator does without anti-aliasing"}),
      ("--characters", {"help": "in a utf-8 folder, the characters to draw: code points in "
                                "hexadecimal and ranges of them, such as 20-7e,400-4ff "
                                "(default 0-ff)"}),
      ("--full-table", {"action": "store_true",
                        "help": "in a utf-8 folder, a table of every code point to U+FFFF, at "
                                "least 655 KB, where the font would contain its characters "
                                "alone"})]),
    ("animation", _run_animation, "make an animation of pictures, and add it to a source folder",
     "Makes an animation of the pictures given, a frame of each, in order, as GmovMaker and the "
     "Nextion Editor's Gmov panel would: GmovMaker's file, animations/<name>.gmov, and the form "
     "the screen shows, animations/<name>.screen.gmov, made for the folder's rotation. Given one "
     "file GmovMaker made (.gmov) instead, it keeps that file as it is, and makes the screen's "
     "form from its frames, which keep their durations. It is listed after the folder's other "
     "animations, named as the first file unless --name gives a name. The pictures must all be "
     "of one size: PNG, JPEG, BMP, GIF (its first frame), or another kind Pillow reads. A name "
     "the folder has, or a file that cannot be read, is refused, and nothing is written then.",
     [("source_folder", {"type": Path, "help": "the source folder"}),
      ("pictures", {"type": Path, "nargs": "+",
                    "help": "the pictures, one per frame, in order, or one GmovMaker file"}),
      ("--duration", {"type": int,
                      "help": "how long each frame shows, in milliseconds (default: 50, as "
                              "GmovMaker's); not with a GmovMaker file"}),
      ("--name", {"help": "the animation's name (default: the first picture's)"})]),
    ("video", _run_video, "make a video of a video file or of pictures, and add it to a "
                          "source folder",
     "Makes a video as VideoBox would, videos/<name>.video, for the folder's rotation, as "
     "VideoBox's display direction, listed after the folder's other videos, named as its "
     "first source unless --name gives a name. Given a video file, ffmpeg, found on the PATH "
     "or named by --ffmpeg, cuts it into frames, --rate a second, from --start for --length, "
     "scaled to --size. Given still pictures instead, of any kind Pillow reads, a frame of "
     "each, in order, all of one size, nxwright reads them itself, without ffmpeg. A name the "
     "folder has, or a source that cannot be read, is refused, and nothing is written then.",
     [("source_folder", {"type": Path, "help": "the source folder"}),
      ("sources", {"type": Path, "nargs": "+",
                   "help": "a video file, or still pictures, one per frame, in order"}),
      ("--rate", {"type": int, "default": VIDEO_RATE,
                  "help": "frames a second, from 1 to 255 (default: 12, as VideoBox's)"}),
      ("--size", {"type": _size, "help": "for a video file: the frames' width and height, "
                                         "as 320,240 (default: the video's own)"}),
      ("--start", {"type": float, "help": "for a video file: where to start, in seconds "
                                          "(default: its start)"}),
      ("--length", {"type": float, "help": "for a video file: how long to take, in seconds "
                                           "(default: to its end)"}),
      ("--name", {"help": "the video's name (default: the first source's)"}),
      ("--ffmpeg", {"type": Path, "help": "the ffmpeg program, for a video file "
                                          "(default: the one on the PATH)"})]),
    ("sound", _run_sound,
     "add a sound to a source folder",
     "Adds a sound, sounds/<name>.wav, in the form the Nextion Editor's Audio panel writes, which "
     "keeps the samples as they are, listed after the folder's other sounds, named as the "
     "file unless --name gives a name. A WAV file of PCM samples of 8 or 16 bits, mono or "
     "stereo, is taken as it is. Any other sound file, and any given --rate or --mono, goes "
     "through ffmpeg, found on the PATH or named by --ffmpeg, which makes 16-bit samples. A "
     "name the folder has, or a file that cannot be read, is refused, and nothing is "
     "written then.",
     [("source_folder", {"type": Path, "help": "the source folder"}),
      ("sound", {"type": Path, "help": "the sound file"}),
      ("--rate", {"type": int, "help": "samples a second to convert to, from 8000 to 48000 "
                                       "(default: the file's own)"}),
      ("--mono", {"action": "store_true", "help": "convert to one channel"}),
      ("--name", {"help": "the sound's name (default: the file's)"}),
      ("--ffmpeg", {"type": Path, "help": "the ffmpeg program, for converting "
                                          "(default: the one on the PATH)"})]),
    ("sd-picture", _run_sd_picture, "write the files external pictures show from an SD card",
     "Writes, for each picture given, the file an external picture shows from the screen's SD "
     "card, as PictureBox does: <output>/<the picture's name>.xi, a JPEG picture at --quality, "
     "for a screen turned --rotation degrees, with the picture's transparency: PNG, JPEG, BMP, "
     "GIF (its first frame), or another kind Pillow reads. A picture that cannot be read, two "
     "of one name, or a file already there, is refused, and nothing is written then.",
     [("pictures", {"type": Path, "nargs": "+", "help": "the pictures"}),
      ("--output", {"type": Path, "required": True,
                    "help": "the folder to write them in, made when it is missing"}),
      ("--quality", {"choices": list(CARD_PICTURE_QUALITIES), "default": "very-high",
                     "help": "PictureBox's quality (default: very-high, as PictureBox's)"}),
      ("--rotation", {"type": int, "choices": ROTATIONS, "default": 0,
                      "help": "the screen's rotation, in degrees (default: 0)"})]),
    ("keyboard", _run_keyboard, "add one of nxwright's keyboard pages to a source folder",
     "Adds the keyboard page a component's key opens, nxwright's own: the full keyboard "
     "(key 1), the numeric keypad (2), the speed dial (3), or the Chinese keyboard (4), laid "
     "out for the folder's screen at its rotation, with its font. The first three draw their "
     "font from Noto Sans, and a warning says which characters of the folder's encoding it "
     "lacks. The Chinese keyboard only works in a gb2312 folder, and needs a font with "
     "Chinese characters: give a typeface file with --typeface, or one of the folder's fonts "
     "with --font. A font in a two-byte encoding, such as the Chinese keyboard's, is large, "
     "and the command says how large. A folder that has that keyboard already, under any "
     "name, is refused, as is one with a page of the keyboard's name (keybdA, keybdB, keybdC, "
     "or keybdAP) that is another page: nothing is written then.",
     [("source_folder", {"type": Path, "help": "the source folder"}),
      ("kind", {"choices": list(KEYBOARD_PAGES),
                "help": "keyboard (key 1), keypad (2), speed-dial (3), or chinese-input (4)"}),
      ("--typeface", {"type": Path,
                      "help": "for chinese-input: a typeface file with Chinese characters "
                              "(.ttf, .otf, or .ttc), to draw its font from"}),
      ("--font", {"help": "for chinese-input: a gb2312 font of the folder's, by name"})]),
    ("picture", _run_picture, "add pictures to a source folder",
     "Copies picture files (.png, .jpg, .jpeg, .bmp, or .gif) into the folder's pictures/, "
     "and lists them after its other pictures, in the order given. Each is named after its "
     "file, kept to letters, digits, _ and -: \"My Icon.jpg\" gives MyIcon. A file nxwright "
     "cannot read as a picture, a name the folder has, in any case, or two files giving one "
     "name, are refused, and nothing is written then.",
     [("source_folder", {"type": Path, "help": "the source folder"}),
      ("pictures", {"type": Path, "nargs": "+", "help": "the picture files"})]),
    ("remove", _run_remove, "remove a resource from a source folder",
     "Removes a picture, font, animation, video, or sound: its files, and its name in "
     "app.toml. Removing one gives each later one of its kind an ID one lower, which a name "
     "follows but a number does not. So it is refused, and nothing written, while the folder "
     "uses it by name, or by a number from its ID to the last of its kind: in a page file, "
     "written or left to the defaults, or in code, written there or given by an nxlang "
     "constant, where its kind is taken. Each place is named. A number code computes, or keeps "
     "in a variable, is not seen. A folder whose checks find an error is refused too.",
     [("source_folder", {"type": Path, "help": "the source folder"}),
      ("kind", {"choices": list(KINDS), "help": "the kind of resource"}),
      ("name", {"help": "its name, as app.toml lists it"})]),
    ("device", _run_device, "change a source folder's screen model, rotation, or encoding",
     "Changes app.toml's screen model, rotation, or character encoding, as the Nextion Editor's "
     "Device window does, and what depends on them: each page takes the new screen's size, "
     "at its rotation; each font and video is turned to the new rotation, a video's frames "
     "coded again, which loses a little of each; and each font is converted to the new "
     "encoding, keeping the characters it has, the others named. Components keep their "
     "places and sizes, so it then lists what the build refuses, such as a component past "
     "a smaller screen's edge, or a text the new encoding cannot store. If a font can't be "
     "turned or converted, the command stops and writes nothing.",
     [("source_folder", {"type": Path, "help": "the source folder"}),
      ("--screen", {"help": "the new screen model, such as NX8048P050"}),
      ("--rotation", {"type": int, "choices": ROTATIONS, "help": "the new rotation, in degrees"}),
      ("--encoding", {"help": "the new character encoding, such as utf-8"})]),
    ("new-page", _run_new_page, "add a blank page to a source folder",
     "Adds a blank page the size of the screen, at the folder's rotation, as `new` starts page0, "
     "with an empty code file, and lists it last in app.toml. Without a name, it takes the first "
     "of page0, page1, and so on that the folder lacks. A name the folder has, in any case, or "
     "one the Nextion Editor refuses, is refused, and nothing is written then.",
     [("source_folder", {"type": Path, "help": "the source folder"}),
      ("name", {"nargs": "?", "help": "the page's name (default: the first free pageN)"})]),
    ("extract", _run_extract, "bring a project file into a source folder",
     "Use it to start from a project made in the Nextion Editor, or to bring back changes "
     "made there later. A new or empty folder gets a fresh source folder. An existing one "
     "keeps its code, names, and comfortable syntax wherever the project did not change "
     "them. The project file is only read.",
     [("project", {"type": Path, "help": "the project file (.HMI)"}),
      ("source_folder", {"type": Path, "help": "the source folder to update or create"})]),
    ("dump", _run_dump, "write a project file out as a dump folder of text and asset files",
     "The project file is only read. The output folder must not exist yet, or be empty. "
     "Nothing is ever deleted; clear an old dump yourself.",
     [("project", {"type": Path, "help": "the project file (.HMI)"}),
      ("output_folder", {"type": Path, "help": "the dump folder to write"})]),
    ("import", _run_import, "turn a dump folder into a source folder, or update one",
     "A new or empty source folder gets a fresh import. A source folder that already has "
     "an app.toml is updated, keeping its code wherever the dump has the same code. Any "
     "other folder is refused.",
     [("dump_folder", {"type": Path, "help": "a dump folder written by nxwright dump"}),
      ("source_folder", {"type": Path, "help": "the source folder to update or create"})]),
    ("write", _run_write, "write a project file from a project and an edited dump of it",
     "Pages, pictures, and fonts may have been edited, added, removed, or renumbered in the "
     "dump, and program.s edited. The rest of the project is copied unchanged. An existing "
     "project file at the output is replaced, once the new one is written in full and has "
     "passed its check: the project itself too, which is read first. The command asks first, "
     "unless --overwrite is given, and refuses when there is no terminal to ask at. Any other "
     "file there is refused.",
     [("project", {"type": Path, "help": "the project file (.HMI) the dump was made from"}),
      ("dump_folder", {"type": Path, "help": "the edited dump folder"}),
      ("output", {"type": Path, "help": "the project file to write"}),
      ("--overwrite", {"action": "store_true",
                       "help": "replace an existing project file at the output without "
                               "asking"})]),
    ("page", _run_page, "write one page of a dump as a page file the Nextion Editor imports",
     "The page file carries the fonts the page uses. Pictures are not carried, so the target "
     "project must have the same pictures with the same IDs. An existing page file at the "
     "output is replaced, once the new one is written in full. The command asks first, unless "
     "--overwrite is given, and refuses when there is no terminal to ask at. Any other file "
     "there is refused.",
     [("dump_folder", {"type": Path, "help": "a dump folder written by nxwright dump"}),
      ("page_id", {"type": _page_id, "help": "the page's ID in the Nextion Editor"}),
      ("output", {"type": Path, "help": "the page file (.page) to write"}),
      ("--overwrite", {"action": "store_true",
                       "help": "replace an existing page file at the output without asking"})]),
    ("password-hash", _run_password_hash, "print the password_hash of a project password",
     "Prints the value app.toml's password_hash takes for the password the screen asks for, "
     "as the Nextion Editor stores it, so that the password itself need not be kept in the source "
     "folder. The password must be ASCII: the Nextion Editor may refuse any other at load.",
     [("password", {"help": "the password"})]),
    ("defaults", _run_defaults, "write the component defaults file from a sample project",
     "The sample is a project made in the Nextion Editor with one newly added component of each "
     "type, left as the Nextion Editor created it. The output lists, per type, the attributes and "
     "events such a component has, which a source folder then leaves out. The output must not "
     "exist yet.",
     [("sample", {"type": Path, "help": "the sample project file (.HMI)"}),
      ("output", {"type": Path, "help": "the defaults file (.toml) to write"})]),
    ("language", _run_language, "switch a source folder to the nxwright language",
     "The nxwright language reads a+b*c as a+(b*c), where the Nextion Editor computes (a+b)*c. So "
     "the switch rewrites every line the two would read differently, with the parentheses that "
     "keep the Nextion Editor's meaning, then sets language = \"nxlang\" in app.toml. Set the "
     "language only this way, never by editing app.toml. Nothing is written when any code would "
     "not build to the same project.",
     [("source_folder", {"type": Path, "help": "the source folder"}),
      ("language", {"choices": [NXLANG], "help": "the language to switch to"})]),
    ("upgrade", _run_upgrade, "convert a source folder to the current format",
     "A source folder's app.toml names the format of its files. When nxwright changes that "
     "format, a folder in an older one is refused until it is converted. This converts it in "
     "place, step by step, without its project file. A folder already in the current format "
     "is left as it is.",
     [("source_folder", {"type": Path, "help": "the source folder"})]),
    ("test", _run_test, "run a folder of tests written with nxwright.testing",
     "Runs the unittest tests in the folder's files named test*.py. The folder is the top of "
     "the import path, so a test imports the folder's other modules by name alone.",
     [("folder", {"type": Path, "help": "the folder of tests"}),
      ("-k", {"action": "append", "metavar": "PATTERN",
              "help": "only run tests whose name contains PATTERN, or matches it in full "
                      "when it has a * wildcard (may be given again)"}),
      ("--list", {"action": "store_true",
                  "help": "print the ids of the tests it would run, and run none"}),
      ("--report", {"type": Path, "metavar": "FILE",
                    "help": "also write each test's result to FILE, as JSON"})]),
    ("debug-adapter", _run_debug_adapter, "serve the debugger of a test and its screen code",
     "Answers VS Code's debugger through the Debug Adapter Protocol on standard input and "
     "output: it runs a test with its Python and its screen code recorded, then steps through "
     "them, forward and backward. VS Code starts it, through nxwright's extension "
     "(editors/vscode).",
     []),
    ("mcp", _run_mcp, "serve the simulator to agents, through MCP",
     "Answers an agent, such as Claude Code, through the Model Context Protocol on standard "
     "input and output: its tools start the app of a source folder, press its screen, let "
     "its time pass, and show what the screen shows, as text and as a picture. The agent "
     "starts it itself (docs/mcp.md).",
     []),
    ("lsp", _run_lsp, "serve the language server, for code editors",
     "Answers a code editor's questions about source folders, such as where a name is "
     "defined, through the Language Server Protocol on standard input and output. Editors "
     "start it themselves, as nxwright's VS Code extension does (editors/vscode).",
     []),
]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nxwright", description="A toolchain for Nextion Editor projects (.HMI).")
    version = installed_version()
    parser.add_argument("--version", action="version",
                        version="nxwright %s" % version if version
                        else "nxwright (from source, not installed)")
    subcommands = parser.add_subparsers(dest="subcommand", metavar="<subcommand>",
                                        required=True)
    for name, run, summary, description, arguments in _SUBCOMMANDS:
        sub = subcommands.add_parser(name, help=summary, description=description)
        for argument, options in arguments:
            sub.add_argument(argument, **options)
        sub.set_defaults(run=run)
    return parser


def main(arguments: list = None) -> int:
    """Runs the subcommand `arguments` names (the command line by default);
    returns the exit code. Wrong arguments, and --help, exit through argparse's
    SystemExit instead."""
    parsed = _parser().parse_args(arguments)
    try:
        message = parsed.run(parsed)
    except (NxwrightError, OSError) as error:
        print("nxwright %s: %s" % (parsed.subcommand, error), file=sys.stderr)
        return 1
    if message:
        print(message)
    return 0
