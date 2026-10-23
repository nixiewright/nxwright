"""The sections of the switch's panel that show code (language/nxlang_samples.py),
and the language server's nxwright/nxlangSamples request giving them; and the
list of what else nxlang lets you do, and its request,
nxwright/nxlangMoreFeatures."""
from pathlib import Path
import tempfile
import tomllib
import unittest

from nxwright.language.nxlang_samples import MORE_FEATURES, SECTIONS, panel_sections
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.resources import COPIED_KINDS
from nxwright.project.screen_models import model_named
from nxwright.source.source_folder import (add_page, export_dump, import_dump,
                                           new_source_folder)
from tests.language_server_connection import initialized


def sample_folder(root: Path, language: str) -> Path:
    """Writes a source folder at `root` in `language`, "nextion" or "nxlang",
    with a page per section that has code in that language, holding that
    code and the section's components; returns `root`, which the tests
    then build."""
    new_source_folder(root, DeviceSettings(model_named("NX4832T035"), 0, "utf-8"), language)
    for section in SECTIONS:
        files = section.strict if language == "nextion" else section.nxlang
        if not files:
            continue
        add_page(root, section.key)
        page = root / "pages" / ("%s.page.toml" % section.key)
        page.write_text(page.read_text(encoding="utf-8")
                        + "".join(_component(name, kind) for name, kind in section.components),
                        encoding="utf-8", newline="\n")
        for path, text in files:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(text, encoding="utf-8", newline="\n")
    return root


def _component(name: str, kind: str) -> str:
    """A component's table in a page file: a variable holding a number or a
    text, or a hotspot, an invisible button."""
    if kind == "hotspot":
        return ('\n[[component]]\nname = "%s"\ntype = "hotspot"\nx = 0\ny = 0\nw = 10\nh = 10\n'
                % name)
    sta, value = (1, 'txt = ""\ntxt_maxl = 40') if kind == "text" else (0, "val = 0")
    return '\n[[component]]\nname = "%s"\ntype = "variable"\nsta = %d\n%s\n' % (name, sta, value)


class NxlangSamplesTest(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.root = Path(self._folder.name)

    def tearDown(self):
        self._folder.cleanup()

    def test_every_sample_builds_in_its_language(self):
        # Strict Nextion's in a folder of strict Nextion syntax, nxlang's in
        # one of nxlang: a sample that stops building fails here.
        for language in ("nextion", "nxlang"):
            with self.subTest(language=language):
                folder = sample_folder(self.root / language, language)
                export_dump(folder, self.root / ("%s-built" % language))

    def test_every_section_has_a_heading_words_and_nxlang(self):
        for section in panel_sections():
            with self.subTest(section=section["key"]):
                self.assertTrue(section["heading"] and section["words"] and section["nxlang"])
        self.assertIn("calculations", [section["key"] for section in panel_sections()])

    def test_a_side_of_several_files_gives_each_path(self):
        sharing = next(section for section in panel_sections() if section["key"] == "sharing")
        self.assertEqual(sharing["strict"], "")
        self.assertIn("// pages/sharing.nx", sharing["nxlang"])
        self.assertIn("// pages/lib/average.nx", sharing["nxlang"])

    def test_going_back_shows_what_the_panel_says(self):
        # Built, then extracted into a new folder: strict Nextion syntax, a
        # function a hidden component clicked, a constant its value, and a
        # local a variable the nxlang code did not have.
        built = self.root / "built"
        export_dump(sample_folder(self.root / "nxlang", "nxlang"), built)
        # A dump read from a project file has every resource's folder, even
        # empty; the build leaves out those the samples need not.
        for required in ("images",) + tuple(kind.folder for kind in COPIED_KINDS):
            (built / required).mkdir(exist_ok=True)
        back = self.root / "back"
        import_dump(built, back)
        app = tomllib.loads((back / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual(app["language"], "nextion")
        functions = (back / "pages" / "functions.nx").read_text(encoding="utf-8")
        names = [component["name"] for component in tomllib.loads(
            (back / "pages" / "functions.page.toml").read_text(encoding="utf-8"))["component"]]
        self.assertTrue([name for name in names if name.startswith("__f")], names)
        self.assertIn("click __f", functions)
        constants = (back / "pages" / "constants.nx").read_text(encoding="utf-8")
        self.assertIn("1200", constants)
        self.assertNotIn("LIMIT", constants)
        self.assertIn("__", constants)

    def test_the_request(self):
        connection = initialized()
        connection.handle({"jsonrpc": "2.0", "id": 2, "method": "nxwright/nxlangSamples",
                           "params": {}})
        self.assertEqual(connection.sent[-1]["result"], panel_sections())
        connection.handle({"jsonrpc": "2.0", "id": 3, "method": "nxwright/nxlangMoreFeatures",
                           "params": {}})
        self.assertEqual(connection.sent[-1]["result"], list(MORE_FEATURES))

    def test_more_features_show_their_code_between_backticks(self):
        # The panel and the README show each part between backticks as code.
        self.assertIn("write `x -= a + b`, which means `x = x - (a + b)`.", MORE_FEATURES)
        for item in MORE_FEATURES:
            with self.subTest(item=item):
                self.assertEqual(item.count("`") % 2, 0)

    def test_the_sections_keys_are_their_pages(self):
        for section in SECTIONS:
            with self.subTest(section=section.key):
                self.assertEqual(section.nxlang[0][0], "pages/%s.nx" % section.key)


if __name__ == "__main__":
    unittest.main()
