"""The probes of the whole compile: projects of pages, texts, numbers,
buttons, and variables, which nxwright compiles alone, borrowing nothing, as
the compile command does (commands/compile.py, compile_project), compared
with the Nextion Editor's file, part by part. Run them with `tools.tft.probe
run compile_probes`.

Six keep the whole compile's fixtures: the headers, the section's table, the
user code, and the file's checksum, made on zeros for the firmware. Not the
padding or the resources, which packaging's tests cover.
"""
from pathlib import Path

from PIL import Image

from nxwright.tft.commands.compile import compile_project
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import editor_file, on_pages, whole_file, with_components
from nxwright.tft.firmware import zero_firmware
from nxwright.tft.packaging import Firmware
from tools.tft.probing.packaging_probes import probe_firmware
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.shared_attribute_probes import IntsChange
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.variable_probes import variable_component
from nxwright.tft.project import Project
from nxwright.tft.tft_file import HEADER_1_SIZE, HEADER_2_END, TABLE_SIZE, read_tft

FIXTURES = "compile"


def fixture_pieces(project: Project, firmware: Firmware) -> dict:
    """Returns the pieces the whole compile's fixtures keep, from compiling
    `project` with `firmware`, zeros in tests: the two headers, the
    section's table, the user code, and the file's checksum."""
    data = compile_project(project, firmware, any_release=True)
    tft = read_tft(data, "nxwright's file", check=False)
    section, user = tft.section_place, tft.user_code_place
    return {"header-1": data[:HEADER_1_SIZE], "header-2": data[HEADER_1_SIZE:HEADER_2_END],
            "table": data[section:section + TABLE_SIZE], "user-code": data[user:-4],
            "checksum": data[-4:]}


def _kept(project: Path) -> dict:
    loaded = Project.from_file(project)
    return fixture_pieces(loaded, zero_firmware(probe_firmware(loaded.settings.model.series)))


# Three pages, two more int variables, and code in events of two pages: the
# parts of the frame and the statements together.
_PAGES_INTS_AND_CODE = IntsChange((
    with_components(code="on page0.down:\n  dim = 50\n  count = count + 1\n"),
    with_components(page="settings", code="on settings.up:\n  limit = limit * 2\n"),
    with_components(page="about")), ("count=5", "limit=-7"))

# Two texts on page0, and t0's up setting t1's txt: the frame, a type, and
# the statements together.
_TWO_TEXTS_AND_CODE = with_components(text_component(), text_component("t1", y=60),
                                      code='on t0.up:\n  t1.txt="Yo"\n')

# A number of val 123 beside a text on page0, setting the text's txt, and a
# number on page1: two types together, over two pages.
_NUMBERS_AND_A_TEXT = on_pages(
    with_components(number_component(val=123), text_component(y=60),
                    code='on n0.up:\n  t0.txt="Yo"\n'),
    with_components(number_component(val=-5), page="page1"))

# Two buttons beside a text on page0, the first's events with code of their
# own, and a button on page1: the buttons' own event blocks, over two pages.
_BUTTONS_AND_A_TEXT = on_pages(
    with_components(button_component(), button_component("b1", y=70), text_component(y=130),
                    code='on b0.down:\n  sys0=1\non b0.up:\n  t0.txt="Yo"\n'),
    with_components(button_component(), page="page1"))

# Two variables beside a text on page0, code setting the text's txt and a
# variable's val, and a variable on page1: components that are not drawn,
# over two pages.
_VARIABLES_AND_A_TEXT = on_pages(
    with_components(variable_component(val=7), text_component(), variable_component("va1"),
                    code='on t0.up:\n  va1.val=va0.val+1\n  t0.txt="Yo"\n'),
    with_components(variable_component(val=-5), page="page1"))


def _resources_and_pages(folder: Path):
    """Two pictures, a second font, and a second page: the user code's place
    moved by the resources."""
    from nxwright.project.truetype import NOTO_SANS
    from nxwright.source.resource_adding import add_font, add_pictures
    from nxwright.source.source_folder import add_page
    pictures = [folder.parent / "red.png", folder.parent / "blue.png"]
    Image.new("RGB", (8, 4), (255, 0, 0)).save(pictures[0])
    Image.new("RGB", (4, 8), (0, 0, 255)).save(pictures[1])
    add_pictures(folder, pictures)
    add_font(folder, NOTO_SANS, 16)
    add_page(folder, "second")


def _the_most_pages(folder: Path):
    """The most pages the Nextion Editor compiles, 251 (editor_limits.MOST_PAGES)."""
    from nxwright.project.editor_limits import MOST_PAGES
    from nxwright.source.source_folder import add_page
    for number in range(1, MOST_PAGES):
        add_page(folder, "page%d" % number)


def _eight_hundred_ints(folder: Path):
    """800 int variables, 3200 bytes of the 3584 of NX4832T035's memory: the
    int area, the variables' table, and each page's base moved far on."""
    program = folder / "program.nx"
    more = ",".join("v%d=%d" % (number, number * 7 - 900) for number in range(797))
    program.write_text(program.read_text(encoding="utf-8").replace(
        "int sys0=0,sys1=0,sys2=0", "int sys0=0,sys1=0,sys2=0," + more), encoding="utf-8")


def _forty_pictures_and_eight_fonts(folder: Path):
    """40 pictures of other sizes and colours, and 7 more fonts, 8 in all:
    the resources' tables and the user code's place far on."""
    from nxwright.project.truetype import NOTO_SANS
    from nxwright.source.resource_adding import add_font, add_pictures
    pictures = []
    for number in range(40):
        pictures.append(folder.parent / ("picture%d.png" % number))
        Image.new("RGB", (4 + number * 3, 2 + number * 5),
                  (number * 40 % 256, 255 - number * 30 % 256, 99)).save(pictures[-1])
    add_pictures(folder, pictures)
    # Sizes apart from the base folder's own font, NotoSans24.
    for size in (13, 17, 21, 25, 29, 33, 37):
        add_font(folder, NOTO_SANS, size)


PROBES = [
    Probe("compile-T-blank", "T", None, whole_file, editor_file, FIXTURES, _kept),
    Probe("compile-T-pages-ints-code", "T", _PAGES_INTS_AND_CODE, whole_file, editor_file,
          FIXTURES, _kept),
    Probe("compile-T-resources-and-pages", "T", _resources_and_pages, whole_file, editor_file),
    Probe("compile-T-texts", "T", _TWO_TEXTS_AND_CODE, whole_file, editor_file, FIXTURES, _kept),
    Probe("compile-T-numbers-and-a-text", "T", _NUMBERS_AND_A_TEXT, whole_file, editor_file,
          FIXTURES, _kept),
    Probe("compile-T-buttons-and-a-text", "T", _BUTTONS_AND_A_TEXT, whole_file, editor_file,
          FIXTURES, _kept),
    Probe("compile-T-variables-and-a-text", "T", _VARIABLES_AND_A_TEXT, whole_file,
          editor_file, FIXTURES, _kept),
    # Projects past what the probes above have: the most pages, many int
    # variables, and many pictures and fonts.
    Probe("compile-T-the-most-pages", "T", _the_most_pages, whole_file, editor_file),
    Probe("compile-T-eight-hundred-ints", "T", _eight_hundred_ints, whole_file, editor_file),
    Probe("compile-T-forty-pictures-and-eight-fonts", "T", _forty_pictures_and_eight_fonts,
          whole_file, editor_file),
]
