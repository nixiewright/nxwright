"""Pictures drawn from SVG files (source/svg_pictures.py): what they share
with other files of the folder, their fonts, their size, and each tool that
reads a picture of a source folder: the build, the checks, the preview, the
simulator, and the language server."""
import base64
import io
import os
from pathlib import Path
import shutil
import tomllib
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from nxwright import NxwrightError
from nxwright.language_server.file_texts import FileTexts, uri_of
from nxwright.language_server.picture_view import svg_picture_view
from nxwright.source import svg_pictures
from nxwright.project.container import HmiContainer
from nxwright.project.pictures import write_png
from nxwright.project.resources import parse_image_source
from nxwright.source.defines import LAUNCH_CONFIGURATION, overriding_defines
from nxwright.source.folder_check import check_folder
from nxwright.source.project_files import extract
from nxwright.source.folder_index import FolderIndex, picture_of
from nxwright.source.resource_adding import Slot, add_pictures
from nxwright.source.resource_renaming import rename_resource
from nxwright.source.source_folder import (folder_byte_reader, folder_lister, folder_reader,
                                           parse_app, picture_file_size,
                                           read_page_components, read_text)
from nxwright.source.svg_pictures import (draw_svg_picture, prepared_svg_picture,
                                          svg_picture_size)
from nxwright.testing import preview
from nxwright.testing.folder_resources import FolderResources
from nxwright.testing.preview import Previews
from nxwright.testing.simulation import Simulation
from tests.test_folder_check import edited_page_file
from tests.test_picture_files import SourceFolderTestCase

FONTS = Path(__file__).resolve().parent / "fixtures" / "fonts"
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">%s</svg>'


def svg(content: str, width: int = 40, height: int = 20, before: str = "") -> str:
    return before + SVG % (width, height, content)


class SvgTestCase(SourceFolderTestCase):
    """The folder's picture "photo" is pictures/photo.svg."""

    def write(self, path: str, text: str):
        (self.source / path).parent.mkdir(parents=True, exist_ok=True)
        (self.source / path).write_text(text, encoding="utf-8", newline="\n")

    def photo(self, text: str):
        self.write("pictures/photo.svg", text)

    def drawn(self, path: str = "pictures/photo.svg") -> Image.Image:
        png = draw_svg_picture(path, folder_reader(self.source), folder_byte_reader(self.source),
                               self.defines())
        return Image.open(io.BytesIO(png)).convert("RGBA")

    def defines(self) -> dict:
        """The values of app.toml's defines, as a build reads them."""
        return parse_app(read_text(self.source / "app.toml"))["defines"]

    def refused(self, said: str, path: str = "pictures/photo.svg"):
        with self.assertRaises(NxwrightError) as raised:
            self.drawn(path)
        self.assertIn(said, str(raised.exception))


class DrawingTest(SvgTestCase):

    def test_a_picture_takes_the_size_its_root_gives(self):
        self.photo(svg('<rect width="40" height="20" fill="#ff0000"/>'))
        picture = self.drawn()
        self.assertEqual((picture.size, picture.getpixel((5, 5))), ((40, 20), (255, 0, 0, 255)))
        self.assertEqual(svg_picture_size("p.svg", svg("", 12, 34)), (12, 34))
        self.assertEqual(svg_picture_size("p.svg", SVG.replace("%d", "%dpx") % (5, 6, "")),
                         (5, 6))

    def test_a_size_missing_or_in_another_unit_is_refused(self):
        for root in ('<svg xmlns="http://www.w3.org/2000/svg" height="10"/>',
                     '<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10"/>',
                     '<svg xmlns="http://www.w3.org/2000/svg" width="50%" height="10"/>'):
            with self.subTest(root):
                self.photo(root)
                self.refused("must give the picture's width in whole pixels")
        self.photo(svg("", 80000, 10))
        self.refused("the picture's width, 80000, is more than 8192 pixels")

    def test_a_file_that_is_not_an_svg_is_refused(self):
        for text, said in (("<svg", "is not an SVG file"),
                           ("<html/>", "its root is <html>, not <svg>")):
            with self.subTest(text):
                self.photo(text)
                self.refused(said)

    def test_a_style_sheet_and_shapes_of_shared_files_through_two_levels(self):
        self.write("art/theme.css", ".back { fill: #0000ff; }\n")
        self.write("art/parts.svg", '<svg xmlns="http://www.w3.org/2000/svg">'
                                    '<g id="pair"><rect class="back" width="10" height="10"/>'
                                    '<use href="dot.svg#dot" x="10"/></g></svg>')
        self.write("art/dot.svg", '<svg xmlns="http://www.w3.org/2000/svg">'
                                  '<rect id="dot" width="10" height="10" fill="#00ff00"/></svg>')
        self.photo(svg('<use href="../art/parts.svg#pair"/>'
                       '<use href="../art/parts.svg#pair" x="20" y="10" '
                       'transform="translate(0 0)"/>',
                       before='<?xml-stylesheet href="../art/theme.css" type="text/css"?>\n'))
        picture = self.drawn()
        self.assertEqual([picture.getpixel(point) for point in ((5, 5), (15, 5), (25, 15),
                                                                 (35, 15), (5, 15))],
                         [(0, 0, 255, 255), (0, 255, 0, 255), (0, 0, 255, 255),
                          (0, 255, 0, 255), (0, 0, 0, 0)])

    def test_the_style_of_a_shared_file_does_not_apply(self):
        self.write("art/parts.svg", '<svg xmlns="http://www.w3.org/2000/svg">'
                                    '<style>.box { fill: #ff0000; }</style>'
                                    '<g id="group"><style>.box { fill: #ff0000; }</style>'
                                    '<rect class="box" width="10" height="10"/></g></svg>')
        self.photo(svg('<use href="../art/parts.svg#group"/>'))
        self.assertEqual(self.drawn().getpixel((5, 5)), (0, 0, 0, 255))

    def test_a_shape_used_alone_and_within_another_is_copied_once(self):
        self.write("art/parts.svg", '<svg xmlns="http://www.w3.org/2000/svg">'
                                    '<g id="panel"><rect id="knob" width="10" height="10" '
                                    'fill="#00ff00"/></g></svg>')
        self.photo(svg('<use href="../art/parts.svg#knob"/>'
                       '<use href="../art/parts.svg#panel" x="20"/>'))
        drawing = prepared_svg_picture("pictures/photo.svg", folder_reader(self.source),
                                       folder_byte_reader(self.source), {})
        self.assertEqual(drawing.text.count('id="knob"'), 1)
        picture = self.drawn()
        self.assertEqual([picture.getpixel((5, 5)), picture.getpixel((25, 5))],
                         [(0, 255, 0, 255), (0, 255, 0, 255)])

    def test_a_shared_shape_brings_its_gradient(self):
        self.write("art/parts.svg", '<svg xmlns="http://www.w3.org/2000/svg"><defs>'
                                    '<linearGradient id="red"><stop offset="0" stop-color="#f00"/>'
                                    '<stop offset="1" stop-color="#f00"/></linearGradient></defs>'
                                    '<rect id="box" width="10" height="10" fill="url(#red)"/>'
                                    '</svg>')
        self.photo(svg('<use href="../art/parts.svg#box"/>'))
        self.assertEqual(self.drawn().getpixel((5, 5)), (255, 0, 0, 255))

    def test_an_image_of_the_folder_goes_in(self):
        Path(self.source / "art").mkdir()
        (self.source / "art" / "dot.png").write_bytes(
            write_png(2, 2, bytes([0, 0, 255, 255] * 4)))
        self.photo(svg('<image href="../art/dot.png" width="40" height="20" '
                       'preserveAspectRatio="none"/>'))
        self.assertEqual(self.drawn().getpixel((5, 5)), (0, 0, 255, 255))

    def test_what_a_picture_cannot_share(self):
        self.write("art/parts.svg", '<svg xmlns="http://www.w3.org/2000/svg">'
                                    '<rect id="box" width="1" height="1"/>'
                                    '<use id="loop" href="#box"/>'
                                    '<use id="round" href="parts.svg#none"/></svg>')
        self.write("art/self.svg", '<svg xmlns="http://www.w3.org/2000/svg">'
                                   '<use id="me" href="other.svg#you"/></svg>')
        self.write("art/other.svg", '<svg xmlns="http://www.w3.org/2000/svg">'
                                    '<use id="you" href="self.svg#me"/></svg>')
        for content, said in (
                ('<use href="../art/missing.svg#box"/>', "art/missing.svg is missing"),
                ('<use href="../../outside.svg#box"/>', "is outside the source folder"),
                ('<use href="http://example.com/a.svg#box"/>', "must be a path relative"),
                ('<use href="../art/parts.svg#nothing"/>', "art/parts.svg has no element with "
                                                           "id nothing"),
                ('<use href="../art/parts.svg"/>', "must name an element of the file"),
                ('<use href="../art/self.svg#me"/>', "art/self.svg#me uses itself"),
                ('<rect id="box"/><use href="../art/parts.svg#box"/>',
                 "pictures/photo.svg and art/parts.svg both have an element with id box"),
                ('<image href="../../outside.png" width="1" height="1"/>',
                 "is outside the source folder"),
                ('<image href="../art/notes.txt" width="1" height="1"/>',
                 "is not a PNG, JPEG, GIF, WebP, or SVG file")):
            with self.subTest(content):
                self.photo(svg(content))
                self.refused(said)

    def test_a_linked_style_sheet_must_be_in_the_folder(self):
        for href, said in (("../art/none.css", "art/none.css is missing"),
                           ("../../theme.css", "is outside the source folder")):
            with self.subTest(href):
                self.photo(svg("", before='<?xml-stylesheet href="%s"?>' % href))
                self.refused(said)


class FontTest(SvgTestCase):

    def ink(self) -> int:
        return sum(1 for pixel in self.drawn().getdata() if pixel[3])

    def text(self, family: str, before: str = "") -> str:
        return svg('<text x="2" y="15" font-size="14"%s>Hi</text>'
                   % ("" if family is None else ' font-family="%s"' % family), before=before)

    def test_noto_sans_and_the_generic_families(self):
        for family in (None, "Noto Sans", "sans-serif", "serif", "Arial, sans-serif"):
            with self.subTest(family):
                self.photo(self.text(family))
                self.assertGreater(self.ink(), 20)

    def test_a_family_no_font_serves_is_refused(self):
        self.photo(self.text("Arial, Helvetica"))
        self.refused("no font is given for font-family: Arial, Helvetica")
        self.photo(svg('<text style="font: 12px Arial">Hi</text>'))
        self.refused("not the font shorthand")

    def test_a_font_file_named_by_font_face(self):
        shutil.copyfile(FONTS / "NotoSans-Latin1.otf", (self.source / "Latin1.otf"))
        self.write("art/fonts.css", '@font-face { font-family: "%s"; src: url(../Latin1.otf); }')
        before = '<?xml-stylesheet href="../art/fonts.css"?>'
        for family, said in (("Noto Sans", None),
                             ("Brand", 'Latin1.otf is of the family Noto Sans, so its '
                                       '@font-face rule must say font-family: "Noto Sans"')):
            with self.subTest(family):
                self.write("art/fonts.css", '@font-face { font-family: "%s"; '
                                            'src: url(../Latin1.otf); }' % family)
                self.photo(self.text(family, before))
                if said is None:
                    self.assertGreater(self.ink(), 20)
                else:
                    self.refused(said)

    def test_a_font_file_must_be_a_font_of_the_folder(self):
        # The file named is read: one that is not a font is refused.
        self.write("art/notes.otf", "not a font")
        for url, said in (("../../outside.otf", "is outside the source folder"),
                          ("notes.otf", "art/notes.otf is not a font file")):
            with self.subTest(url):
                self.write("art/fonts.css", '@font-face { font-family: "Noto Sans"; '
                                            'src: url(%s); }' % url)
                self.photo(self.text("Noto Sans", '<?xml-stylesheet href="../art/fonts.css"?>'))
                self.refused(said)

    def test_the_drawing_changes_with_any_file_it_reads(self):
        shutil.copyfile(FONTS / "NotoSans-Latin1.otf", (self.source / "Latin1.otf"))
        self.write("art/theme.css", '@font-face { font-family: "Noto Sans"; '
                                    'src: url(../Latin1.otf); }\n.a { fill: #000; }')
        Path(self.source / "art" / "dot.png").write_bytes(write_png(1, 1, bytes(4)))
        self.photo(svg('<image href="../art/dot.png" width="1" height="1"/>',
                       before='<?xml-stylesheet href="../art/theme.css"?>'))
        read = folder_reader(self.source), folder_byte_reader(self.source)
        first = prepared_svg_picture("pictures/photo.svg", *read, {})
        self.assertEqual(first.files, ("pictures/photo.svg", "art/theme.css", "art/dot.png",
                                       "Latin1.otf"))
        keys = {first.key}
        for change in (lambda: self.write("art/theme.css", read_text(
                           self.source / "art/theme.css") + "\n.b { fill: #fff; }"),
                       lambda: (self.source / "art" / "dot.png").write_bytes(
                           write_png(1, 1, bytes(3) + b"\xff")),
                       lambda: (self.source / "Latin1.otf").write_bytes(
                           (self.source / "Latin1.otf").read_bytes() + b"\0")):
            change()
            keys.add(prepared_svg_picture("pictures/photo.svg", *read, {}).key)
        self.assertEqual(len(keys), 4)


class ToolsTest(SvgTestCase):
    """Each tool that reads a picture of a source folder reads an SVG
    picture as the PNG picture drawn from it."""

    def setUp(self):
        super().setUp()
        self.photo(svg('<rect width="40" height="20" fill="#ff0000"/>'))

    def test_the_build_stores_the_png_drawn(self):
        # The same as building a folder whose picture is that PNG file.
        png = draw_svg_picture("pictures/photo.svg", folder_reader(self.source),
                               folder_byte_reader(self.source), {})
        from_svg = self.built("svg.HMI").blocks
        (self.source / "pictures" / "photo.svg").unlink()
        self.picture(".png", png)
        self.assertEqual(from_svg, self.built("png.HMI").blocks)

    def test_a_second_build_takes_the_drawn_picture_from_the_cache(self):
        cache = self.folder / "cache"
        with mock.patch.dict(os.environ, {"NXWRIGHT_CACHE": str(cache)}):
            first = self.built("first.HMI").blocks
            svg_pictures._drawn.clear()
            with mock.patch.object(svg_pictures, "_draw",
                                   side_effect=AssertionError("drawn again")):
                self.assertEqual(self.built("second.HMI").blocks, first)
        with mock.patch.dict(os.environ, {"NXWRIGHT_CACHE": "off"}):
            svg_pictures._drawn.clear()
            self.assertEqual(self.built("uncached.HMI").blocks, first)

    def test_the_checks_draw_it(self):
        self.assertEqual(self.findings(), [])
        self.photo(svg('<use href="../art/missing.svg#a"/>'))
        messages = [finding.message for finding in self.findings()]
        self.assertIn("pictures/photo.svg: art/missing.svg is missing", messages)
        with self.assertRaisesRegex(NxwrightError, "art/missing.svg is missing"):
            self.built()

    def test_the_preview_shows_the_png_drawn(self):
        drawing = Previews().drawing(self.source, "pages/page0.page.toml",
                                     folder_reader(self.source))
        shown = drawing["pictureFiles"]["photo"]
        self.assertTrue(shown["data"].startswith("data:image/png;base64,"))
        key = prepared_svg_picture("pictures/photo.svg", folder_reader(self.source),
                                   folder_byte_reader(self.source), {}).key
        self.assertEqual(shown["version"], key)

    def test_the_preview_shows_nothing_for_a_picture_that_cannot_be_drawn(self):
        # A path would let the webview's browser draw the SVG file itself.
        self.photo(svg('<use href="../art/missing.svg#a"/>'))
        drawing = Previews().drawing(self.source, "pages/page0.page.toml",
                                     folder_reader(self.source))
        self.assertEqual(drawing["pictureFiles"]["photo"], {"version": "0"})

    def shown_by(self, previews: Previews, defines: dict = None) -> dict:
        """Returns what `previews` lists for the picture "photo" in a drawing
        of page0, drawn with `defines`, or with app.toml's defines when
        `defines` is None."""
        app, components = read_page_components(folder_reader(self.source), "page0")
        if defines is not None:
            app = dict(app, defines=defines)
        return previews.drawing_of(self.source, app, components)["pictureFiles"]["photo"]

    def test_the_preview_keeps_the_picture_while_its_files_are_unchanged(self):
        self.write("art/parts.svg", svg('<rect id="a" width="40" height="20" fill="#00ff00"/>'))
        self.photo(svg('<use href="../art/parts.svg#a"/>'))
        previews = Previews()
        first = self.shown_by(previews)
        with mock.patch.object(preview, "prepared_svg_picture",
                               side_effect=AssertionError("prepared again")):
            self.assertEqual(self.shown_by(previews), first)
        # A new Previews has nothing kept, so it gives the right result. After a
        # change to the file the picture links to, to its own file, or to a
        # define it uses, `previews` must give the same.
        self.write("art/parts.svg", svg('<rect id="a" width="40" height="20" fill="#0000ff"/>'))
        second = self.shown_by(previews)
        self.assertNotEqual(second, first)
        self.assertEqual(second, self.shown_by(Previews()))
        self.photo(svg('<rect width="40" height="20" fill="var(--ACCENT)"/>'))
        for defines in ({"ACCENT": "#ff0000"}, {"ACCENT": "#00ffff"}):
            third = self.shown_by(previews, defines)
            self.assertNotEqual(third, second)
            self.assertEqual(third, self.shown_by(Previews(), defines))
            second = third

    def test_the_preview_draws_a_picture_once_its_missing_file_appears(self):
        self.photo(svg('<use href="../art/parts.svg#a"/>'))
        previews = Previews()
        self.assertEqual(self.shown_by(previews), {"version": "0"})
        with mock.patch.object(preview, "prepared_svg_picture",
                               side_effect=AssertionError("prepared again")):
            self.assertEqual(self.shown_by(previews), {"version": "0"})
        self.write("art/parts.svg", svg('<rect id="a" width="40" height="20" fill="#00ff00"/>'))
        self.assertEqual(self.shown_by(previews), self.shown_by(Previews()))
        self.assertIn("data", self.shown_by(previews))

    def test_a_simulation_shows_the_png_drawn(self):
        # The simulator's panel, and the test runner's pictures of the
        # screen, draw what simulation_drawing gives.
        simulation = Simulation(self.source)
        drawing = Previews().simulation_drawing(simulation, simulation.drawing_inputs())
        self.assertTrue(drawing["pictureFiles"]["photo"]["data"].startswith(
            "data:image/png;base64,"))

    def test_the_simulator_and_the_preview_read_its_size(self):
        app = parse_app(read_text(self.source / "app.toml"))
        self.assertEqual(FolderResources(self.source, app).picture_size(0), (40, 20))
        self.assertEqual(picture_file_size(self.source / "pictures" / "photo.svg"), (40, 20))

    def test_a_source_svg_file_is_not_a_source_file(self):
        self.picture(".source.svg", svg("").encode("utf-8"))
        self.assertEqual(self.findings(), [])
        self.assertNotIn("0.source.svg", str(self.built().blocks))

    def test_a_screen_copy_beside_it_is_not_used(self):
        reference = self.built("reference.HMI").blocks
        self.picture(".screen", b"not a screen copy")
        self.assertEqual(self.findings(), [])
        self.assertEqual(self.built().blocks, reference)

    def test_hovers_and_references_know_its_file(self):
        self.assertEqual(picture_of("pictures/photo.svg"), "photo")
        index = FolderIndex(self.source, lambda path: path.read_text(encoding="utf-8")
                            if path.is_file() else None)
        self.assertEqual(index.picture_path("photo"), "pictures/photo.svg")

    def test_picture_adds_an_svg_file_whose_shared_files_are_there(self):
        given = self.folder / "logo.svg"
        given.write_text(svg('<use href="../art/parts.svg#a"/>'), encoding="utf-8")
        with self.assertRaisesRegex(NxwrightError, "art/parts.svg is missing"):
            add_pictures(self.source, [given])
        self.assertFalse((self.source / "pictures" / "logo.svg").exists())
        self.write("art/parts.svg", '<svg xmlns="http://www.w3.org/2000/svg">'
                                    '<rect id="a" width="1" height="1"/></svg>')
        self.assertEqual(add_pictures(self.source, [given]), ["logo"])
        self.assertTrue((self.source / "pictures" / "logo.svg").is_file())

    def test_replace_takes_an_svg_file(self):
        (self.source / "pictures" / "photo.svg").unlink()
        self.picture(".png", write_png(4, 4, bytes(4 * 4 * 4)))
        given = self.folder / "new.svg"
        given.write_text(svg(""), encoding="utf-8")
        self.assertEqual(add_pictures(self.source, [given], replacing=Slot("photo")), ["photo"])
        self.assertTrue((self.source / "pictures" / "photo.svg").is_file())
        self.assertFalse((self.source / "pictures" / "photo.png").exists())
        self.assertEqual(self.findings(), [])

    def test_a_rename_leaves_the_paths_to_shared_files_as_they_are(self):
        # Moved into another folder, the picture's path to its shared file
        # leads nowhere: the checks say so, for you to fix.
        self.write("art/parts.svg", '<svg xmlns="http://www.w3.org/2000/svg">'
                                    '<rect id="a" width="1" height="1"/></svg>')
        self.photo(svg('<use href="../art/parts.svg#a"/>'))
        rename_resource(self.source, "picture", "photo", "icons/photo")
        self.assertIn('href="../art/parts.svg#a"',
                      read_text(self.source / "pictures" / "icons" / "photo.svg"))
        messages = [finding.message for finding in self.findings()]
        self.assertIn("pictures/icons/photo.svg: pictures/art/parts.svg is missing", messages)

    def test_a_picture_uses_the_drawing_of_another_picture(self):
        # As a page's pressed picture uses the drawing of its normal one.
        self.photo(svg('<style>.only-pressed { display: none; } '
                       '.pressed .only-pressed { display: inline; }</style>'
                       '<g id="drawing"><rect width="40" height="20" fill="#0000ff"/>'
                       '<rect class="only-pressed" width="10" height="10" fill="#ff0000"/></g>'))
        self.write("pictures/pressed.svg",
                   '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20" '
                   'class="pressed"><style>.only-pressed { display: none; } '
                   '.pressed .only-pressed { display: inline; }</style>'
                   '<use href="photo.svg#drawing"/></svg>')
        self.assertEqual(self.drawn().getpixel((5, 5)), (0, 0, 255, 255))
        self.assertEqual(self.drawn("pictures/pressed.svg").getpixel((5, 5)), (255, 0, 0, 255))


class DefinesTest(SvgTestCase):
    """app.toml's defines in SVG pictures: ACCENT, a colour, TITLE, a text,
    and SIZE, a number."""

    def setUp(self):
        super().setUp()
        self.edit_app(lambda app: app.update(defines={"ACCENT": "#ff0000", "TITLE": "Hi",
                                                      "SIZE": 14}))

    def colour(self) -> tuple:
        return self.drawn().getpixel((5, 5))

    def test_a_css_variable_in_each_place_takes_the_value(self):
        for variable in ("var(--ACCENT)", "var(--ACCENT, rgb(0, 255, 0))"):
            self.write("art/theme.css", ".a { fill: %s; }" % variable)
            for content, before in (
                    ('<style>.a { fill: %s; }</style><rect class="a" width="40" '
                     'height="20"/>' % variable, ""),
                    ('<rect class="a" width="40" height="20"/>',
                     '<?xml-stylesheet href="../art/theme.css"?>'),
                    ('<rect style="fill: %s" width="40" height="20"/>' % variable, ""),
                    ('<rect fill="%s" width="40" height="20"/>' % variable, "")):
                with self.subTest(content):
                    self.photo(svg(content, before=before))
                    self.assertEqual(self.colour(), (255, 0, 0, 255))
                    with overriding_defines({"ACCENT": "#0000ff"}):
                        self.assertEqual(self.colour(), (0, 0, 255, 255))

    def test_a_texts_text_takes_the_value(self):
        self.edit_app(lambda app: app["defines"].update(TITLE="A & <B>"))
        self.photo(svg('<text data-nxwright-text="TITLE" y="15">sample</text>'
                       '<text><tspan data-nxwright-text="SIZE">0</tspan></text>'))
        drawing = prepared_svg_picture("pictures/photo.svg", folder_reader(self.source),
                                       folder_byte_reader(self.source), self.defines())
        self.assertIn(">A &amp; &lt;B&gt;</text>", drawing.text)
        self.assertIn(">14</tspan>", drawing.text)
        self.assertNotIn("data-nxwright-text", drawing.text)

    def test_what_a_define_cannot_do(self):
        self.edit_app(lambda app: app["defines"].update(BAD="red; x: y", COMMENT="red /* x"))
        for content, said in (
                ('<rect fill="var(--card)"/>', "var(--card) does not name a define of app.toml"),
                ('<rect fill="var(--ACCENT"/>', "var(--ACCENT has no closing parenthesis"),
                ('<rect style="fill: var(--BAD)"/>', "the define BAD cannot be a style value"),
                ('<rect style="fill: var(--COMMENT)"/>',
                 "the define COMMENT cannot be a style value"),
                ('<text data-nxwright-text="NOPE">x</text>',
                 'data-nxwright-text="NOPE" does not name a define'),
                ('<text data-nxwright-text="TITLE">x<tspan>y</tspan></text>',
                 "contains other elements"),
                ('<rect data-nxwright-text="TITLE"/>', "Put it on a <text> or a <tspan>")):
            with self.subTest(content):
                self.photo(svg(content))
                self.refused(said)

    def test_the_check_warns_of_a_declared_value_that_differs(self):
        self.write("art/theme.css", ":root { --ACCENT: #00FF00; --SIZE: 14; --other: 1px; }")
        self.photo(svg('<rect fill="var(--ACCENT)" width="1" height="1"/>',
                       before='<?xml-stylesheet href="../art/theme.css"?>'))
        listed = folder_lister(self.source)
        found = check_folder(folder_reader(self.source),
                             lambda path: (self.source / path).is_file(), None,
                             folder_byte_reader(self.source), listed).folder_findings
        self.assertEqual([finding.message for finding in found],
                         ["pictures/photo.svg: art/theme.css declares --ACCENT: #00FF00 for "
                          "other SVG viewers, but the define's default is #ff0000, which "
                          "nxwright draws"])
        self.write("art/theme.css", ":root { --ACCENT: #FF0000; }")
        self.assertEqual(check_folder(folder_reader(self.source),
                                      lambda path: (self.source / path).is_file(), None,
                                      folder_byte_reader(self.source), listed).folder_findings,
                         [])
        # A value declared in a shared shape is the shared file's.
        self.write("art/parts.svg", '<svg xmlns="http://www.w3.org/2000/svg">'
                                    '<rect id="a" style="--ACCENT: blue" width="1" height="1"/>'
                                    '</svg>')
        self.photo(svg('<use href="../art/parts.svg#a"/>'))
        found = check_folder(folder_reader(self.source),
                             lambda path: (self.source / path).is_file(), None,
                             folder_byte_reader(self.source), listed).folder_findings
        self.assertIn("pictures/photo.svg: art/parts.svg declares --ACCENT: blue",
                      found[0].message)

    def test_one_colour_serves_a_component_and_a_picture(self):
        page = self.source / "pages" / "page0.page.toml"
        page.write_text(edited_page_file(page.read_text(encoding="utf-8"),
                                         lambda tables: tables[0].update(sta=1,
                                                                         bco="%ACCENT%")),
                        encoding="utf-8", newline="\n")
        self.photo(svg('<rect fill="var(--ACCENT)" width="40" height="20"/>'))
        with overriding_defines({"ACCENT": "#0000ff"}):
            project = self.built()
        record = parse_image_source(project.blocks["0.is"])
        stored = Image.open(io.BytesIO(record.data)).convert("RGBA")
        self.assertEqual(stored.getpixel((5, 5)), (0, 0, 255, 255))
        # The page's background has the same colour, as extracting shows it.
        extract(self.folder / "built.HMI", self.folder / "extracted")
        extracted = tomllib.loads((self.folder / "extracted" / "pages" / "page0.page.toml")
                                  .read_text(encoding="utf-8"))
        self.assertEqual(extracted["page"]["bco"], "#0000ff")

    def test_a_simulation_draws_with_its_launch_defines(self):
        self.photo(svg('<rect fill="var(--ACCENT)" width="40" height="20"/>'))
        with overriding_defines({"ACCENT": "#0000ff"}, LAUNCH_CONFIGURATION):
            simulation = Simulation(self.source)
        drawing = Previews().simulation_drawing(simulation, simulation.drawing_inputs())
        data = drawing["pictureFiles"]["photo"]["data"].split(",", 1)[1]
        picture = Image.open(io.BytesIO(base64.b64decode(data))).convert("RGBA")
        self.assertEqual(picture.getpixel((5, 5)), (0, 0, 255, 255))

    def test_a_refusal_in_a_shared_shape_names_its_file(self):
        self.write("art/parts.svg", '<svg xmlns="http://www.w3.org/2000/svg">'
                                    '<rect id="a" fill="var(--card)"/></svg>')
        self.photo(svg('<use href="../art/parts.svg#a"/>'))
        self.refused("art/parts.svg: var(--card) does not name a define of app.toml")


class PictureViewTest(SvgTestCase):
    """The language server's answer to the picture editor in VS Code
    (language_server/picture_view.py), from the files as open in the editor."""

    def setUp(self):
        super().setUp()
        self.write("art/theme.css", ".a { fill: #ff0000; }")
        self.photo(svg('<rect class="a" width="40" height="20"/>',
                       before='<?xml-stylesheet href="../art/theme.css"?>'))
        workspace = SimpleNamespace(text_documents={})
        self.texts = FileTexts(lambda: workspace)
        self.workspace = workspace

    def open(self, path: str, text: str):
        """Opens the folder's file `path` in the editor, with the unsaved `text`."""
        self.workspace.text_documents[uri_of(self.source / path)] = SimpleNamespace(source=text)

    def viewed(self) -> dict:
        return svg_picture_view(self.source / "pictures" / "photo.svg", self.texts)

    def colour(self, view: dict) -> tuple:
        data = base64.b64decode(view["picture"].split(",", 1)[1])
        return Image.open(io.BytesIO(data)).convert("RGBA").getpixel((5, 5))

    def test_the_picture_its_size_and_the_files_it_reads(self):
        view = self.viewed()
        self.assertEqual((view["width"], view["height"]), (40, 20))
        self.assertEqual(self.colour(view), (255, 0, 0, 255))
        self.assertEqual(view["files"], [str(self.source / "pictures" / "photo.svg"),
                                         str(self.source / "app.toml"),
                                         str(self.source / "art" / "theme.css")])

    def test_unsaved_text_of_the_picture_and_of_a_shared_file(self):
        self.open("art/theme.css", ".a { fill: #0000ff; }")
        self.assertEqual(self.colour(self.viewed()), (0, 0, 255, 255))
        self.open("pictures/photo.svg", svg('<rect width="40" height="20" fill="#00ff00"/>'))
        self.assertEqual(self.colour(self.viewed()), (0, 255, 0, 255))

    def test_a_picture_that_cannot_be_drawn_says_why(self):
        self.open("pictures/photo.svg", svg('<use href="../art/none.svg#a"/>'))
        view = self.viewed()
        self.assertEqual(view["error"], "pictures/photo.svg: art/none.svg is missing")
        self.assertNotIn("picture", view)
        # The missing file is among those watched, so the editor draws again
        # once it is made.
        self.assertIn(str(self.source / "art" / "none.svg"), view["files"])

    def test_a_picture_outside_a_source_folder(self):
        outside = self.folder / "loose.svg"
        outside.write_text(svg(""), encoding="utf-8")
        view = svg_picture_view(outside, self.texts)
        self.assertEqual(view["error"], "loose.svg is not in a source folder")

    def test_the_picture_takes_the_defaults_of_the_defines(self):
        self.edit_app(lambda app: app.update(defines={"ACCENT": "#0000ff"}))
        self.write("art/theme.css", ".a { fill: var(--ACCENT); }")
        self.assertEqual(self.colour(self.viewed()), (0, 0, 255, 255))
