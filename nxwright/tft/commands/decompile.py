"""turn a TFT file back into a source folder

  nxwright decompile <file.tft> <folder> [--continue-unconfirmed]

Writes the source folder of the TFT file into <folder>, which must not
exist yet or be empty. The command first writes the folder in a scratch
place. For a file made by the Nextion Editor 1.68.2, it then runs the
round trip check. The check compiles the folder again with the file's own
firmware, and compares the two files. It compares their pages,
components, int variables, macros, and code, their pictures' pixels,
their fonts' characters, and every other byte outside the names. When the
two give the same, the round trip confirms the folder, and the command
writes it.

The round trip may not confirm the folder: it finds differences, or it
cannot compile the folder again, as for a line of code nxwright has no rule
for. The folder is still what the command read, so the command warns, and
prints each difference, or why the folder could not be compiled again.
Then it prompts "Go on anyway? [y/N]" before writing anything:

  - y writes the folder, and exits with 0;
  - n, or an empty answer, writes nothing, and exits with 1;
  - with no terminal to prompt at, as in a script, or when the input
    ends at the prompt, it writes nothing, and exits with 3.

--continue-unconfirmed writes such a folder without prompting.

A picture is compared by its pixels, not its bytes: nxwright may compress
a picture into other bytes than the Nextion Editor did, which the screen
shows the same. A font is compared by its characters, as nxwright may code
their glyphs in other bytes too. So a folder the round trip confirms
compiles into a file that shows the same, though its pictures' and fonts'
bytes may differ.

The file does not keep the names of its pages, components, int variables,
and macros, only a checksum of each. Each name is the one the Nextion
Editor or nxwright gives, or one the file's code keeps as text, as
`page settings` does, where its checksum matches. Any other gets a
readable name, such as text3 for the text of ID 3, which the command lists
with what it names. Such a name's checksum differs in the file compiled
again, so names are compared by their text, and the file's checksum, which
covers them, is not compared.

A file made by an older Nextion Editor, such as 1.65.1, is decompiled too
when nxwright can read how that version lays out its files. Such a file's
folder is not compiled again, as nxwright compiles only with the firmware of
the Nextion Editor 1.68.2. The command writes the folder, with a warning
that the round trip check is disabled. nxwright reads how each version from
1.60.1 on lays out its files, and refuses a file made by an older one.

A file made by a Nextion Editor later than 1.68.2 is refused. A later
version may number its commands differently, and the round trip check
would not catch that. Code read with the wrong numbers compiles back into
the same bytes.

Exits with 1 when the file cannot be read or decompiled, the folder
cannot be written, or the answer at the prompt is no; with 2 when <folder>
is a file or contains files; and with 3 when a folder the round trip did
not confirm is not written, as there was no terminal to prompt at, or the
input ended at the prompt.
"""
import argparse
from pathlib import Path
import shutil
import sys
import tempfile

from nxwright import NxwrightError

from nxwright.tft.commands.compile import at_terminal
from nxwright.tft.decompiling.round_trip import round_trip

# The exit codes: a file that cannot be decompiled, a folder that cannot be
# written, or a folder the round trip did not confirm that the user chose
# not to write; a folder that is not empty; and a folder the round trip did
# not confirm, not written as there was nobody to prompt. A script can then
# tell the last from a refusal, as extract's code 3 in nxwright does.
_FAILED, _FOLDER_NOT_EMPTY, _NO_ANSWER = 1, 2, 3
# How many characters of a value a difference shows, as a piece of the file
# may be long.
_MOST_SHOWN = 80


def main(arguments: list) -> int:
    parser = argparse.ArgumentParser(prog="nxwright decompile",
                                     description="Turns a TFT file back into a source folder, "
                                     "checked by compiling it again.")
    parser.add_argument("file", type=Path)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--continue-unconfirmed", action="store_true",
                        help="write a folder the round trip did not confirm without prompting")
    options = parser.parse_args(arguments)
    if options.folder.exists() and (not options.folder.is_dir()
                                    or any(options.folder.iterdir())):
        print("nxwright decompile: %s is not an empty folder; nothing was written" % options.folder,
              file=sys.stderr)
        return _FOLDER_NOT_EMPTY
    with tempfile.TemporaryDirectory(prefix="nxwright-decompile-") as scratch:
        written = Path(scratch) / "folder"
        try:
            result = round_trip(options.file.read_bytes(), str(options.file), written)
        except (OSError, NxwrightError) as error:
            print("nxwright decompile: %s" % error, file=sys.stderr)
            return _FAILED
        if result.warning:
            print("nxwright decompile: warning: %s" % result.warning, file=sys.stderr)
        _print_names(result.names)
        confirmed = result.unchecked_reason is None and not result.mismatches
        if not confirmed:
            _warn_unconfirmed(result, options.file)
            if not options.continue_unconfirmed:
                stopped = _stop_unless_user_goes_on()
                if stopped is not None:
                    return stopped
        try:
            shutil.copytree(written, options.folder, dirs_exist_ok=True)
        except OSError as error:
            print("nxwright decompile: %s" % error, file=sys.stderr)
            return _FAILED
    if confirmed and result.again is not None:
        print("nxwright decompile: wrote %s, which compiles into a file of the same content as %s"
              % (options.folder, options.file))
    else:
        print("nxwright decompile: wrote %s" % options.folder)
    return 0


def _warn_unconfirmed(result, file: Path):
    """Prints why the round trip `result` did not confirm the folder: the
    refusal that kept it from being compiled again, or each difference
    between `file` and the file compiled again."""
    if result.unchecked_reason is not None:
        print("nxwright decompile: warning: the round trip could not check the folder: %s"
              % result.unchecked_reason, file=sys.stderr)
        return
    print("nxwright decompile: warning: the folder compiles into a file that differs from %s:"
          % file, file=sys.stderr)
    for mismatch in result.mismatches:
        print("  %s: %s in %s, %s compiled again" % (
            mismatch.where, _shown(mismatch.original), file, _shown(mismatch.again)),
            file=sys.stderr)


def _stop_unless_user_goes_on():
    """Prompts the user whether to write a folder the round trip did not
    confirm, as nxwright's extract does (cli.py, go_on_past).
    Returns None when they choose to go on, or else the exit code, having
    said why nothing was written."""
    why = "there was no terminal to prompt at"
    while at_terminal():
        try:
            answer = input("Go on anyway? [y/N]: ").strip().lower()
        except EOFError:
            why = "the input ended at the prompt"
            break
        if answer in ("y", "yes"):
            return None
        if answer in ("", "n", "no"):
            print("nxwright decompile: stopped; nothing was written", file=sys.stderr)
            return _FAILED
        print("Not one of the choices: y, n")
    print("nxwright decompile: %s, so nothing was written. Pass --continue-unconfirmed to write "
          "this folder." % why, file=sys.stderr)
    return _NO_ANSWER


def _print_names(names: list):
    """Prints each name no guess matched, which the folder gives a readable
    name, and what it names, or nothing when every name matched. `names`
    is RoundTrip's: [(key, Name)], a key ("page", page ID), ("object", page
    ID, object ID), ("int", name), or ("macro", name)."""
    if not names:
        return
    print("%d names matched no guess, and have readable names in the folder:" % len(names))
    for key, name in names:
        print("  %s: %s" % (name.text, _owner(key)))


def _owner(key: tuple) -> str:
    """Returns what the name of `key` names, in words."""
    kind = key[0]
    if kind == "page":
        return "page %d" % key[1]
    if kind == "object":
        return "object %d of page %d" % (key[2], key[1])
    return "an int variable of program.s" if kind == "int" else "a macro"


def _shown(value) -> str:
    """Returns `value` as a difference shows it: its repr, cut to
    _MOST_SHOWN characters."""
    text = repr(value)
    return text if len(text) <= _MOST_SHOWN else text[:_MOST_SHOWN] + "..."
