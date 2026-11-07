"""The first probes, those the work on nxwright's compile starts from: the
blank project of each series' base folder, and six one-change variants of
the T one, the probes `ResearchNotes/tft/tft-files.md` was written from.

nxwright writes nothing yet, so each probe compares no piece. Its check is that
nxwright's reader (tft/tft_file.py) splits the Nextion Editor's file, with
every checksum and size the file states holding. Run them with
`tools.tft.probe run first_probes`.
"""
from pathlib import Path

from PIL import Image

from tools.tft.probing.probe_runner import BASE_MODELS, Probe, ProbeMismatch

# The text component the variants add, at the base page's top left, in the
# base folder's font.
_TEXT = '''
[[component]]
name = "t0"
type = "text"
x = 10
y = 10
w = 100
h = 30
font = "NotoSans24"
txt = "Hi"
txt_maxl = 10
'''


def _nothing(project: Path) -> dict:
    return {}


def _read(data: bytes) -> dict:
    """Raises ProbeMismatch unless the reader splits `data`, every checksum
    and size holding. Gives no piece, as nxwright writes none yet."""
    from nxwright.tft.tft_file import TftFileError, read_tft
    try:
        read_tft(data, "the Nextion Editor's file")
    except TftFileError as error:
        raise ProbeMismatch(str(error)) from None
    return {}


def _probe(name: str, base: str, change=None) -> Probe:
    return Probe(name, base, change, _nothing, _read)


def _add_text(folder: Path):
    page = folder / "pages" / "page0.page.toml"
    page.write_text(page.read_text(encoding="utf-8") + _TEXT, encoding="utf-8")


def _add_text_and_code(folder: Path):
    _add_text(folder)
    (folder / "pages" / "page0.nx").write_text('on t0.up:\n  t0.txt="Yo"\n', encoding="utf-8")


def _add_long_text(folder: Path):
    _add_text(folder)
    page = folder / "pages" / "page0.page.toml"
    page.write_text(page.read_text(encoding="utf-8").replace("txt_maxl = 10", "txt_maxl = 20"),
                    encoding="utf-8")


# The changes call nxwright's library, not its command line, which loads every
# package nxwright uses, some of which the Editor tool's Python lacks.
def _add_page(folder: Path):
    from nxwright.source.source_folder import add_page
    add_page(folder, "page1")


def _add_picture(folder: Path):
    from nxwright.source.resource_adding import add_pictures
    # Drawn beside the folder, which add_pictures copies it into.
    picture = folder.parent / "red.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(picture)
    add_pictures(folder, [picture])


def _add_int(folder: Path):
    program = folder / "program.nx"
    program.write_text(program.read_text(encoding="utf-8").replace(
        "int sys0=0,sys1=0,sys2=0", "int sys0=0,sys1=0,sys2=0,count=5"), encoding="utf-8")


PROBES = [_probe("blank-" + series, series) for series in BASE_MODELS] + [
    _probe("T-text", "T", _add_text),
    _probe("T-text-code", "T", _add_text_and_code),
    _probe("T-text-maxl-20", "T", _add_long_text),
    _probe("T-second-page", "T", _add_page),
    _probe("T-picture", "T", _add_picture),
    _probe("T-int", "T", _add_int),
]
