"""Every component type the Editor offers, through extract and build."""
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest

from nxwright.project.component_defaults import DEFAULTS_FILE, NAME_PREFIXES
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.new_project import write_new_project
from nxwright.project.object_types import TYPE_NAMES
from nxwright.project.page_text import page_from_text
from nxwright.project.screen_models import model_named
from nxwright.source.project_files import build, extract

# The dump of a project made with Editor 3.1.73: one page holding one newly
# added component of each type, as the Editor created them. nxwright's
# component defaults come from it. Its two pictures are the thermostat demo's
# logo, in place of the ones the project was made with.
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "every-component"
SETTINGS = DeviceSettings(model_named("NX8048P070"), 180, "iso-8859-1")


class EveryComponentTest(unittest.TestCase):

    def test_every_type_round_trips(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            # The Editor's project has no font, which its compile refuses for
            # the texts, and so does the build: the dump gets one.
            dump = folder / "dump"
            shutil.copytree(FIXTURE, dump)
            (dump / "fonts").mkdir(exist_ok=True)
            shutil.copyfile(FIXTURE.parent / "fonts" / "NotoSans20.zi", dump / "fonts" / "0.zi")
            project = folder / "objects.HMI"
            write_new_project(dump, SETTINGS, project)
            extract(project, folder / "app")
            page = tomllib.loads((folder / "app" / "pages" / "page0.page.toml").read_text(
                encoding="utf-8"))
            # Each type the defaults know is on the page: two text components, one of each other.
            types = {table["type"] for table in _tables(page)}
            defaults = tomllib.loads(DEFAULTS_FILE.read_text(encoding="utf-8"))
            self.assertEqual(types, set(defaults))
            # Each component is as newly added, so only its placement is written.
            self.assertEqual([table["name"] for table in _tables(page)
                              if table.get("defaults") is False], [])
            build(folder / "app", folder / "built.HMI")
            self.assertTrue((folder / "built.HMI").read_bytes() == project.read_bytes(),
                            "the build differs from the project extracted")

    def test_each_type_named_as_the_editor_names_a_new_one(self):
        # The page's components keep the names the Editor gave them: its
        # type's prefix and a number, t0 and t1 for its two texts.
        page = page_from_text((FIXTURE / "pages" / "00-page0.txt").read_text(encoding="utf-8"))
        named = {}
        for page_object in page.objects[1:]:
            object_type = int.from_bytes(page_object.attribute("type"), "little")
            named.setdefault(object_type, []).append(page_object.attribute("objname").decode())
        self.assertEqual(set(NAME_PREFIXES), set(TYPE_NAMES) - {121})
        for object_type, names in named.items():
            with self.subTest(type=TYPE_NAMES[object_type]):
                prefix = NAME_PREFIXES[object_type]
                self.assertEqual(names, [prefix + str(number) for number in range(len(names))])


def _tables(page: dict) -> list:
    """Returns the page's own table and its components' tables."""
    return [page["page"]] + page.get("component", [])


if __name__ == "__main__":
    unittest.main()
