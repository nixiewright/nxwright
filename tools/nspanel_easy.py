"""Checks that nxwright still builds NSPanel-Easy's display files byte for byte.

NSPanel-Easy (https://github.com/edwardtfn/NSPanel-Easy) keeps three source
folders in hmi/src. NSPanel-Easy also commits the project file and the TFT
file that nxwright builds from each folder, and keeps them in hmi. This script
builds each folder again with this checkout's nxwright, and compares the
results with the committed files. A difference means that this nxwright
writes something different from the version NSPanel-Easy built with.

Run the script from nxwright's folder, and pass it a clone of NSPanel-Easy:

    python -m tools.nspanel_easy <NSPanel-Easy folder>

Or let the script clone NSPanel-Easy's main branch from GitHub into a
temporary folder:

    python -m tools.nspanel_easy --clone

The script exits with 1 when the clone or a compile fails, or when a file
differs. For each difference, it prints the output of `nxwright diff` for a
project file, or of `nxwright tft-compare` for a TFT file.

NSPanel-Easy builds with its own script, hmi/dev/scripts/hmi_build.sh, which
installs the version of nxwright that NSPanel-Easy picks. This script repeats
what hmi_build.sh does before compiling, so that only the version of nxwright
differs:

- The source folders do not contain their fonts. Instead, each folder lists
  its fonts in fonts.sha256, with a font's SHA-256 and path on each line, and
  the fonts themselves are in hmi/dev/fonts. The script copies each folder and
  puts its fonts back.
- The firmware comes from the one TFT file in hmi/dev/firmware.
- The script compiles with --no-lock.
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


NSPANEL_EASY = "https://github.com/edwardtfn/NSPanel-Easy"


def main() -> int:
    arguments = parse_arguments(sys.argv[1:])
    # Without this, the lines printed here could appear after the output of
    # the nxwright commands that follow them.
    sys.stdout.reconfigure(line_buffering=True)
    if not arguments.clone:
        return check_checkout(arguments.checkout.resolve())
    with tempfile.TemporaryDirectory() as clone_name:
        clone = Path(clone_name) / "NSPanel-Easy"
        print("Cloning %s" % NSPANEL_EASY)
        if subprocess.run(["git", "clone", "--depth", "1", "--quiet", NSPANEL_EASY, str(clone)],
                          stdin=subprocess.DEVNULL).returncode != 0:
            print("Could not clone %s." % NSPANEL_EASY, file=sys.stderr)
            return 1
        return check_checkout(clone)


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    """Reads the command line `arguments`, which give either the folder of an
    NSPanel-Easy clone or --clone. Raises SystemExit, after printing the
    usage, when both or neither are given."""
    parser = argparse.ArgumentParser(
        description="Build NSPanel-Easy's source folders with this checkout's "
                    "nxwright, and compare the results with the files NSPanel-Easy "
                    "commits.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("checkout", type=Path, nargs="?", help="a clone of NSPanel-Easy")
    source.add_argument("--clone", action="store_true",
                        help="clone NSPanel-Easy from GitHub into a temporary folder, "
                             "and check that clone")
    return parser.parse_args(arguments)


def check_checkout(checkout: Path) -> int:
    """Builds the source folders of the NSPanel-Easy clone `checkout`, and
    compares the results with the files NSPanel-Easy commits. Returns the
    script's exit code: 0 when every file matches, 1 otherwise."""
    hmi = checkout / "hmi"
    sources = sorted(folder for folder in (hmi / "src").iterdir()
                     if (folder / "app.toml").is_file())
    if not sources:
        print("No source folders in %s." % (hmi / "src"), file=sys.stderr)
        return 1
    firmware = list((hmi / "dev" / "firmware").glob("*.tft"))
    if len(firmware) != 1:
        print("Expected one TFT file in %s, found %d."
              % (hmi / "dev" / "firmware", len(firmware)), file=sys.stderr)
        return 1
    fonts = {hashlib.sha256(font.read_bytes()).hexdigest(): font
             for font in (hmi / "dev" / "fonts").glob("*.zi")}

    failures = 0
    with tempfile.TemporaryDirectory() as work_name:
        for source in sources:
            failures += check_project(source, hmi, firmware[0], fonts, Path(work_name))
    if failures:
        print("%d file(s) did not match NSPanel-Easy's." % failures, file=sys.stderr)
        return 1
    print("Every file matches NSPanel-Easy's.")
    return 0


def check_project(source: Path, hmi: Path, firmware: Path, fonts: dict[str, Path],
                  work: Path) -> int:
    """Builds the project file and the TFT file of the source folder `source`
    in the folder `work`, and compares each with the one NSPanel-Easy commits
    in `hmi`. Returns how many of the two did not match. A failed compile
    counts as two."""
    name = source.name
    print("Building %s" % name)
    staging = work / "src" / name
    shutil.copytree(source, staging)
    restore_fonts(staging, fonts)
    built_hmi = work / (name + ".hmi")
    built_tft = work / (name + ".tft")
    if nxwright("compile", "--firmware", str(firmware),
                "--project-file", str(built_hmi), "--no-lock", "--no-backup",
                str(staging), str(built_tft)) != 0:
        print("  the compile failed")
        return 2
    failures = 0
    for built, committed, command in ((built_hmi, hmi / (name + ".hmi"), "diff"),
                                      (built_tft, hmi / (name + ".tft"), "tft-compare")):
        if not committed.is_file():
            failures += 1
            print("  %s is missing from NSPanel-Easy" % committed.name)
        elif built.read_bytes() != committed.read_bytes():
            failures += 1
            print("  %s differs:" % committed.name)
            nxwright(command, str(committed), str(built))
        else:
            print("  %s matches" % committed.name)
    return failures


def restore_fonts(folder: Path, fonts: dict[str, Path]) -> None:
    """Puts back the fonts that `folder`'s fonts.sha256 lists, each at its
    listed path, then removes fonts.sha256, so that the folder is the same as
    the one NSPanel-Easy's build compiles. `fonts` maps a SHA-256 to the font
    file with that SHA-256. Raises SystemExit if a listed SHA-256 matches no
    font, or if a listed path leads out of `folder`."""
    manifest = folder / "fonts.sha256"
    if not manifest.is_file():
        return
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, path = line.split(maxsplit=1)
        if digest not in fonts:
            raise SystemExit("%s: fonts.sha256 lists %s, but no font in "
                             "hmi/dev/fonts has its SHA-256." % (folder.name, path))
        # fonts.sha256 comes from another repository, so the script rejects a
        # path that leads out of the folder rather than writing to it.
        target = (folder / path).resolve()
        if not target.is_relative_to(folder.resolve()):
            raise SystemExit("%s: fonts.sha256 lists %s, which is outside the folder."
                             % (folder.name, path))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fonts[digest], target)
    manifest.unlink()


def nxwright(*arguments: str) -> int:
    """Runs this checkout's nxwright with `arguments`, and returns its exit
    code. nxwright gets no standard input, so it cannot stop at a prompt to
    wait for an answer."""
    return subprocess.run([sys.executable, "-m", "nxwright", *arguments],
                          stdin=subprocess.DEVNULL).returncode


if __name__ == "__main__":
    sys.exit(main())
