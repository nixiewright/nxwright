"""Catalogs every attribute the Editor shows, for every component type: the
every-component project as nxwright builds it, then its variants, each with
its choice attributes set to one choice. Merges the catalogs, compares them
with nxwright's component defaults, and writes a report (README.md). Last, it
checks that none of nxwright's own descriptions of attributes equals an
Editor's hint, and says which do.

    python tools/editor/catalog_variants.py [folder]

Run it with the tool's own Python, from nxwright's folder. It writes the
projects, the catalogs, `merged.json`, and `report.md` in `folder`, by
default `tools/editor/build/catalog`, which git ignores: they hold the
Editor's hints, which are not nxwright's to publish. It deletes nothing. It
holds the dedicated Editor for its run, as `catalog-variants-<its process
ID>` (editor.py hold), and stops at once when another holds it.

The Attribute panel shows only the attributes that apply under the current
choices, such as `pic` once a text's `sta` is "image". So variant k sets every
choice attribute of every component to its choice k, where it has one. The
first catalog is read in full; each variant's is read with `--known`, which
skips the clicks for hints read already. A variant the Editor refuses to open
is reported and skipped. A project or catalog already in the folder, left by a run
that stopped, is used as it is: remove it to make it again.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

# Run as a script, so the folder above tools/ is put first on the import path.
NXWRIGHT_FOLDER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NXWRIGHT_FOLDER))

from nxwright.project.attribute_descriptions import describe  # noqa: E402
from nxwright.project.component_defaults import DEFAULTS_FILE  # noqa: E402
from nxwright.project.device_settings import DeviceSettings  # noqa: E402
from nxwright.project.new_project import write_new_project  # noqa: E402
from nxwright.project.screen_models import model_named  # noqa: E402
from tools.editor.catalog import (compare, copied_hints, merge, most_choices,  # noqa: E402
                                  report_markdown, variant_settings, with_values)

# The dump of a project holding one newly added component of each type, and
# the settings tests/test_every_component.py builds it with.
FIXTURE = NXWRIGHT_FOLDER / "tests" / "fixtures" / "every-component"
SETTINGS = DeviceSettings(model_named("NX8048P070"), 180, "iso-8859-1")
PAGE_FILE = Path("pages") / "00-page0.txt"
EDITOR = Path(__file__).resolve().parent / "editor.py"
# The holder whose hold keeps the dedicated Editor this run's: its own, so
# that a second run at once is refused, rather than taken for this one.
HOLDER = "catalog-variants-%d" % os.getpid()


def main(arguments: list) -> int:
    folder = Path(arguments[0] if arguments else NXWRIGHT_FOLDER / "tools" / "editor" / "build"
                  / "catalog").resolve()
    folder.mkdir(parents=True, exist_ok=True)
    project = folder / "every-component.HMI"
    _build(FIXTURE, project)
    # Its commands run as one holder's, so that no one else's lands between
    # them (editor.py hold).
    held = _editor("hold", HOLDER, "--minutes", "60")
    if held.returncode != 0:
        print(held.stderr.strip(), file=sys.stderr)
        return 1
    try:
        catalogs = _all_catalogs(folder, project)
    finally:
        released = _editor("release", HOLDER)
        if released.returncode != 0:
            # Else the Editor would stay held, to its time, by a name no agent knows.
            print("The hold %s was not released: %s" % (HOLDER, released.stderr.strip()),
                  file=sys.stderr)
    if catalogs is None:
        print("Stopped: the every-component project could not be catalogued", file=sys.stderr)
        return 1
    defaults_catalog = catalogs[0]
    merged = merge(catalogs)
    defaults = tomllib.loads(DEFAULTS_FILE.read_text(encoding="utf-8"))
    comparison = compare(merged, defaults_catalog, defaults)
    (folder / "merged.json").write_text(json.dumps(
        {name: {attribute: vars(seen) for attribute, seen in attributes.items()}
         for name, attributes in merged.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    (folder / "report.md").write_text(report_markdown(merged, comparison), encoding="utf-8")
    print("Wrote %s" % (folder / "report.md"))
    # nxwright's descriptions are its own words (nxwright/project/attribute_descriptions.toml).
    copied = copied_hints(merged, describe)
    for name, attribute in copied:
        print("The description of %s's %s equals the Editor's hint" % (name, attribute),
              file=sys.stderr)
    return 1 if copied else 0


def _all_catalogs(folder: Path, project: Path):
    """Catalogs the every-component project, then each variant of it, and
    returns the catalogs, the project's first; None when the project itself
    could not be catalogued."""
    defaults_catalog = _catalog(project, folder / "defaults.json", "defaults", None)
    if defaults_catalog is None:
        return None
    catalogs = [defaults_catalog]
    for choice in range(most_choices(merge(catalogs)) + 1):
        settings = variant_settings(merge([defaults_catalog]), defaults_catalog, choice)
        if not settings:
            continue
        name = "choice %d" % choice
        dump = folder / ("dump-choice-%d" % choice)
        shutil.copytree(FIXTURE, dump, dirs_exist_ok=True)
        page = (FIXTURE / PAGE_FILE).read_text(encoding="utf-8")
        (dump / PAGE_FILE).write_text(with_values(page, settings), encoding="utf-8")
        variant = folder / ("choice-%d.HMI" % choice)
        _build(dump, variant)
        known = folder / "known.json"
        known.write_text(json.dumps(_known(catalogs)), encoding="utf-8")
        catalog = _catalog(variant, folder / ("choice-%d.json" % choice), name, known)
        if catalog is not None:
            catalogs.append(catalog)
    return catalogs


def _build(dump: Path, project: Path):
    """Builds `project` from a dump, unless an earlier run built it: nxwright
    writes no project over another."""
    if not project.exists():
        write_new_project(dump, SETTINGS, project)


def _catalog(project: Path, file: Path, variant: str, known: Path):
    """Opens `project` in the dedicated Editor and catalogs it into `file`.
    Returns the catalog, or None when the Editor refused it, saying why. The
    two commands run as HOLDER's, whose hold keeps anyone else's from
    opening another project in between; the catalog must still name the copy
    opened, or the run stops."""
    if file.exists():
        # Left by an earlier run, which stopped later on.
        print("Reusing %s" % file)
        return json.loads(file.read_text(encoding="utf-8"))
    opened = None
    for command in (["open", str(project)],
                    ["catalog", str(file), "--variant", variant]
                    + (["--known", str(known)] if known else [])):
        done = _editor(*command, "--as", HOLDER)
        if done.returncode != 0:
            print("Skipped %s: %s" % (variant, done.stderr.strip()), file=sys.stderr)
            return None
        opened = opened or done.stdout.strip().removeprefix("Opened ")
    catalog = json.loads(file.read_text(encoding="utf-8"))
    if catalog["project"] != opened:
        sys.exit("Stopped: the Editor showed %s while %s was catalogued, not the copy opened"
                 % (catalog["project"], variant))
    return catalog


def _editor(*command: str) -> subprocess.CompletedProcess:
    """Runs one command of editor.py, capturing what it says."""
    return subprocess.run([sys.executable, str(EDITOR)] + list(command), cwd=NXWRIGHT_FOLDER,
                          capture_output=True, text=True, encoding="utf-8")


def _known(catalogs: list) -> dict:
    """The catalogs so far as one, for `editor.py catalog --known`."""
    return {"variant": "known", "objects": [entry for catalog in catalogs
                                            for entry in catalog["objects"]]}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
