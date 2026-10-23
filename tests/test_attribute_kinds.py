"""Whether an attribute is a text or a number, by its component's type: a
direction's `dir` and a width's `vvs2` are numbers on the scrolling text, the
combo box, the waveform, and the gauge, and texts on the data record and the
file browser. Page files and defaults files nxwright wrote before hold such a
number as a text of its bytes, which the build still reads."""
import tomllib
import unittest

from nxwright import NxwrightError
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.project.page_text import page_from_text, page_to_text
from nxwright.language.resource_names import ResourceNames
from nxwright.project.component_defaults import DEFAULTS_FILE, defaults_from_toml, nxwright_defaults
from nxwright.source.page_source import PageSource, page_from_source, page_to_source

# The texts and lists need a font.
NAMES = ResourceNames([], ["Sans"])

# A page holding a component of each type with `dir` or `vvs2`, each given
# the values the test passes, written as a page file writes them.
PAGE = """[page]
name = "first"
type = "page"
x = 0
y = 0
w = 800
h = 480

[[component]]
name = "g0"
type = "scrolling-text"
x = 0
y = 0
w = 100
h = 30
dir = %(g0_dir)s
vvs2 = %(g0_vvs2)s

[[component]]
name = "cb0"
type = "combo-box"
x = 0
y = 40
w = 100
h = 30
dir = %(cb0_dir)s

[[component]]
name = "s0"
type = "waveform"
x = 0
y = 80
w = 100
h = 60
dir = %(s0_dir)s

[[component]]
name = "z0"
type = "gauge"
x = 120
y = 0
w = 100
h = 100
vvs2 = %(z0_vvs2)s

[[component]]
name = "fb0"
type = "file-browser"
x = 120
y = 120
w = 100
h = 100
dir = "sd1/"

[[component]]
name = "d0"
type = "data-record"
x = 240
y = 0
w = 200
h = 100
dir = "a^b"
"""
NUMBERS = {"g0_dir": "2", "g0_vvs2": "300", "cb0_dir": "3", "s0_dir": "1", "z0_vvs2": "4"}
# The same values as page files nxwright wrote before held them.
TEXTS = {"g0_dir": r'"\u0002"', "g0_vvs2": r'"\u002c\u0001"', "cb0_dir": r'"\u0003"',
         "s0_dir": r'"\u0001"', "z0_vvs2": r'"\u0004"'}
STORED = {("g0", "dir"): b"\x02", ("g0", "vvs2"): b"\x2c\x01", ("cb0", "dir"): b"\x03",
          ("s0", "dir"): b"\x01", ("z0", "vvs2"): b"\x04", ("fb0", "dir"): b"sd1/",
          ("d0", "dir"): b"a^b"}


def built(values: dict, encoding: str = "iso-8859-1"):
    """Returns the page block PAGE builds to, given `values`."""
    return page_from_source(PageSource(PAGE % values, ""), "first", NAMES, nxwright_defaults(),
                            encoding=encoding)


def stored(page, name: str, attribute: str) -> bytes:
    """The bytes the page block `page` stores for `attribute` of `name`."""
    found = next(page_object for page_object in page.objects
                 if page_object.attribute("objname") == name.encode())
    return found.attribute(attribute)


class PageFileTest(unittest.TestCase):

    def test_numbers_build_to_their_bytes(self):
        page = built(NUMBERS)
        for (name, attribute), data in STORED.items():
            with self.subTest(name=name, attribute=attribute):
                self.assertEqual(stored(page, name, attribute), data)

    def test_the_text_form_builds_to_the_same_bytes(self):
        for encoding in ("iso-8859-1", "utf-8"):
            with self.subTest(encoding=encoding):
                self.assertEqual(built(TEXTS, encoding), built(NUMBERS, encoding))

    def test_a_text_of_another_length_is_refused(self):
        # It would store the attribute at another width than the screen reads.
        for key, text in (("g0_dir", r'"\u0002\u0000"'), ("g0_vvs2", r'"\u0001"'),
                          ("z0_vvs2", '""')):
            with self.subTest(key=key):
                with self.assertRaisesRegex(NxwrightError, "must be a number"):
                    built(dict(NUMBERS, **{key: text}))

    def test_a_folder_and_a_record_keep_their_texts(self):
        text = (PAGE % NUMBERS).replace('dir = "sd1/"', "dir = 1")
        # fb0 is object 5.
        with self.assertRaisesRegex(NxwrightError, "object 5: dir must be a string"):
            page_from_source(PageSource(text, ""), "first", NAMES, nxwright_defaults())

    def test_extracting_writes_numbers(self):
        toml = page_to_source(built(TEXTS), NAMES, nxwright_defaults()).toml
        tables = {table["name"]: table for table in tomllib.loads(toml)["component"]}
        self.assertEqual(
            {(name, attribute): tables[name][attribute] for name, attribute in STORED},
            {("g0", "dir"): 2, ("g0", "vvs2"): 300, ("cb0", "dir"): 3, ("s0", "dir"): 1,
             ("z0", "vvs2"): 4, ("fb0", "dir"): "sd1/", ("d0", "dir"): "a^b"})


class DumpTest(unittest.TestCase):

    def test_a_dump_writes_numbers_and_reads_the_text_form(self):
        page = built(NUMBERS)
        text = page_to_text(page)
        scrolling = text[text.index("object 1"):text.index("object 2")]
        self.assertIn("  dir = 2\n", scrolling)
        self.assertIn("  vvs2 = 300\n", scrolling)
        self.assertEqual(page_from_text(text), page)
        older = text.replace("  dir = 2\n", '  dir = "\\x02"\n', 1)
        self.assertNotEqual(older, text)
        self.assertEqual(page_from_text(older), page)


class DefaultsFileTest(unittest.TestCase):

    def test_the_defaults_file_writes_numbers(self):
        attributes = {name: table["attributes"]
                      for name, table in tomllib.loads(DEFAULTS_FILE.read_text("utf-8")).items()}
        self.assertEqual(
            (attributes["waveform"]["dir"], attributes["scrolling-text"]["dir"],
             attributes["scrolling-text"]["vvs2"], attributes["combo-box"]["dir"],
             attributes["gauge"]["vvs2"]),
            (0, 1, 0, 1, 2))

    def test_its_values_keep_their_bytes(self):
        defaults = nxwright_defaults()
        self.assertEqual(
            [dict(defaults[TYPES_BY_NAME[type_name]].attributes)[attribute]
             for type_name, attribute in (("waveform", "dir"), ("scrolling-text", "dir"),
                                          ("scrolling-text", "vvs2"), ("combo-box", "dir"),
                                          ("gauge", "vvs2"))],
            [b"\x00", b"\x01", b"\x00\x00", b"\x01", b"\x02"])

    def test_a_folders_copy_in_the_text_form_is_read(self):
        # Each source folder keeps its own copy, as nxwright wrote it.
        text = ('[scrolling-text]\nevents = []\n\n[scrolling-text.attributes]\n'
                'dir = "\\u0001"\nvvs2 = "\\u0000\\u0000"\n')
        defaults = defaults_from_toml(text, "defaults.toml")
        self.assertEqual(defaults[TYPES_BY_NAME["scrolling-text"]].attributes,
                         [("dir", b"\x01"), ("vvs2", b"\x00\x00")])
        with self.assertRaisesRegex(NxwrightError, "dir must be a number"):
            defaults_from_toml(text.replace('"\\u0001"', '"\\u0001\\u0001"'), "defaults.toml")


if __name__ == "__main__":
    unittest.main()
