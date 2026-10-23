"""The page preview's drawing: the shapes of a page, its texts placed in their
fonts, and the language server's nxwright/pageDrawing request."""
import base64
import json
import tempfile
import tomllib
from pathlib import Path
import unittest

from PIL import Image, ImageChops

from nxwright import NxwrightError
from nxwright.language_server.file_texts import uri_of
from nxwright.testing.preview import Previews
from nxwright.project.pictures import read_picture, write_png
from nxwright.project.screen_colours import rgb565_to_rgb
from nxwright.project.zi_font import decode_font
from nxwright.drawing.combo_box_drawing import items, list_layout
from nxwright.drawing.page_drawing import DrawingResources, draw_page
from nxwright.drawing.screen_pictures import paint_drawing
from nxwright.drawing.drawing_shared import NO_RESOURCE
from nxwright.language.resource_names import ResourceNames
from nxwright.project.component_defaults import DEFAULTS_FILE, defaults_from_toml
from nxwright.source.page_source import Component, page_components
from nxwright.source.source_folder import folder_reader
from nxwright.drawing.text_pictures import MissingCharacter, text_picture, text_size
from nxwright.testing.simulation import Simulation
from tests.language_server_connection import initialized
from tests.test_folder_check import FolderTestCase, fonts_first
from tests.test_zi_font import (chosen_characters_fixture, font_block, gb2312_font, grid_font,
                                pairs_glyph, utf8_fixture)

FONTS = Path(__file__).resolve().parent / "fixtures" / "fonts"
SANS20 = decode_font((FONTS / "Sans20.zi").read_bytes())
WHITE = (255, 255, 255)


class Resources(DrawingResources):
    """Two pictures, 800 by 480 and 64 by 64, and the font Sans20."""
    PICTURES = {0: ("background", (800, 480)), 1: ("logo", (64, 64))}

    def picture(self, picture_id):
        return self.PICTURES.get(picture_id, (None, None))[0]

    def picture_size(self, picture_id):
        return self.PICTURES.get(picture_id, (None, None))[1]

    def font(self, font_id):
        if font_id != 0:
            raise NxwrightError("the folder has no font %d" % font_id)
        return SANS20


def component(name: str, kind: str, **values) -> Component:
    return Component(name, kind, dict({"x": 10, "y": 20, "w": 100, "h": 30}, **values))


class DrawingTest(unittest.TestCase):

    def test_each_drawn_type(self):
        components = [
            Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "sta": 2, "pic": 0}),
            component("title", "text", sta=0, picc=0, font=0, pco=0xffff, txt="Hello", xcen=0,
                      ycen=0),
            component("ok", "button", sta=1, bco=0xf800, font=0, pco=0, txt="OK"),
            component("photo", "picture", pic=1),
            component("cut", "crop", picc=0),
            component("zone", "hotspot"),
            # A type the preview does not draw: outlined.
            component("dial", "unknown-type"),
            Component("tick", "timer", {"tim": 50}),
        ]
        drawing = draw_page(components, Resources())
        self.assertEqual((drawing["width"], drawing["height"], drawing["notes"]), (800, 480, []))
        self.assertEqual([(shape["component"], shape["kind"]) for shape in drawing["shapes"]], [
            ("page", "picture"), ("title", "picture"), ("title", "text"), ("ok", "colour"),
            ("ok", "text"), ("photo", "picture"), ("cut", "picture"), ("dial", "outline")])
        shapes = drawing["shapes"]
        # A crop picture shows the part of the picture under the component.
        self.assertEqual((shapes[1]["picture"], shapes[1]["sx"], shapes[1]["sy"]),
                         ("background", 10, 20))
        self.assertEqual((shapes[5]["picture"], shapes[5]["sx"]), ("logo", 0))
        self.assertEqual(shapes[3]["colour"], "#ff0000")
        self.assertEqual(shapes[7]["label"], "dial (unknown-type)")
        # A hotspot draws nothing, but is listed, so that a click selects it.
        self.assertNotIn("zone", [shape["component"] for shape in shapes])
        self.assertEqual([entry["name"] for entry in drawing["components"]],
                         ["page", "title", "ok", "photo", "cut", "zone", "dial"])

    def test_a_crop_shows_its_picture_from_its_offsets(self):
        # The Editor's simulator drew a crop's picture from vvs0 pixels right
        # of its x and vvs1 below its y, set by its page file or by code;
        # nothing where that passes the picture's edge.
        drawing = draw_page([component("cut", "crop", picc=0, vvs0=50, vvs1=30)], Resources())
        [shape] = drawing["shapes"]
        self.assertEqual((shape["picture"], shape["sx"], shape["sy"]), ("background", 60, 50))

    def test_each_components_scope_and_those_without_a_place(self):
        # The preview names each component in its scope's colours, and shows
        # those without a place in a strip under the page, in ID order.
        components = [
            Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "vscope": 1}),
            component("near", "hotspot"),
            Component("tick", "timer", {"tim": 50}),
            component("far", "hotspot", vscope=1),
            Component("count", "variable", {"vscope": 1}),
            Component("touch", "touch-capture", {}),
        ]
        drawing = draw_page(components, Resources(), hidden=["far"])
        self.assertEqual([(entry["name"], entry["global"]) for entry in drawing["components"]],
                         [("page", True), ("near", False)])
        self.assertEqual(drawing["unplaced"], [
            {"name": "tick", "type": "timer", "global": False},
            {"name": "count", "type": "variable", "global": True},
            {"name": "touch", "type": "touch-capture", "global": False}])
        drawing = draw_page(components, Resources())
        self.assertEqual(drawing["components"][2], {"name": "far", "type": "hotspot",
                                                    "global": True, "locked": False, "x": 10,
                                                    "y": 20, "w": 100, "h": 30})

    def test_a_locked_component(self):
        # The preview draws a padlock on it.
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})
        drawing = draw_page([page, component("held", "hotspot", lockobj=1),
                             component("free", "hotspot")], Resources())
        self.assertEqual([entry["locked"] for entry in drawing["components"]],
                         [False, True, False])

    def test_a_grouped_component(self):
        # The components sharing both groupid0 and groupid1, groupid0 not 0,
        # are one group, as the Editor's design view showed.
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})
        drawing = draw_page([page, component("a", "hotspot", groupid0=1),
                             component("b", "hotspot", groupid0=3, groupid1=4),
                             component("c", "hotspot", groupid0=0, groupid1=9),
                             component("d", "hotspot")], Resources())
        self.assertEqual([entry.get("group") for entry in drawing["components"]],
                         [None, "1/0", "3/4", None, None])

    def test_a_scrolling_texts_border_cuts_its_text_without_moving_it(self):
        # Its words are where the simulation moved them, in page pixels,
        # with a border or without; the border only cuts them.
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})

        # Moved, it is placed across its way by its size, which a
        # simulation measures.
        width, height = text_size("Hi", SANS20, Resources.encoding)

        def text_shape(style: int) -> tuple:
            moving = component("st", "scrolling-text", sta=1, bco=0, pco=0xffff, font=0,
                               txt="Hi", xcen=0, ycen=1, dir=1, style=style, borderw=4,
                               borderc=0xf800, vvs2=width, vvs3=height)
            drawing = draw_page([page, moving], Resources(), scrolled={"st": 40})
            shape = next(shape for shape in drawing["shapes"] if shape["kind"] == "text")
            image = read_picture(base64.b64decode(shape["image"].split(",")[1]))
            ink = min(shape["x"] + index % image.width
                      for index, pixel in enumerate(image.get_flattened_data()) if pixel[3])
            return ink, (shape["x"], shape["w"])
        plain, bordered = text_shape(0), text_shape(1)
        self.assertEqual(bordered[0], plain[0])
        self.assertEqual((plain[1], bordered[1]), ((10, 100), (14, 92)))

    def test_a_component_drawn_again_looks_as_drawn_once(self):
        # The Editor's simulator showed a rounded progress bar whose val code
        # set four times alike as it first drew it, to the pixel, and a text
        # without background whose txt code shortened showing its new words
        # alone, over the component under it. So drawn again, a component's
        # earlier drawing goes: smoothed edges and glyphs are not blended
        # twice. (A drawing is made from the values the code left, so a
        # shortened text's old words are never in it.)
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "sta": 1,
                                          "bco": 0x8410})
        under = component("under", "text", sta=1, bco=0xf800, txt="")
        bar = component("bar", "progress-bar", y=80, sta=0, bco=0xc618, pco=0x0400, val=30,
                        dis=50, dez=0)
        text = component("t", "text", sta=3, font=0, pco=0, txt="Hi", xcen=0, ycen=1)
        components = [page, under, bar, text]
        once = paint_drawing(draw_page(components, Resources()))
        again = draw_page(components, Resources(),
                          [("redraw", "bar"), ("redraw", "t"), ("redraw", "bar"), ("redraw", "t")])
        self.assertEqual(differing_pixels(paint_drawing(again), once, page.values, 0), [])
        # The redrawn are drawn last, over what came before them: the text
        # last, after the one under it, which it meets, in ID order.
        self.assertEqual([shape["component"] for shape in again["shapes"]][-2:], ["under", "t"])

    def test_a_border_as_wide_as_its_component(self):
        # The border covers the component, its text with it: nothing more
        # is drawn, and nothing is noted.
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})
        text = component("t", "text", sta=1, bco=0, pco=0xffff, font=0, txt="Hi", style=1,
                         borderw=30, borderc=0xf800)
        drawing = draw_page([page, text], Resources())
        self.assertEqual(drawing["notes"], [])
        self.assertNotIn("text", [shape["kind"] for shape in drawing["shapes"]])
        # The border is as wide as half the component's height, 15 of its 30:
        # its top and bottom, after the background.
        self.assertEqual([shape["h"] for shape in drawing["shapes"][1:3]], [15, 15])

    def test_pictures_on_a_screen_that_keeps_no_alpha(self):
        # The Editor's simulator showed a picture's transparent share white on
        # an Enhanced screen, and the page through it on an Intelligent one:
        # the webview flattens the folder's pictures marked opaque.
        class OpaqueResources(Resources):
            opaque_pictures = True
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "sta": 2, "pic": 0})
        photo = component("photo", "picture", pic=1)
        for resources, opaque in ((Resources(), []), (OpaqueResources(), [True, True])):
            with self.subTest(opaque=opaque):
                shapes = draw_page([page, photo], resources)["shapes"]
                self.assertEqual([shape["opaque"] for shape in shapes if "opaque" in shape], opaque)

    def test_no_border_on_a_picture_or_transparent(self):
        # The Editor's simulator drew a keypad's buttons of style 1 on
        # pictures without their border, and a text and a file browser of
        # style 1 without background (`sta` 3) without theirs.
        for sta, kinds in ((1, ["colour", "colour", "colour", "colour", "colour"]),
                           (2, ["picture"]), (3, [])):
            with self.subTest(sta=sta):
                page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})
                key = component("key", "button", sta=sta, bco=0, pic=1, style=1, borderw=1,
                                borderc=0x1D9F, txt="")
                shapes = draw_page([page, key], Resources())["shapes"]
                self.assertEqual([shape["kind"] for shape in shapes], kinds)

    def test_a_page_without_background(self):
        # `sta` 0 paints nothing of its own: the page is drawn over what the
        # screen showed before. So does `sta` 2, a picture, with none set, or
        # one the folder does not have.
        for sta, pic, transparent, shapes in ((0, 0, True, []), (1, 0, False, ["colour"]),
                                              (2, 0, False, ["picture"]),
                                              (2, NO_RESOURCE, True, []), (2, 99, True, [])):
            with self.subTest(sta=sta, pic=pic):
                page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "sta": sta,
                                                  "bco": 0, "pic": pic})
                drawing = draw_page([page], Resources())
                self.assertEqual(drawing["transparent"], transparent)
                self.assertEqual([shape["kind"] for shape in drawing["shapes"]], shapes)

    def shapes(self, *components) -> list:
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})
        return [{key: value for key, value in shape.items() if key != "component"}
                for shape in draw_page([page, *components], Resources())["shapes"]]

    def test_a_slider_as_the_editors(self):
        # The demo's brightness slider, whose knob the Editor showed from x 260.
        slider = Component("brightness", "slider", {
            "x": 64, "y": 281, "w": 280, "h": 40, "sta": 0, "psta": 1, "wid": 28, "hig": 28,
            "picc": 0, "picc1": 0, "pic2": 1, "val": 80, "minval": 10, "maxval": 100})
        track, filled, knob = self.shapes(slider)
        self.assertEqual(track, {"kind": "picture", "x": 64, "y": 281, "w": 280, "h": 40,
                                 "picture": "background", "sx": 64, "sy": 281})
        self.assertEqual((filled["x"], filled["w"], filled["sx"]), (64, 196 + 14, 64))
        self.assertEqual(knob, {"kind": "picture", "x": 260, "y": 287, "w": 28, "h": 28,
                                "picture": "logo", "sx": 0, "sy": 0})

    def test_a_slider_knob_where_a_press_kept_it(self):
        # The knob's start a press kept (Simulation.scrolled), from the
        # track's start, or its bottom when upright, takes the place of the
        # one `val` gives, and the filled part ends under its middle, as the
        # Nextion Editor's simulator drew a slider pressed. One that no
        # longer fits the track is clamped to it.
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})
        across = {"x": 10, "y": 20, "w": 400, "h": 40, "sta": 0, "psta": 1, "wid": 28,
                  "hig": 28, "picc": 0, "picc1": 0, "pic2": 1, "val": 50, "minval": 0,
                  "maxval": 100}

        def drawn(values: dict, start: int) -> list:
            return [shape for shape in draw_page([page, Component("s", "slider", values)],
                                                 Resources(), scrolled={"s": start})["shapes"]
                    if shape["component"] == "s"]

        _, filled, knob = drawn(across, 71)
        self.assertEqual((knob["x"], knob["y"], filled["w"]), (81, 26, 71 + 14))
        self.assertEqual(drawn(across, 500)[-1]["x"], 10 + 400 - 28)
        upright = dict(across, x=600, w=40, h=400, mode=1)
        self.assertEqual(drawn(upright, 300)[-1]["y"], 20 + 400 - 300 - 28)

    def test_a_waveform(self):
        wave = Component("w", "waveform", {"x": 10, "y": 10, "w": 100, "h": 50, "sta": 1,
                                           "bco": 0, "gdc": 0xffff, "gdw": 40, "gdh": 20})
        shapes = self.shapes(wave)
        # Lines up and down from the left edge, and across from the bottom
        # row up, as the Editor's simulator drew them (EditorAssumptionsTest).
        self.assertEqual([(shape["x"], shape["y"], shape["w"], shape["h"]) for shape in shapes],
                         [(10, 10, 100, 50), (10, 10, 1, 50), (50, 10, 1, 50), (90, 10, 1, 50),
                          (10, 59, 100, 1), (10, 39, 100, 1), (10, 19, 100, 1)])
        self.assertEqual(shapes[1]["colour"], "#ffffff")
        # The demo's chart: no grid.
        self.assertEqual(len(self.shapes(Component("w", "waveform", dict(wave.values, gdw=0,
                                                                         gdh=0)))), 1)

    def test_a_waveform_draws_its_first_ch_channels(self):
        # Given points on its four channels, a waveform of ch 2 drew channels
        # 0 and 1 alone in the Editor's simulator.
        page = Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50})
        wave = Component("w", "waveform", {"x": 10, "y": 10, "w": 4, "h": 20, "sta": 1, "bco": 0,
                                           "gdw": 0, "gdh": 0, "ch": 2, "pco0": 0xf800,
                                           "pco1": 0x07e0, "pco2": 0x001f, "pco3": 0xffff})
        four = draw_page([page, wave], Resources(),
                         waves={"w": {channel: [channel * 3] for channel in range(4)}})
        two = draw_page([page, wave], Resources(), waves={"w": {0: [0], 1: [3]}})
        self.assertEqual(len(four["shapes"]), 3)
        self.assertEqual(four["shapes"], two["shapes"])

    def test_a_waveforms_points(self):
        # dir 1: a new point enters at the right.
        wave = Component("w", "waveform", {"x": 10, "y": 10, "w": 4, "h": 20, "sta": 1, "bco": 0,
                                           "gdw": 0, "gdh": 0, "pco0": 0xf800, "dis": 100,
                                           "dir": 1})
        drawing = draw_page([Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50}), wave],
                            Resources(), waves={"w": {0: [0, 2, 2, 99]}})
        points = drawing["shapes"][-1]
        image = read_picture(base64.b64decode(points["image"].split(",")[1]))
        ink = {(points["x"] + index % image.width, points["y"] + index // image.width)
               for index, pixel in enumerate(image.get_flattened_data()) if pixel[3]}
        # From the bottom row, 29, a pixel per unit, each joined in its own
        # column to the one before; 99 is past the top, 10.
        self.assertEqual(ink, {(10, 29), (11, 29), (11, 28), (11, 27), (12, 27)} |
                         {(13, row) for row in range(10, 28)})
        self.assertEqual({pixel[:3] for pixel in image.get_flattened_data() if pixel[3]},
                         {(255, 0, 0)})
        # dir 0, the default: at the left, so the oldest point is at the right.
        wave.values["dir"] = 0
        drawing = draw_page([Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50}), wave],
                            Resources(), waves={"w": {0: [0, 2, 2, 99]}})
        points = drawing["shapes"][-1]
        image = read_picture(base64.b64decode(points["image"].split(",")[1]))
        ink = {(points["x"] + index % image.width, points["y"] + index // image.width)
               for index, pixel in enumerate(image.get_flattened_data()) if pixel[3]}
        self.assertEqual(ink, {(10, 10)} | {(11, row) for row in range(10, 28)} | {(12, 27)} |
                         {(13, 27), (13, 28), (13, 29)})

    def test_a_button_held_down(self):
        button = component("b", "button", sta=1, bco=0x001f, bco2=0xf800, font=0, txt="")
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})
        held = draw_page([page, button], Resources(), pressed="b")["shapes"]
        released = draw_page([page, button], Resources())["shapes"]
        self.assertEqual((held[0]["colour"], released[0]["colour"]), ("#ff0000", "#0000ff"))

    def test_a_border(self):
        text = component("t", "text", sta=1, bco=0xffff, style=1, borderw=3, borderc=0)
        shapes = self.shapes(text)
        self.assertEqual([(shape["x"], shape["y"], shape["w"], shape["h"]) for shape in shapes[1:]],
                         [(10, 20, 100, 3), (10, 47, 100, 3), (10, 23, 3, 24), (107, 23, 3, 24)])
        # Style 0, the default of texts, has none.
        self.assertEqual(len(self.shapes(component("t", "text", sta=1, bco=0xffff,
                                                   borderw=3))), 1)

    def test_given_values_are_drawn(self):
        # As a simulation would give them, in place of the page file's.
        first, second = (draw_page([Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50}),
                                    component("t", "text", font=0, txt=text)], Resources())
                         for text in ("one", "two"))
        self.assertNotEqual(first["shapes"][-1]["image"], second["shapes"][-1]["image"])

    def test_a_text_picture_in_place(self):
        drawing = draw_page([Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50}),
                             component("t", "text", font=0, txt="!", pco=0xffff, xcen=0, ycen=0)],
                            Resources())
        image = read_picture(base64.b64decode(drawing["shapes"][-1]["image"].split(",")[1]))
        self.assertEqual((image.width, image.height), (100, 30))
        self.assertEqual(image.getpixel((1, 6)), (255, 255, 255, (5 * 255 + 3) // 7))

    def test_a_picture_not_in_the_folder(self):
        # A page without its picture has no background, but the note says why.
        drawing = draw_page([Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50,
                                                        "sta": 2, "pic": 9})], Resources())
        self.assertEqual((drawing["transparent"], drawing["shapes"]), (True, []))
        self.assertIn("pic 9 is not a picture of the folder", drawing["notes"][0])
        # A component's is outlined.
        drawing = draw_page([Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50}),
                             component("p", "picture", pic=9)], Resources())
        self.assertEqual(drawing["shapes"][0]["kind"], "outline")
        self.assertIn("pic 9 is not a picture of the folder", drawing["notes"][0])

    def test_a_font_that_cannot_be_drawn(self):
        drawing = draw_page([Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50}),
                             component("t", "text", font=3, txt="Hi", pco=0x001f)], Resources())
        shape = drawing["shapes"][-1]
        self.assertEqual((shape["kind"], shape["text"], shape["colour"], shape["size"]),
                         ("plainText", "Hi", "#0000ff", 30))
        self.assertIn("t: drawn in an ordinary font: font 3: the folder has no font 3",
                      drawing["notes"])

    def test_texts_too_large_or_empty(self):
        for width, height in ((0, 30), (65535, 65535)):
            with self.subTest(width=width, height=height):
                page = Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50})
                drawing = draw_page([page, component("t", "text", font=0, txt="Hi", w=width,
                                                     h=height)], Resources())
                self.assertEqual([shape["kind"] for shape in drawing["shapes"]], [])
                self.assertIn("is too large or empty", drawing["notes"][0])

    def test_a_font_in_another_encoding(self):
        resources = Resources()
        resources.encoding = "ascii"
        drawing = draw_page([Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50}),
                             component("t", "text", font=0, txt="Hi")], resources)
        self.assertEqual(drawing["shapes"][-1]["kind"], "text")
        self.assertEqual(drawing["notes"], ["t: font Sans20 is in iso-8859-1, the project in ascii"])

    def test_a_character_the_font_lacks(self):
        # Drawn as the screen draws it, the table's first character, and
        # named in a note.
        drawing = draw_page([Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50}),
                             component("t", "text", font=0, txt="a\tb")], Resources())
        self.assertEqual(drawing["shapes"][-1]["kind"], "text")
        self.assertEqual(drawing["notes"],
                         ["t: font Sans20 lacks character 9; the screen draws its first "
                          "character, the space, in its place"])
        # So too in a select's lines, each drawn on its own.
        drawing = draw_page([Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50}),
                             component("s", "select", font=0, path="a\tb\r\nc\td")],
                            Resources())
        self.assertEqual(drawing["notes"],
                         ["s: font Sans20 lacks character 9; the screen draws its first "
                          "character, the space, in its place"])


class PaintedTest(unittest.TestCase):
    """What drawing commands painted, drawn over the page."""
    PAGE = Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50, "sta": 1, "bco": 0})
    TEXT = component("t", "text", sta=1, bco=0xffff, font=0, txt="")

    def shapes(self, painted, components=None) -> list:
        drawing = draw_page(components or [self.PAGE], Resources(), painted)
        return drawing["shapes"]

    def ink(self, shape) -> set:
        image = read_picture(base64.b64decode(shape["image"].split(",")[1]))
        return {(shape["x"] + index % image.width, shape["y"] + index // image.width)
                for index, pixel in enumerate(image.get_flattened_data()) if pixel[3]}

    def test_rectangles(self):
        shapes = self.shapes([("cls", 0xf800), ("fill", 1, 2, 3, 4, 0x001f),
                              ("draw", 5, 5, 2, 3, 0)])
        self.assertEqual([(shape["x"], shape["y"], shape["w"], shape["h"], shape["colour"])
                          for shape in shapes[1:]],
                         [(0, 0, 100, 50, "#ff0000"), (1, 2, 3, 4, "#0000ff"),
                          (2, 3, 4, 1, "#000000"), (2, 5, 4, 1, "#000000"),
                          (2, 3, 1, 3, "#000000"), (5, 3, 1, 3, "#000000")])

    def test_lines_and_circles_pixel_by_pixel(self):
        # Two thirds of the way down at x = 2, cut toward zero: row 0.
        line, = self.shapes([("line", 0, 0, 3, 1, 0xffff)])[1:]
        self.assertEqual(self.ink(line), {(0, 0), (1, 0), (2, 0), (3, 1)})
        circle, = self.shapes([("cir", 10, 10, 2, 0)])[1:]
        self.assertEqual(self.ink(circle), {
            (8, 9), (8, 10), (8, 11), (12, 9), (12, 10), (12, 11), (9, 8), (10, 8), (11, 8),
            (9, 12), (10, 12), (11, 12)})
        disc, = self.shapes([("cirs", 10, 10, 2, 0)])[1:]
        self.assertEqual(len(self.ink(disc)), 21)
        self.assertIn((10, 10), self.ink(disc))

    def test_a_lines_steps_as_the_editors(self):
        # At each step from its start, the other coordinate moves by the
        # largest whole number below the next step's share of the way, as the
        # Editor's simulator drew every line probed (fixtures/drawing-
        # assumptions/, page9 and page11). Along 190 steps of 37, the 5th
        # step's share is 0.97, a row down, and the 3rd's 0.58, none.
        line, = self.shapes([("line", 0, 0, 190, 37, 0xffff)])[1:]
        self.assertLessEqual({(3, 0), (5, 1), (10, 2), (13, 2)}, self.ink(line))
        self.assertFalse({(5, 0), (10, 1)} & self.ink(line))
        # Up and down: along 40 steps of 7, the 5th step's share is 0.875.
        line, = self.shapes([("line", 0, 0, 7, 40, 0xffff)])[1:]
        self.assertIn((1, 5), self.ink(line))
        # Shares of a half stay, whichever way the line is drawn.
        line, = self.shapes([("line", 0, 0, 4, 2, 0xffff)])[1:]
        self.assertEqual(self.ink(line), {(0, 0), (1, 0), (2, 1), (3, 1), (4, 2)})
        line, = self.shapes([("line", 4, 2, 0, 0, 0xffff)])[1:]
        self.assertEqual(self.ink(line), {(4, 2), (3, 2), (2, 1), (1, 1), (0, 0)})

    def test_huge_lines_and_circles_are_cut_to_the_page(self):
        line, = self.shapes([("line", 0, 0, 2_000_000_000, 0, 0)])[1:]
        self.assertEqual((line["x"], line["w"], line["h"]), (0, 100, 1))
        disc, = self.shapes([("cirs", 50, 25, 2_000_000_000, 0)])[1:]
        self.assertEqual((disc["w"], disc["h"]), (100, 50))

    def test_pictures(self):
        shapes = self.shapes([("pic", 3, 4, 1), ("picq", 5, 6, 7, 8, 0),
                              ("xpic", 1, 2, 3, 4, 50, 60, 0), ("pic", 0, 0, 9)])
        self.assertEqual([(shape["picture"], shape["x"], shape["y"], shape["w"], shape["h"],
                           shape["sx"], shape["sy"]) for shape in shapes[1:]],
                         [("logo", 3, 4, 64, 64, 0, 0), ("background", 5, 6, 7, 8, 5, 6),
                          ("background", 1, 2, 3, 4, 50, 60)])

    def test_xstr(self):
        drawing = draw_page([self.PAGE], Resources(),
                            [("xstr", 0, 0, 20, 20, 0, 0xffff, 0x001f, 0, 0, 1, "!")])
        background, text = drawing["shapes"][1:]
        self.assertEqual((background["colour"], text["kind"]), ("#0000ff", "text"))
        self.assertEqual(min(y for _, y in self.ink(text)), 5)
        self.assertEqual(drawing["notes"], [])
        # A character the font lacks is drawn as the screen draws it, and named.
        drawing = draw_page([self.PAGE], Resources(),
                            [("xstr", 0, 0, 20, 20, 0, 0xffff, 0x001f, 0, 0, 1, "a\tb")])
        self.assertEqual(drawing["shapes"][-1]["kind"], "text")
        self.assertEqual(drawing["notes"],
                         ["page: xstr 'a\\tb': font Sans20 lacks character 9; the screen draws "
                          "its first character, the space, in its place"])

    def test_components_drawn_again(self):
        # Drawn again, a component's earlier drawing goes. The page's
        # background comes back in its box, and it is drawn over that and
        # over what was painted since: here the fill, the page's command.
        components = [self.PAGE, self.TEXT]
        for painted, drawn in (
                ([("fill", 0, 0, 9, 9, 0), ("redraw", "t")], ["page", "page", "t"]),
                ([("ref", "1")], ["page", "t"]),
                ([("ref_stop",), ("redraw", "t"), ("fill", 0, 0, 9, 9, 0), ("ref_star",)],
                 ["page", "page", "t"]),
                # The page drawn again: its background over everything, then
                # the text, its earlier drawing gone.
                ([("redraw", "page")], ["page", "t"]),
                ([("redraw", "gone")], ["t"])):
            with self.subTest(painted=painted):
                shapes = draw_page(components, Resources(), painted)["shapes"]
                self.assertEqual([shape["component"] for shape in shapes[1:]], drawn)
                if painted[-1] == ("ref_star",):
                    # The text waited until ref_star: it is drawn last.
                    self.assertEqual(shapes[-1]["component"], "t")

    def test_drawn_again_with_the_page_under_it_and_those_it_meets(self):
        # As the Editor's simulator drew texts drawn again over a fill
        # (fixtures/drawing-assumptions/, page31 to page33, page36, and
        # page38). The page's background comes back in the box of the one
        # drawn again, and of each component linked to it by overlaps. Then
        # those are drawn again whole, in ID order. A moved component's old
        # place is uncovered alike. A component linked to neither keeps the
        # fill over it.
        def page(sta: int) -> Component:
            return Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50, "sta": sta,
                                              "bco": 0})
        a = component("a", "text", x=0, y=0, w=20, h=20, sta=1, bco=0xffff, font=0, txt="")
        b = component("b", "text", x=10, y=10, w=20, h=20, sta=1, bco=0xf800, font=0, txt="")
        c = component("c", "text", x=60, y=0, w=20, h=20, sta=1, bco=0x001f, font=0, txt="")
        # 90 wide, to be told from the page's own background.
        fill = ("fill", 0, 0, 90, 50, 0x07e0)
        for sta, painted, drawn in (
                (1, [fill, ("redraw", "b")],
                 [("page", 10, 10, 20, 20), ("page", 0, 0, 20, 20), ("a", 0, 0, 20, 20),
                  ("b", 10, 10, 20, 20)]),
                # c moved from (5, 25), where it met b, which meets a: both
                # are drawn again (assumed for a moved component's old place).
                (1, [fill, ("left", "c", (5, 25, 20, 20)), ("redraw", "c")],
                 [("page", 5, 25, 20, 20), ("page", 0, 0, 20, 20), ("page", 10, 10, 20, 20),
                  ("a", 0, 0, 20, 20), ("b", 10, 10, 20, 20), ("page", 60, 0, 20, 20),
                  ("c", 60, 0, 20, 20)]),
                # A page of no background brings back, in those boxes, the
                # screen as it found the page (page35).
                (0, [fill, ("redraw", "b")],
                 [("page", 10, 10, 20, 20), ("page", 0, 0, 20, 20), ("a", 0, 0, 20, 20),
                  ("b", 10, 10, 20, 20)])):
            with self.subTest(sta=sta, painted=painted):
                shapes = draw_page([page(sta), a, b, c], Resources(), painted)["shapes"]
                after = next(index for index, shape in enumerate(shapes) if shape["w"] == 90)
                self.assertEqual([(shape["component"], shape["x"], shape["y"], shape["w"],
                                   shape["h"]) for shape in shapes[after + 1:]], drawn)
                # The page's shapes are its background, or the screen it was
                # drawn over, which the panel keeps.
                self.assertEqual({shape["kind"] for shape in shapes[after + 1:]
                                  if shape["component"] == "page"},
                                 {"colour"} if sta else {"backdrop"})


class EditorPaintingTest(unittest.TestCase):
    """What drawing commands painted on a page of light gray, against the
    Editor's simulator showing it, fixtures/drawing/editor.png, cropped to
    the screen: a fill, a rectangle's outline, and a line.
    The screenshot's circles, whose edges the Editor's simulator smooths, its
    text, in a font the fixtures lack, and its buttons, of a 3D style, are
    left out."""
    SCREENSHOT = Path(__file__).resolve().parent / "fixtures" / "drawing" / "editor.png"
    PAINTED = [("fill", 10, 10, 300, 100, 63488), ("line", 0, 150, 300, 250, 31),
               ("draw", 320, 10, 420, 110, 2016)]
    AREAS = [(10, 10, 300, 100), (0, 140, 320, 120), (320, 10, 101, 101)]

    def test_as_the_editor_paints(self):
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "sta": 1,
                                          "bco": 0xe71c})
        drawing = draw_page([page], Resources(), self.PAINTED)
        drawn = {}
        for shape in drawing["shapes"]:
            if shape["kind"] == "colour":
                colour = tuple(int(shape["colour"][index:index + 2], 16) for index in (1, 3, 5))
                for y in range(shape["y"], shape["y"] + shape["h"]):
                    for x in range(shape["x"], shape["x"] + shape["w"]):
                        drawn[(x, y)] = colour
            else:
                image = read_picture(base64.b64decode(shape["image"].split(",")[1]))
                for index, pixel in enumerate(image.get_flattened_data()):
                    if pixel[3]:
                        drawn[(shape["x"] + index % image.width,
                               shape["y"] + index // image.width)] = pixel[:3]
        screenshot = read_picture(self.SCREENSHOT.read_bytes())
        differing = []
        for left, top, width, height in self.AREAS:
            for y in range(top, top + height):
                for x in range(left, left + width):
                    shown = screenshot.getpixel((x, y))
                    if max(abs(a - b) for a, b in zip(drawn[(x, y)], shown[:3])) > 12:
                        differing.append((x, y))
        self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


class EditorStylesTest(unittest.TestCase):
    """Texts and buttons of each style, fixtures/styles/styles.toml, against
    the Editor's simulator showing them, each screenshot cropped to the
    screen: on a light gray page, light.png, and on a green one, green.png;
    and with buttons 0, 2, 3, and 4 held down, pressed0.png and so on. Each
    component's two outer rows and columns are compared, where its edges
    are, its text left out. The two components on pictures, in green.png
    alone, are left out too: they show no edges."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "styles"
    LIGHT_GRAY, GREEN = 0xE71C, 0x2408
    SCREENSHOTS = (("light.png", LIGHT_GRAY, None), ("green.png", GREEN, None),
                   ("pressed0.png", LIGHT_GRAY, "button0"), ("pressed2.png", LIGHT_GRAY, "button2"),
                   ("pressed3.png", LIGHT_GRAY, "button3"), ("pressed4.png", LIGHT_GRAY, "button4"))

    def components(self, page_colour: int) -> list:
        data = tomllib.loads((self.FOLDER / "styles.toml").read_text(encoding="utf-8"))
        made = [Component("styles", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "sta": 1,
                                             "bco": page_colour})]
        for table in data["component"]:
            if table["sta"] != 1:
                continue
            values = {key: _rgb565(value) if str(value).startswith("#") else value
                      for key, value in table.items() if key not in ("name", "type")}
            values.update(txt="", font=0, borderw=values.get("borderw", 2))
            made.append(Component(table["name"], table["type"], values))
        return made

    def test_as_the_editor_draws_them(self):
        for name, page_colour, pressed in self.SCREENSHOTS:
            with self.subTest(screenshot=name):
                components = self.components(page_colour)
                drawn = paint_drawing(draw_page(components, Resources(), pressed=pressed))
                screenshot = read_picture((self.FOLDER / name).read_bytes())
                differing = []
                for component in components[1:]:
                    x0, y0, w, h = (component.values[key] for key in ("x", "y", "w", "h"))
                    # Its edges are its top two rows, its bottom two rows,
                    # and the two columns at each side. A pixel where two of
                    # them meet counts once.
                    strips = [(x0, y0, w, 2), (x0, y0 + h - 2, w, 2), (x0, y0, 2, h),
                              (x0 + w - 2, y0, 2, h)]
                    edges = {pixel for x, y, width, height in strips for pixel in differing_pixels(
                        drawn, screenshot, {"x": x, "y": y, "w": width, "h": height}, 6)}
                    differing += [(component.name, x, y) for x, y in sorted(edges)]
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


class EditorProgressTest(unittest.TestCase):
    """Progress bars, fixtures/progress/bars.toml, against the Editor's
    simulator showing them, editor.png, cropped to the screen: across and
    down, at several values, not rounded and rounded, and with striped
    pictures. The Editor smooths the edges of rounded bars, and its corners
    are not symmetric; the drawing smooths them alike on every corner. So a
    rounded bar's pixels match exactly where the screenshot shows the bar's
    or the page's own colours, and its edge's blends are near."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "progress"
    PICTURES = ["backAcross", "fillAcross", "backDown", "fillDown"]
    PAGE = 0xE71C

    def components(self) -> list:
        data = tomllib.loads((self.FOLDER / "bars.toml").read_text(encoding="utf-8"))
        made = [Component("bars", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "sta": 1,
                                           "bco": self.PAGE})]
        for table in data["component"]:
            if table["type"] not in ("progress-bar", "external-picture"):
                continue
            values = {}
            for key, value in table.items():
                if key in ("bpic", "ppic"):
                    values[key] = self.PICTURES.index(value)
                elif str(value).startswith("#"):
                    values[key] = _rgb565(value)
                elif key not in ("name", "type"):
                    values[key] = value
            made.append(Component(table["name"], table["type"], values))
        return made

    def painted(self, drawing: dict) -> Image.Image:
        """Paints the drawing's shapes over the page, as the webview does,
        its pictures the fixture's files."""
        drawing["pictureFiles"] = {name: {"path": str(self.FOLDER / ("%s.png" % name))}
                                   for name in self.PICTURES}
        return paint_drawing(drawing)

    def test_as_the_editor_draws_them(self):
        components = self.components()
        resources = Resources()
        resources.picture = lambda picture_id: (self.PICTURES[picture_id]
                                                if 0 <= picture_id < 4 else None)
        resources.picture_size = lambda picture_id: (1, 1) if 0 <= picture_id < 4 else None
        drawing = draw_page(components, resources)
        drawn = self.painted(drawing)
        screenshot = read_picture((self.FOLDER / "editor.png").read_bytes())
        for component in components[1:]:
            if component.type != "progress-bar":
                continue
            values = component.values
            with self.subTest(bar=component.name):
                differing = []
                # The rule passes every pixel within 6, on a bar's edge or not.
                for x, y in differing_pixels(drawn, screenshot, values, 6):
                    difference = max(abs(a - b) for a, b in zip(drawn.getpixel((x, y)),
                                                                screenshot.getpixel((x, y))[:3]))
                    edge = _on_rounded_bar_edge(values, x, y)
                    if difference > (BAR_SMOOTHING if edge else 6):
                        differing.append((x, y, difference))
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))

    def test_external_pictures_draw_nothing(self):
        # The Editor's simulator showed the page through them, their file missing.
        shapes = draw_page(self.components(), Resources())["shapes"]
        self.assertEqual([shape for shape in shapes
                          if shape["component"] in ("noPath", "missing")], [])


class EditorSliderTest(unittest.TestCase):
    """Sliders with a colour track and a colour knob, fixtures/slider/
    sliders.toml, against the Editor's simulator showing them, editor.png,
    cropped to the screen: along each row, the value, the rounding `dis`,
    the track's breadth `ch`, the knob's size `wid` and `hig`; down the
    side, two vertical sliders; and a square knob. Where both show one of
    the page's, the track's, the fill's, or the knob's own colour, it is the
    same one. The Editor smooths the round knob's and the rounded track's
    edges, and its knobs are not quite round: the drawing comes within 64
    of its edges."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "slider"
    DEFAULTS = {"sta": 1, "psta": 0, "wid": 255, "hig": 255, "dis": 100, "ch": 25, "mode": 0,
                "minval": 0, "maxval": 100}
    PURE = [(230, 226, 230), (66, 97, 255), (255, 65, 0), (33, 130, 33)]

    def test_as_the_editor_draws_them(self):
        data = tomllib.loads((self.FOLDER / "sliders.toml").read_text(encoding="utf-8"))
        components = [Component("sliders", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "sta": 1,
                                                     "bco": 0xE71C})]
        for table in data["component"]:
            values = dict(self.DEFAULTS)
            values.update({key: _rgb565(value) if str(value).startswith("#") else value
                           for key, value in table.items() if key not in ("name", "type")})
            components.append(Component(table["name"], table["type"], values))
        drawn = paint_drawing(draw_page(components, Resources()))
        screenshot = read_picture((self.FOLDER / "editor.png").read_bytes())
        for component in components[1:]:
            with self.subTest(slider=component.name):
                differing = smoothed_differences(drawn, screenshot, component.values, self.PURE,
                                                 64)
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


class EditorSliderKnobTest(unittest.TestCase):
    """A probe of sliders' knobs, fixtures/slider-knobs/app, against the
    Editor's simulator showing each page, editor-<page>.png, cut to the
    screen. Each slider's track is the page's white, so only its knob shows,
    black. page0 holds round knobs across, of the size the Editor chooses, on
    sliders 10 to 81 high, and page1 the same knobs given that size. page2
    and page3 hold them upright. page4 gives one side of a knob and lets the
    Editor choose the other, and holds two sliders with tracks: one of the
    defaults' colours, 40 high, and one 25 high. page5 and page6, across and
    upright, place knobs on sliders of odd lengths and breadths, with one
    side of a knob even and the other odd. page7 and page8 hold square knobs
    and picture knobs. Each picture is black, its right column red and its
    bottom row blue. Where both show one of the page's, the sliders', or the
    pictures' colours, it is the same one. Elsewhere, on a smoothed edge, the
    drawing comes within SMOOTHING."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "slider-knobs"

    def test_as_the_editor_draws_them(self):
        root = self.FOLDER / "app"
        pictures = {path.stem: read_picture(path.read_bytes())
                    for path in (root / "pictures").glob("*.png")}
        shown_in_pictures = {colour for picture in pictures.values()
                             for _, colour in picture.convert("RGB").getcolors()}
        for page in ["page%d" % number for number in range(9)]:
            simulation = Simulation(root)
            if page != simulation.page:
                simulation.serial_input("page %s" % page)
            drawn = paint_drawing(screen_drawing(simulation))
            screenshot = read_picture((self.FOLDER / ("editor-%s.png" % page)).read_bytes())
            components = simulation.drawing_inputs().components
            palette = list(shown_in_pictures | {
                rgb565_to_rgb(entry.values[key]) for entry in components
                for key in ("bco", "bco1", "pco") if key in entry.values})
            for entry in components[1:]:
                with self.subTest(page=page, slider=entry.name):
                    differing = smoothed_differences(drawn, screenshot, entry.values, palette,
                                                     SMOOTHING)
                    self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


class EditorDataRecordScrollTest(unittest.TestCase):
    """A probe of data records scrolled past the screen's left,
    fixtures/data-record-scroll/: three folders, app0 to app2, whose pages
    page1 to page5 each hold up to 8 data records, against the Editor's
    simulator showing each page, editor-<folder>-<page>.png, cut to the
    screen. Each record has one title, black on white, in a first column of
    60 to 240, which its page's load event scrolls by `val_x`, a step at a
    time around the scroll that hides as much of the column as the title is
    wide. Most are centred: titles 10 to 129 pixels wide, one wider than its
    column, grid lines 1 and 3 wide, and records at x 100, away from the
    screen's edge. The last are right-aligned and left-aligned, scrolled 30
    to 130. Every record's pixels come within 12 of the Editor's."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "data-record-scroll"

    def test_as_the_editor_draws_them(self):
        for screenshot_path in sorted(self.FOLDER.glob("editor-*.png")):
            _, folder, page = screenshot_path.stem.split("-")
            with self.subTest(folder=folder, page=page):
                simulation = Simulation(self.FOLDER / ("app%s" % folder))
                simulation.serial_input("page %s" % page)
                drawn = paint_drawing(screen_drawing(simulation))
                screenshot = read_picture(screenshot_path.read_bytes())
                differing = [(entry.name, x, y)
                             for entry in simulation.drawing_inputs().components[1:]
                             for x, y in differing_pixels(drawn, screenshot, entry.values, 12)]
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


def smoothed_differences(drawn: Image.Image, shot: Image.Image, box: dict, palette: list,
                         tolerance: int) -> list:
    """Returns the pixels of `box` where the painted picture `drawn` and the
    screenshot `shot` differ, as (x, y, why). Where both show a colour of
    `palette`, within 6 in each colour, it must be the same one ("colour").
    Elsewhere one shows a blend, as on a smoothed edge, and they may differ
    by `tolerance` ("edge")."""
    def pure(colour: tuple):
        return next((index for index, listed in enumerate(palette)
                     if max(abs(a - b) for a, b in zip(colour, listed)) <= 6), None)
    differing = []
    # The rule passes every pixel that is the same in both pictures.
    for x, y in differing_pixels(drawn, shot, box, 0):
        shown = shot.getpixel((x, y))[:3]
        ours = drawn.getpixel((x, y))
        both = [pure(shown), pure(ours)]
        if None not in both:
            if both[0] != both[1]:
                differing.append((x, y, "colour"))
        elif max(abs(a - b) for a, b in zip(shown, ours)) > tolerance:
            differing.append((x, y, "edge"))
    return differing


def screen_drawing(simulation: Simulation) -> dict:
    """The drawing of what `simulation`'s screen shows, as the debugger's
    panel takes it (Previews.simulation_drawing)."""
    return Previews().simulation_drawing(simulation, simulation.drawing_inputs())


# The most a pixel of a smoothed edge differs from the Editor's: its edges
# blend otherwise than nxwright's sampling, by up to 76 where one list's
# rounded item lies over another's. A slider's round knob, black on white,
# differs by up to 75, on a knob 29 by 15. A box, an item, a text, an
# arrow, or a knob out of place differs by far more.
SMOOTHING = 80
# The most a pixel of a rounded progress bar's smoothed edge differs from the
# Editor's (_on_rounded_bar_edge).
BAR_SMOOTHING = 112


def _on_rounded_bar_edge(values: dict, x: int, y: int) -> bool:
    """Whether the page's pixel (x, y) lies on a rounded progress bar's
    smoothed edge, whose attributes are `values`: near a corner, on its
    sides, or by its fill's rounded end. nxwright smooths those otherwise than
    the Editor does (page_drawing.py)."""
    x0, y0, w, h = (values[key] for key in ("x", "y", "w", "h"))
    if not (values.get("sta") == 0 and values.get("dis", 0) >= 25):
        return False
    down = values.get("dez") == 1
    reach = values["dis"] / 100 * (min(w, h) - 1) / 2 + 2
    filled = (h if down else w) * values.get("val", 0) // 100
    along, across = (y0 + h - 1 - y, x - x0) if down else (x - x0, y - y0)
    length, breadth = (h, w) if down else (w, h)
    return (min(along, length - 1 - along) < reach and min(across, breadth - 1 - across) < reach
            or min(along, length - 1 - along, across, breadth - 1 - across) < 2
            or 0 < filled < length and filled - reach <= along < filled + 2)


def combo_box_differences(component: Component, drawn: Image.Image, shot) -> list:
    """Returns the (x, y) where a combo box's pixels, `drawn` as the
    webview paints them, differ from the Editor's picture `shot` by more
    than SMOOTHING: over the box, and over its open list."""
    values = component.values
    areas = [values]
    layout = list_layout(values, len(items(values))) if values.get("down") == 1 else None
    if layout:
        areas.append(layout.area)
    return [pixel for area in areas for pixel in differing_pixels(drawn, shot, area, SMOOTHING)]


def _in_box(box: dict, x: int, y: int) -> bool:
    """Returns whether the pixel (x, y) lies in `box`, a dict of "x", "y",
    "w", and "h"."""
    return box["x"] <= x < box["x"] + box["w"] and box["y"] <= y < box["y"] + box["h"]


def differing_pixels(drawn: Image.Image, shot: Image.Image, box: dict, tolerance: int) -> list:
    """Returns the pixels where the painted picture `drawn` and the
    screenshot `shot` differ by more than `tolerance` in a colour, as (x, y),
    row by row.
    Only the pixels of `box` are compared, a dict of "x", "y", "w", and "h".
    The part of `box` outside either picture is left out.
    The screenshot's alpha is not compared."""
    left, top = max(box["x"], 0), max(box["y"], 0)
    right = min(box["x"] + box["w"], drawn.width, shot.width)
    bottom = min(box["y"] + box["h"], drawn.height, shot.height)
    if left >= right or top >= bottom:
        return []
    area = (left, top, right, bottom)
    red, green, blue = ImageChops.difference(drawn.crop(area),
                                             shot.crop(area).convert("RGB")).split()
    largest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    past = largest.point([255 if level > tolerance else 0 for level in range(256)]).tobytes()
    # Python reads only the pixels past the tolerance, one at a time.
    width, found = right - left, []
    index = past.find(255)
    while index >= 0:
        found.append((left + index % width, top + index // width))
        index = past.find(255, index + 1)
    return found


class DifferingPixelsTest(unittest.TestCase):
    """The pixels of a box where a painted picture and a screenshot differ
    by more than a tolerance (differing_pixels)."""
    BOX = {"x": 0, "y": 0, "w": 4, "h": 3}

    def test_past_the_tolerance_row_by_row(self):
        drawn = Image.new("RGB", (4, 3), (100, 100, 100))
        shot = Image.new("RGBA", (4, 3), (100, 100, 100, 255))
        shot.putpixel((2, 0), (100, 103, 100, 255))
        shot.putpixel((1, 1), (98, 100, 100, 255))
        shot.putpixel((0, 2), (100, 100, 97, 255))
        # A screenshot's alpha is not compared.
        shot.putpixel((3, 2), (100, 100, 100, 0))
        self.assertEqual(differing_pixels(drawn, shot, self.BOX, 1), [(2, 0), (1, 1), (0, 2)])
        self.assertEqual(differing_pixels(drawn, shot, self.BOX, 2), [(2, 0), (0, 2)])
        self.assertEqual(differing_pixels(drawn, shot, self.BOX, 3), [])

    def test_a_box_is_cut_at_both_pictures_edges(self):
        drawn = Image.new("RGB", (4, 3), (0, 0, 0))
        shot = Image.new("RGBA", (3, 4), (255, 255, 255, 255))
        self.assertEqual(differing_pixels(drawn, shot, {"x": -1, "y": 1, "w": 10, "h": 10}, 0),
                         [(0, 1), (1, 1), (2, 1), (0, 2), (1, 2), (2, 2)])
        self.assertEqual(differing_pixels(drawn, shot, {"x": 3, "y": 0, "w": 2, "h": 2}, 0), [])


def _rgb565(colour: str) -> int:
    """Returns the RGB565 number of a colour written "#rrggbb"."""
    red, green, blue = (int(colour[index:index + 2], 16) for index in (1, 3, 5))
    return (red >> 3) << 11 | (green >> 2) << 5 | blue >> 3


class EditorWaveformTest(unittest.TestCase):
    """A waveform's points, fixtures/waveform/points.json, as the demo's Day
    page added them, against the Editor's simulator showing them, its colours
    dimmed to 80%, each screenshot cropped to the screen: with `dir` 0, new
    points entering at the left, fixtures/waveform/editor.png; and with `dir`
    1, at the right, editor-dir1.png, whose screenshot missed the page's last
    3 columns."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "waveform"
    SCREENSHOTS = (("editor.png", 0), ("editor-dir1.png", 1))

    def test_the_points_as_the_editor_draws_them(self):
        for name, direction in self.SCREENSHOTS:
            with self.subTest(screenshot=name):
                self.compare(name, direction)

    def compare(self, name: str, direction: int):
        data = json.loads((self.FOLDER / "points.json").read_text(encoding="utf-8"))
        chart = dict(data["chart"], dir=direction)
        wave = Component("chart", "waveform", dict(chart, sta=3))
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})
        waves = {"chart": {int(channel): points for channel, points in data["points"].items()}}
        shapes = draw_page([page, wave], Resources(), waves=waves)["shapes"]
        drawn = set()
        for shape in [shape for shape in shapes if shape["kind"] == "text"]:
            image = read_picture(base64.b64decode(shape["image"].split(",")[1]))
            drawn |= {(shape["x"] + index % image.width, shape["y"] + index // image.width)
                      for index, pixel in enumerate(image.get_flattened_data()) if pixel[3]}
        screenshot = read_picture((self.FOLDER / name).read_bytes())
        shown = set()
        for y in range(chart["y"], chart["y"] + chart["h"]):
            for x in range(chart["x"], chart["x"] + chart["w"]):
                red, green, blue = screenshot.getpixel((x, y))[:3]
                # A curve's pixels are coloured; the chart's background is gray.
                if max(red, green, blue) - min(red, green, blue) > 60:
                    shown.add((x, y))
        self.assertGreater(len(shown), 1000)
        self.assertEqual(drawn, shown)


class EditorAssumptionsTest(unittest.TestCase):
    """The probe of what the drawing had assumed, fixtures/drawing-assumptions/:
    a source folder whose pages the Editor's simulator showed once open,
    editor-<page>.png, cropped to the screen, each page on a picture of
    bands. page0: a text without background, and texts on a crop, one with
    a border; waveforms with a grid, `dis` 50 and 200, and `dir` 1 and 2;
    progress bars of pictures rounded, and fills that are no whole number
    of pixels. page1: texts placed at their corner with a border on each
    background; a grid whose cells do not divide its waveform; `dis` 33;
    full waveforms in each `dir`. page2: a text on a picture, a button and
    a number on a crop, each with a border. page3: the layouts that read the
    border's inset, on a crop with a border, and a sliding text on a colour
    alike, with numbers that code sets to the two sliding texts' `maxval_y`.
    page4: a select on each background. page5: a text, a sliding text, a
    select, and an open combo box, each with its lines apart by a carriage
    return and a line feed, by a carriage return alone, and by a line feed
    alone, and numbers that code sets to the sliding texts' `maxval_y`.
    page6: a gauge on each background, and a waveform of `ch` 2 whose code
    adds points to its four channels. Its picture also shows the probe's
    gauges past what is modelled (gauge_drawing.py), which page6 leaves out.
    Each page's code gives its waveforms a ramp of 100 points as it opens. Every component's pixels
    come within 12 of the Editor's in each colour, but a gauge's, compared
    as EditorValueWidgetsTest compares a gauge, with GAUGE_COLOURS as its
    colours."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "drawing-assumptions"
    # The colours page6's gauges show: the crop's two bands, white, the
    # page's two bands, the needle's red, and its centre's blue.
    GAUGE_COLOURS = [(132, 211, 165), (247, 211, 132), (255, 255, 255), (165, 195, 231),
                     (231, 227, 231), (255, 0, 0), (0, 0, 255)]

    def test_as_the_editor_draws_them(self):
        root = self.FOLDER / "app"
        for page in ("page0", "page1", "page2", "page3", "page4", "page5", "page6"):
            with self.subTest(page=page):
                simulation = Simulation(root)
                if page != simulation.page:
                    simulation.serial_input("page %s" % page)
                drawing = Previews().drawing_of(
                    simulation.source_folder, simulation.app, simulation.components(),
                    waves=simulation.waves(), cards=simulation.cards)
                drawn = paint_drawing(drawing)
                screenshot = read_picture((self.FOLDER / ("editor-%s.png" % page)).read_bytes())
                differing = []
                for component in simulation.components()[1:]:
                    values = component.values
                    if "x" not in values:
                        continue
                    if component.type == "combo-box":
                        # Its corners are smoothed otherwise than the
                        # Editor's, and its open list lies outside it.
                        differing += [(component.name, x, y) for x, y in
                                      combo_box_differences(component, drawn, screenshot)]
                        continue
                    gauge = component.type == "gauge"
                    if gauge:
                        # The rule passes every pixel that is the same in both pictures.
                        apart = [(component.name, x, y)
                                 for x, y in differing_pixels(drawn, screenshot, values, 0)
                                 if _smoothed_pixel_differs(screenshot.getpixel((x, y))[:3],
                                                            drawn.getpixel((x, y)),
                                                            self.GAUGE_COLOURS)]
                    else:
                        apart = [(component.name, x, y)
                                 for x, y in differing_pixels(drawn, screenshot, values, 12)]
                    allowed = values["w"] * values["h"] * EditorValueWidgetsTest.NEEDLE_ENDS
                    if not gauge or len(apart) > allowed:
                        differing += apart
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


# A `fill` of the whole screen in green, which the probes of drawing again
# paint first.
_FILL = "fill 0,0,800,480,2016"


class EditorDrawingProbesTest(unittest.TestCase):
    """The probes in fixtures/drawing-assumptions/: pages 7 to 16, which the
    Editor's simulator showed once open, editor-<page>.png, and page7 again
    after lines typed on its serial line. page7: the types with a border on a
    crop, a picture, and none; checkboxes of widths 4 does not divide;
    xfloats and numbers of many digits; QR codes whose logo is wider than
    the code; combo boxes on a picture, and open with a border. page8: the
    larger types with a border. page9: lines of four slopes, and `xstr` on
    each background. page10: QR logos past the bound; data records with a
    border; an open list running past the screen's bottom; scrolling texts
    placed across their border. page11: lines whose steps fall halfway.
    page12, page14, and page15: QR logos at and past the bound, at three
    sizes. page13: a text whose `aph` code sets past 127. page16: file
    browsers with icons of two sizes, a type's own icon, and no file icon,
    on a card the test makes as the probe's held. page17, page18, and
    page19: selects of no background, on a picture, and on a crop, of
    heights 120 to 143, the last row of them cut by the screen's bottom.
    page20: page8's select of no background, and copies of it changed one
    way each, some near the screen's bottom. page21: selects cut by the
    screen's right edge, its bottom edge, and both. page22: open combo
    boxes whose lists run past the screen's top, its left, its right, and
    its bottom. page23: data records whose columns `val_x` scrolls past the
    screen's left, their texts at their cells' left and centred, and one
    away from the edge, each filling its file on the card as the page
    loads. page24: centred data records scrolled away from the screen's
    edge, and data records cut by its right edge. page25, page26, and
    page27: centred data records at the screen's left, scrolled by
    `val_x` from 20 to 100, their grid lines 1 and 3 wide. page28: texts of
    lines of different widths, wrapping, and with a border. page29: one
    component of each of several types, which code sets after a `fill`,
    some to the value they hold. page31, page32, and page33: texts drawn
    again over a `fill`, of no background and over or under others, and
    moved. page34: texts `ref` draws again over a `fill`. page35: a page
    without background, entered from page0 before a `fill` and after one,
    its texts set. page36 and page38: texts linked in turn to one drawn
    again over a `fill`, and one under it. page37: a hidden text, set and
    moved. page39: a text nothing meets, left under the fill as another is
    drawn again. page40: a button pressed, then released, over a `fill`,
    meeting a text of no background. page35-ref0 and page36-ref0: `ref 0`,
    the page drawn again over a `fill`, without a background and with one.
    page41 and page42: a text sliding in, over a `fill` painted as it
    starts, moved by code meanwhile or not, and over another text. page44:
    a checkbox a press toggles, held and released, and a sliding text
    pressed, held and released, over a `fill`, each meeting a text of no
    background. page45: a file browser and a data record pressed and held
    over a `fill`. page46 to page48: a chain of texts, each meeting the
    next alone, over a `fill`: the first moved away, the last of no
    background, and the middle one hidden, the first set or moved.
    page40-slider: its slider pressed on its track, the knob
    left under the press; tS, which its release event writes `val` into,
    is left out, as the value a press gives differs. page30: a page that a
    `page` command shows while `ref_stop` holds, from page0, before and
    after code changes it, and after `ref_star`. A page without background
    is drawn over the screen painted before the line that entered it, as
    the panel keeps it. Every
    component's pixels, and those drawing commands painted, come within 12
    of the Editor's in each colour; a combo box's within SMOOTHING, its open
    list too; a rounded progress bar's smoothed edges within BAR_SMOOTHING;
    and the areas of SMOOTHED within their own tolerance."""
    FOLDER = EditorAssumptionsTest.FOLDER
    # (page, picture, lines typed once the page is open, or touches:
    # ("press", component, x, y) and ("release",), or ("advance", ms))
    PROBES = [("page%d" % number, "page%d" % number, ()) for number in range(7, 29)
              if number != 13] + [
        ("page13", "page13", ("tAph.aph=200",)),
        ("page29", "page29", (_FILL, 't0.txt="new"', 't1.txt="same"', "n0.val=5", "b0.bco=63488",
                              "j0.val=60", "c0.val=0", "x0.val=5678", "h0.val=50", "t2.font=0",
                              "t3.x=330", "t4.aph=127")),
        ("page31", "page31", (_FILL, 'tOver.txt="OVER"', "tMove.x=470", 'tAlone.txt="ALONE"')),
        ("page32", "page32", (_FILL, 'tSmall.txt="SMALL"')),
        ("page33", "page33", (_FILL, "tMover.x=640", 'tSmall2.txt="S2"')),
        ("page34", "page34", (_FILL, "ref tRef", "ref tRefColour")),
        # A page without background, entered from page0, then after a fill.
        ("page0", "page35", ("page page35", _FILL, 'tNone.txt="NONE"', 'tSolid.txt="SOLID"')),
        ("page0", "page35-green", (_FILL, "page page35", 'tNone.txt="NONE"')),
        ("page36", "page36", (_FILL, 'tA.txt="AA"')),
        ("page37", "page37", ("vis tHid,0", _FILL, 'tHid.txt="H"', "tHid.x=300")),
        ("page38", "page38", (_FILL, 'tA.txt="AA"')),
        ("page39", "page39", (_FILL, 'tA.txt="AA"')),
        ("page40", "page40-held", (_FILL, ("press", "bP", 110, 50))),
        ("page40", "page40-released", (_FILL, ("press", "bP", 110, 50), ("release",))),
        ("page40", "page40-slider", (_FILL, ("press", "hS", 100, 270), ("release",))),
        ("page0", "page35-ref0", ("page page35", _FILL, "ref 0")),
        ("page41", "page41", (_FILL, ("advance", 5000))),
        ("page41", "page41-moved", (_FILL, "tSl.x=400", ("advance", 5000))),
        ("page42", "page42", (("advance", 5000),)),
        ("page44", "page44-check-held", (_FILL, ("press", "cB", 50, 50))),
        ("page44", "page44-check-released", (_FILL, ("press", "cB", 50, 50), ("release",))),
        ("page44", "page44-slide-held", (_FILL, ("press", "stS", 550, 80), ("advance", 500))),
        ("page45", "page45-fb-held", (_FILL, ("press", "fbH", 60, 50), ("advance", 1500))),
        ("page45", "page45-dr-held", (_FILL, ("press", "drH", 500, 40), ("advance", 1500))),
        ("page46", "page46", (_FILL, "tA.x=500")),
        ("page47", "page47", (_FILL, 'tA.txt="AA"')),
        ("page48", "page48", ("vis tH,0", _FILL, 'tA.txt="AA"')),
        ("page48", "page48-moved", ("vis tH,0", _FILL, "tA.x=500")),
        ("page44", "page44-slide-released", (_FILL, ("press", "stS", 550, 80),
                                             ("advance", 500), ("release",))),
        ("page36", "page36-ref0", (_FILL, "ref 0")),
        ("page7", "page7-ref-stop", ("ref_stop", "xTwelve.val=99", "xV5.val=1")),
        ("page7", "page7-hidden-held", ("ref_stop", "vis xTwelve,0")),
        ("page7", "page7-shown-at-once", ("vis xTwelve,0", "ref_stop", "vis xTwelve,1")),
        # Each from the start, on page0: the page before kept showing.
        ("page0", "page30-held", ("ref_stop", "page page30")),
        ("page0", "page30-changed", ("ref_stop", "page page30", 'tNew.txt="changed"')),
        ("page0", "page30-star", ("ref_stop", "page page30", "ref_star"))]
    # The areas compared beyond the components', as (x, y, w, h), by picture:
    # those drawing commands painted, or the whole screen.
    PAINTED_AREAS = {"page9": [(0, 0, 440, 220), (450, 10, 200, 170)],
                     "page11": [(0, 320, 440, 70)],
                     # A `fill` of the whole screen: a moved component's old
                     # place lies outside every component. And page30's
                     # pictures, where nothing of another page may show.
                     **{picture: [(0, 0, 800, 480)] for picture in (
                         "page29", "page31", "page32", "page33", "page34", "page35",
                         "page35-green", "page36", "page37", "page38", "page39",
                         "page40-held", "page40-released", "page40-slider", "page35-ref0",
                         "page36-ref0", "page41", "page41-moved", "page42",
                         "page44-check-held", "page44-check-released", "page44-slide-held",
                         "page44-slide-released", "page45-fb-held", "page45-dr-held",
                         "page46", "page47", "page48", "page48-moved",
                         "page30-held", "page30-changed",
                         "page30-star")}}
    # Areas left out, as (x, y, w, h), by picture: page40's tS, where the
    # value a press on the slider gives shows, 19 in the Editor's and 20 in
    # nxwright's.
    LEFT_OUT = {"page40-slider": [(300, 220, 200, 80)]}
    # Areas of smoothed edges, as ((x, y, w, h), tolerance): page29's
    # slider's round knob, and its track's rounded ends, smoothed as a
    # rounded progress bar's.
    SMOOTHED = {"page29": [((140, 180, 40, 40), SMOOTHING), ((10, 195, 10, 10), BAR_SMOOTHING),
                           ((300, 195, 10, 10), BAR_SMOOTHING)],
                # page40-slider's round knob, from x 81 under the press, and
                # its track's rounded ends, drawn again over the fill.
                "page40": [((81, 250, 39, 40), SMOOTHING), ((10, 265, 10, 10), BAR_SMOOTHING),
                           ((400, 265, 10, 10), BAR_SMOOTHING)]}

    def card(self) -> Path:
        """A card holding what the probe's held: a folder with a folder and
        a file in it."""
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        card = Path(folder.name)
        (card / "nxprobe_agent-a_fb" / "sub").mkdir(parents=True)
        (card / "nxprobe_agent-a_fb" / "a.txt").write_bytes(b"hello")
        return card

    def test_as_the_editor_draws_them(self):
        root = self.FOLDER / "app"
        for page, picture, lines in self.PROBES:
            with self.subTest(picture=picture):
                simulation = Simulation(root, cards={"sd0/": self.card()})
                typed = ([] if page == simulation.page else ["page %s" % page]) + list(lines)
                # The screen the page shown was entered over, as the panel
                # keeps it: the screen painted before the line that entered it.
                under = None
                for line in typed:
                    entry = simulation.drawing_inputs().entry
                    before = screen_drawing(simulation)
                    if isinstance(line, str):
                        simulation.serial_input(line)
                    elif line[0] == "press":
                        simulation.press(*line[1:])
                    elif line[0] == "release":
                        simulation.release()
                    else:
                        simulation.advance(line[1])
                    if simulation.drawing_inputs().entry != entry:
                        under = paint_drawing(before, under)
                drawn = paint_drawing(screen_drawing(simulation), under)
                # The components the screen shows, which a page change while
                # `ref_stop` holds leaves those of the page before.
                on_screen = simulation.drawing_inputs().components
                screenshot = read_picture(
                    (self.FOLDER / ("editor-%s.png" % picture)).read_bytes())
                differing = []
                areas = [(entry.name, entry.values) for entry in on_screen[1:]
                         if "x" in entry.values and entry.type != "combo-box"]
                areas += [("painted", {"x": x, "y": y, "w": w, "h": h})
                          for x, y, w, h in self.PAINTED_AREAS.get(picture, ())]
                # An open list is drawn over what lies under it, so it is
                # left out here. It is compared with its combo box below, at
                # the wider tolerance for smoothed edges.
                left_out = [list_layout(entry.values, len(items(entry.values))).area
                            for entry in on_screen[1:]
                            if entry.type == "combo-box" and entry.values.get("down") == 1]
                left_out += [{"x": x, "y": y, "w": w, "h": h}
                             for x, y, w, h in self.LEFT_OUT.get(picture, ())]
                smoothed = [({"x": x, "y": y, "w": w, "h": h}, tolerance)
                            for (x, y, w, h), tolerance in self.SMOOTHED.get(page, ())]
                # A rounded progress bar's smoothed edges, within BAR_SMOOTHING.
                bars = [entry.values for entry in on_screen[1:] if entry.type == "progress-bar"]
                for name, area in areas:
                    # The rule passes every pixel within 12, on a smoothed edge or not.
                    for x, y in differing_pixels(drawn, screenshot, area, 12):
                        if any(_in_box(box, x, y) for box in left_out):
                            continue
                        most = next((tolerance for box, tolerance in smoothed
                                     if _in_box(box, x, y)), None)
                        if most is None:
                            most = BAR_SMOOTHING if any(_on_rounded_bar_edge(bar, x, y)
                                                        for bar in bars) else 12
                        if max(abs(a - b) for a, b in zip(drawn.getpixel((x, y)),
                                                          screenshot.getpixel((x, y))[:3])) > most:
                            differing.append((name, x, y))
                for entry in on_screen[1:]:
                    if entry.type == "combo-box":
                        differing += [(entry.name, x, y) for x, y in
                                      combo_box_differences(entry, drawn, screenshot)]
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))

    def test_slides_over_a_fill_as_the_editor_draws_them_but_for_their_steps(self):
        # page43, whose loadend event paints a fill as its slides start: a
        # text sliding in from the left, and one from the top left corner,
        # its box sliding from (-150, -60) to (300, 250). The Editor's
        # simulator's steps of that slide left its band's slanted edges in
        # steps of about 3 pixels across and 2 down, as nxwright's steps of
        # 20 milliseconds do (opening_effects.STEP). Where the two steps
        # fall differs, by up to a step and the pixel each place is cut by.
        root = self.FOLDER / "app"
        simulation = Simulation(root)
        simulation.serial_input("page page43")
        simulation.advance(5000)
        drawn = paint_drawing(screen_drawing(simulation))
        screenshot = read_picture((self.FOLDER / "editor-page43.png").read_bytes())
        across = (300 + 150) / (250 + 60)       # pixels across for each one down

        def near_an_edge(x: int, y: int) -> bool:
            # The lines the box's top right corner, from (0, -60), and its
            # bottom left corner, from (-150, 0), swept.
            return any(abs(x - (start_x + (y - start_y) * across)) <= 4
                       for start_x, start_y in ((0, -60), (-150, 0)))
        differing = [(x, y) for x, y in differing_pixels(drawn, screenshot,
                                                         {"x": 0, "y": 0, "w": 800, "h": 480}, 12)
                     if not near_an_edge(x, y)]
        self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


class TurnedCardFilesTest(unittest.TestCase):
    """A probe of a card's files on a turned screen, in
    fixtures/drawing-assumptions/turned/: a folder for each of 90, 180, and
    270 degrees, whose pages the Editor's simulator showed,
    editor-<rotation>-<page>.png, cut to the screen, and the card it read. On
    each, external pictures show one marked picture as a PNG, a JPEG, and .xi
    files made for each rotation, and larger than its component, and videos
    show it made for 0 and for the screen's rotation. The Editor's window
    showed a screen turned 90 or 270 degrees down to its 523rd row, which the
    probe's components stay above. Every component's pixels come within 12 of
    the Editor's in each colour."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "drawing-assumptions" / "turned"
    PROBES = [("f90", "page0"), ("f90", "page1"), ("f180", "page0"), ("f270", "page0"),
              ("f270", "page1")]

    def test_as_the_editor_draws_them(self):
        for folder, page in self.PROBES:
            with self.subTest(folder=folder, page=page):
                simulation = Simulation(self.FOLDER / folder,
                                        cards={"sd0/": self.FOLDER / "card"})
                if page != simulation.page:
                    simulation.serial_input("page %s" % page)
                drawn = paint_drawing(screen_drawing(simulation))
                screenshot = read_picture((self.FOLDER / ("editor-%s-%s.png" % (
                    folder[1:], page))).read_bytes())
                differing = []
                for entry in simulation.components()[1:]:
                    differing += [(entry.name, x, y) for x, y in
                                  differing_pixels(drawn, screenshot, entry.values, 12)]
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


class CheckboxTest(unittest.TestCase):
    """A checkbox's tick: the box less a quarter of its width on each side,
    the quarter cut toward zero, as the Editor's simulator drew it at widths
    of 21 to 33 (fixtures/drawing-assumptions/, page7)."""

    def test_the_tick_at_widths_4_does_and_does_not_divide(self):
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})
        for width, side in ((20, 10), (21, 11), (22, 12), (23, 13), (30, 16), (33, 17)):
            with self.subTest(width=width):
                box = component("c", "checkbox", w=width, h=20, val=1, bco=0xffff, pco=0, style=0)
                tick = [shape for shape in draw_page([page, box], Resources())["shapes"]
                        if shape["component"] == "c"][1]
                self.assertEqual((tick["x"], tick["y"], tick["w"], tick["h"]),
                                 (10 + width // 4, 20 + width // 4, side, side))


class ComboBoxListTest(unittest.TestCase):
    """An open combo box's list running past the screen's bottom edge."""

    def test_an_item_cut_by_the_screens_edge_centres_its_text_in_what_shows(self):
        # The Editor's simulator drew the item's box at its full size, cut by
        # the edge, and its text in the 20 rows the screen showed of its 42
        # (fixtures/drawing-assumptions/, page10).
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})
        combo = Component("cb", "combo-box", {
            "x": 570, "y": 360, "w": 180, "h": 42, "font": 0, "txt": "one",
            "path": "one\r\ntwo", "sta": 1, "bco": 0xffff, "dis": 40, "down": 1})
        shapes = [(shape["kind"], shape["x"], shape["y"], shape["w"], shape["h"])
                  for shape in draw_page([page, combo], Resources())["shapes"]
                  if shape["component"] == "cb"]
        self.assertIn(("text", 570, 460, 180, 20), shapes)


class QrCodeTest(unittest.TestCase):
    """A QR code component's shapes: a square of `bco` as wide as the
    component, the code inside its margin `dis`, and the logo."""
    URL = "https://nextion.itead.cc"

    def draw(self, **values) -> dict:
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})
        code = Component("code", "qr-code", dict({"x": 10, "y": 20, "w": 120, "h": 120,
                                                  "dis": 4, "bco": 0xFFFF, "pco": 0,
                                                  "sta": 0, "txt": self.URL}, **values))
        return draw_page([page, code], Resources())

    def shapes(self, drawing: dict) -> list:
        return [(shape["kind"], shape["x"], shape["y"], shape["w"], shape["h"])
                for shape in drawing["shapes"] if shape["component"] == "code"]

    def test_a_square_as_high_as_wide(self):
        drawing = self.draw(w=200, h=120)
        self.assertEqual(self.shapes(drawing), [("colour", 10, 20, 200, 200),
                                                ("text", 14, 24, 192, 192)])
        self.assertEqual(drawing["components"][1]["h"], 120)

    def test_no_code_for_an_empty_text(self):
        self.assertEqual(self.shapes(self.draw(txt="")), [("colour", 10, 20, 120, 120)])

    def test_no_code_for_modules_under_a_pixel(self):
        # The text makes 25 modules a side.
        self.assertEqual(self.shapes(self.draw(w=24, h=24, dis=0)), [("colour", 10, 20, 24, 24)])
        self.assertEqual(self.shapes(self.draw(w=25, h=25, dis=0)),
                         [("colour", 10, 20, 25, 25), ("text", 10, 20, 25, 25)])

    def test_the_logo_in_the_squares_middle(self):
        drawing = self.draw(w=129, h=60, sta=1, pic=1)
        logo = [shape for shape in drawing["shapes"] if shape["kind"] == "picture"]
        # The 64 by 64 picture in a square of 129: its corner at 32.5, rounded down.
        self.assertEqual([(shape["x"], shape["y"], shape["w"], shape["h"]) for shape in logo],
                         [(42, 52, 64, 64)])

    def test_a_logo_only_within_the_code_less_4(self):
        # The Editor's simulator drew a logo whose sides are each at most
        # the code's width, w - 2 * dis, less 4, and none past it: at 150
        # wide and dis 4, a logo 138 wide, and not one 139 wide
        # (fixtures/drawing-assumptions/, page14). The 64 by 64 logo needs a
        # code 68 wide.
        for width, dis, drawn in ((76, 4, True), (75, 4, False), (72, 2, True), (71, 2, False)):
            with self.subTest(width=width, dis=dis):
                drawing = self.draw(w=width, h=width, dis=dis, sta=1, pic=1)
                self.assertEqual(any(shape["kind"] == "picture" for shape in drawing["shapes"]),
                                 drawn)

    def test_a_text_the_encoding_cannot_hold(self):
        drawing = self.draw(txt="日本")
        self.assertEqual(self.shapes(drawing), [("colour", 10, 20, 120, 120)])
        self.assertEqual(len(drawing["notes"]), 1)
        self.assertIn("its code is not drawn", drawing["notes"][0])


class TooLargeTest(unittest.TestCase):
    """A picture far larger than the page, as from a mistyped size, is not
    made, so that the drawing never stalls on it: a note says so."""

    def test_pictures_too_large_are_not_made(self):
        page = Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480})
        for kind, values in (("radio", {"w": 20000, "h": 20}),
                             ("switch", {"w": 30000, "h": 300}),
                             ("qr-code", {"w": 9000, "h": 20, "dis": 0,
                                          "txt": "https://nextion.itead.cc"})):
            with self.subTest(kind=kind):
                drawing = draw_page([page, Component("big", kind, dict(values, x=0, y=0))],
                                    Resources())
                self.assertEqual([shape["kind"] for shape in drawing["shapes"]
                                  if shape["component"] == "big" and shape["kind"] == "text"], [])
                self.assertEqual(len(drawing["notes"]), 1)
                self.assertIn("is too large", drawing["notes"][0])


class EditorQrCodeTest(unittest.TestCase):
    """QR codes against the Editor's simulator showing them, each screenshot
    cropped to the screen (fixtures/qr-codes/). codes.toml, editor.png: texts
    of each mode, up to version 11, on a white page. sizes.toml,
    editor-sizes.png, on a gray page: an empty text; codes of less than a
    pixel a module, and of 1 to 3; components wider than high and higher
    than wide; and logos of 40 and 41 pixels in squares of 90 to 200 pixels.
    Every pixel of each component's square and rectangle is the same, within
    the screen's 16-bit colours. The codes of the texts the Editor splits
    otherwise (fixtures/qr-codes.json) are left out: their modules differ."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "qr-codes"
    DEFAULTS = {"dis": 8, "bco": 0xFFFF, "pco": 0, "sta": 0, "txt": "https://nextion.itead.cc"}
    LOGOS = ("logo", "logo41")
    PAGES = (("codes.toml", "editor.png"), ("sizes.toml", "editor-sizes.png"))

    def test_as_the_editor_draws_them(self):
        fixture = json.loads((self.FOLDER.parent / "qr-codes.json").read_text(encoding="utf-8"))
        split_otherwise = {code["txt"] for code in fixture["codes"] if "editor_segments" in code}
        logos = {name: read_picture((self.FOLDER / (name + ".png")).read_bytes())
                 for name in self.LOGOS}
        for page_file, screenshot_file in self.PAGES:
            with self.subTest(page=page_file):
                components = self.components(page_file)
                drawing = draw_page(components, _Logos(logos))
                drawing["pictureFiles"] = {name: {"path": str(self.FOLDER / (name + ".png"))}
                                           for name in self.LOGOS}
                drawn = paint_drawing(drawing)
                screenshot = read_picture((self.FOLDER / screenshot_file).read_bytes())
                for component in components[1:]:
                    if component.values["txt"] not in split_otherwise:
                        with self.subTest(code=component.name):
                            self.compare(component.values, drawn, screenshot)

    def components(self, page_file: str) -> list:
        """The page file's page and QR codes, their colours as RGB565 and
        their logos as picture IDs."""
        data = tomllib.loads((self.FOLDER / page_file).read_text(encoding="utf-8"))

        def values(table: dict, defaults: dict) -> dict:
            found = dict(defaults)
            for key, value in table.items():
                if key == "pic":
                    found[key] = self.LOGOS.index(value)
                elif isinstance(value, str) and value.startswith("#"):
                    found[key] = _rgb565(value)
                elif key not in ("name", "type"):
                    found[key] = value
            return found
        return [Component("page", "page", values(data["page"], {"sta": 1, "bco": 0xFFFF}))] + [
            Component(table["name"], table["type"], values(table, self.DEFAULTS))
            for table in data["component"]]

    def compare(self, values: dict, drawn: Image.Image, screenshot):
        differing = differing_pixels(drawn, screenshot,
                                     dict(values, h=max(values["w"], values["h"])), 2)
        self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


class EditorValueWidgetsTest(unittest.TestCase):
    """The value widgets nxwright draws against the Editor's simulator
    showing them, in the font Sans20, each screenshot cropped to the screen
    (fixtures/value-widgets/): widgets.png, of widgets.toml, the first probe
    of the value widgets; numbers.png, of numbers.toml, the second, of
    numbers and xfloats alone; overflow.png, of overflow.toml, texts and a
    switch's word larger than their room; and gauges.png and needles.png, of
    gauges.toml and needles.toml, gauges of every attribute. The components
    are read as the build reads them, with nxwright's own defaults. Every
    pixel of each widget, and of what it draws past its own rectangle, is
    the same, within the screen's 16-bit colours. On a radio, a switch, and
    a gauge, which the Editor smooths otherwise, where both show one of the
    probe's colours it is the same one, and elsewhere the two come within
    SMOOTHING of each other; but for a few pixels of a gauge's needle, at
    its ends, where the Editor's polygon differs most (NEEDLE_ENDS)."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "value-widgets"
    PAGES = (("widgets.toml", "widgets.png"), ("numbers.toml", "numbers.png"),
             ("overflow.toml", "overflow.png"), ("gauges.toml", "gauges.png"),
             ("needles.toml", "needles.png"))
    DRAWN = ("text", "number", "xfloat", "checkbox", "radio", "dual-state-button", "switch",
             "gauge")
    # The share of a gauge's pixels that may differ past the smoothing: the
    # ends of its needle. The probes' worst, a needle whose widest point
    # passes its foot (`left` 40, `down` 30), had 42 of 22,500.
    NEEDLE_ENDS = 1 / 200
    # The most a radio's smoothed edge differs from the Editor's: the widest
    # gap the fit left, at the edge of its dot.
    SMOOTHING = 140

    def test_as_the_editor_draws_them(self):
        for page_file, screenshot_file in self.PAGES:
            with self.subTest(page=page_file):
                components = page_components(
                    (self.FOLDER / page_file).read_text(encoding="utf-8"), page_file,
                    ResourceNames([], ["Sans20"]),
                    defaults_from_toml(DEFAULTS_FILE.read_text(encoding="utf-8"), "defaults"),
                    "iso-8859-1")
                widgets = [component for component in components[1:]
                           if component.type in self.DRAWN]
                drawn = paint_drawing(draw_page(components[:1] + widgets, Resources()))
                screenshot = read_picture((self.FOLDER / screenshot_file).read_bytes())
                for component in widgets:
                    with self.subTest(component=component.name):
                        self.compare(component, drawn, screenshot)

    def compare(self, component: Component, drawn: Image.Image, screenshot):
        values = component.values
        # A checkbox's tick and a radio's disc go by the width alone.
        height = values["h"]
        if component.type in ("checkbox", "radio"):
            height = max(values["w"], height)
        box = dict(values, h=height)
        if component.type in ("radio", "switch", "gauge"):
            # The rule passes every pixel that is the same in both pictures.
            differing = [(column, row)
                         for column, row in differing_pixels(drawn, screenshot, box, 0)
                         if _smoothed_pixel_differs(screenshot.getpixel((column, row))[:3],
                                                    drawn.getpixel((column, row)), self.PURE)]
        else:
            differing = differing_pixels(drawn, screenshot, box, 2)
        allowed = int(values["w"] * height * self.NEEDLE_ENDS) if component.type == "gauge" else 0
        self.assertLessEqual(len(differing), allowed, "%d pixels differ, such as %s"
                             % (len(differing), differing[:5]))

    # The probes' colours: the page's gray, white, black, red, yellow, the
    # dark edge, and a gauge's green and blue.
    PURE = [(131, 129, 131), (255, 255, 255), (0, 0, 0), (255, 0, 0), (255, 255, 0),
            (66, 69, 66), (0, 130, 0), (0, 0, 255)]


def _smoothed_pixel_differs(shown: tuple, ours: tuple, colours: list) -> bool:
    """Whether a pixel nxwright draws of a widget the Editor smooths
    otherwise, `ours`, differs from the Editor's, `shown`. Where both are
    one of `colours`, within 3, they must be the same one. Elsewhere, at an
    edge one of them smooths, they must come within
    EditorValueWidgetsTest.SMOOTHING of each other."""
    both = [next((index for index, one in enumerate(colours)
                  if max(abs(a - b) for a, b in zip(colour, one)) <= 3), None)
            for colour in (shown, ours)]
    if None in both:
        return max(abs(a - b) for a, b in zip(shown, ours)) > EditorValueWidgetsTest.SMOOTHING
    return both[0] != both[1]


class _NotoSans(Resources):
    """Resources whose font 0 is NotoSans20."""
    NOTO_SANS = decode_font((FONTS / "NotoSans20.zi").read_bytes())

    def font(self, font_id):
        if font_id != 0:
            raise NxwrightError("the folder has no font %d" % font_id)
        return self.NOTO_SANS


class EditorBordersTest(unittest.TestCase):
    """Texts placed at a corner of a component with a border, against the
    Editor's simulator showing them, cropped to the screen
    (fixtures/borders/), their text at the top left (`xcen` and `ycen` 0) or
    the bottom right (2), in NotoSans20 on a gray page: borders.png, of
    borders.toml, texts and a button of `style` 1, `borderw` 2 and 6, and a
    text of the 3D `style` 2; widgets.png, of widgets.toml, numbers,
    xfloats, and dual-state buttons, with borders or 3D edges, at each
    `val`. The Editor places the text inside the border, a 3D edge's pixel
    included. Every pixel of each is the same, within the screen's 16-bit
    colours. The combo boxes of borders.toml are combo_boxes' own."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "borders"
    PAGES = ("borders", "widgets")
    DRAWN = ("text", "button", "number", "xfloat", "dual-state-button")

    def test_text_inside_the_border(self):
        for page in self.PAGES:
            with self.subTest(page=page):
                self.compare(page)

    def compare(self, page: str):
        components = page_components(
            (self.FOLDER / (page + ".toml")).read_text(encoding="utf-8"), page + ".toml",
            ResourceNames([], ["NotoSans20"]),
            defaults_from_toml(DEFAULTS_FILE.read_text(encoding="utf-8"), "defaults"),
            "iso-8859-1")
        drawn_ones = [component for component in components[1:]
                      if component.type in self.DRAWN]
        drawn = paint_drawing(draw_page(components[:1] + drawn_ones, _NotoSans()))
        screenshot = read_picture((self.FOLDER / (page + ".png")).read_bytes())
        for component in drawn_ones:
            with self.subTest(component=component.name):
                differing = differing_pixels(drawn, screenshot, component.values, 2)
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


class _Logos(DrawingResources):
    """Pictures alone, from {name: an RGBA image}, their IDs in its order."""

    def __init__(self, pictures: dict):
        self.pictures = pictures
        self.names = list(pictures)

    def picture(self, picture_id):
        return self.names[picture_id] if 0 <= picture_id < len(self.names) else None

    def picture_size(self, picture_id):
        name = self.picture(picture_id)
        return (self.pictures[name].width, self.pictures[name].height) if name else None


class HiddenTest(unittest.TestCase):

    def test_a_hidden_component_keeps_its_id(self):
        page = Component("page", "page", {"x": 0, "y": 0, "w": 100, "h": 50})
        first = component("a", "text", sta=1, bco=0xf800, font=0, txt="")
        second = component("b", "text", sta=1, bco=0x001f, font=0, txt="")
        drawing = draw_page([page, first, second], Resources(), [("ref", "2")], hidden={"a"})
        self.assertEqual([shape["component"] for shape in drawing["shapes"]], ["b"])
        self.assertEqual([entry["name"] for entry in drawing["components"]], ["page", "b"])


class TextPictureTest(unittest.TestCase):
    """Sans20's "!": 4 pixels wide, its ink in columns 1 and 2, rows 5 to 14."""

    def ink(self, text: str, width: int = 20, height: int = 20, **values) -> list:
        """Returns the (x, y) of the inked pixels of a text picture."""
        values.setdefault("xcen", 0)
        values.setdefault("ycen", 0)
        pixels = text_picture(text, SANS20, "iso-8859-1", values, width, height, WHITE)
        return [(index % width, index // width) for index in range(width * height)
                if pixels[index * 4 + 3]]

    def bounds(self, ink: list) -> tuple:
        xs, ys = [x for x, _ in ink], [y for _, y in ink]
        return min(xs), max(xs), min(ys), max(ys)

    def test_alignments(self):
        for xcen, left in ((0, 1), (1, 9), (2, 17)):
            with self.subTest(xcen=xcen):
                self.assertEqual(self.bounds(self.ink("!", xcen=xcen))[0], left)
        for ycen, top in ((0, 5), (1, 15), (2, 25)):
            with self.subTest(ycen=ycen):
                self.assertEqual(self.bounds(self.ink("!", height=40, ycen=ycen))[2], top)

    def test_spacing_between_characters(self):
        ink = self.ink("!!", spax=3)
        self.assertEqual(sorted({x for x, _ in ink}), [1, 2, 8, 9])

    def test_line_breaks_and_spacing_between_lines(self):
        ink = self.ink("!\r\n!", height=50, spay=2)
        self.assertEqual(self.bounds(ink)[2:], (5, 36))
        # A carriage return or a line feed alone breaks no line, and shows
        # as a space, as the Editor's simulator drew them
        # (EditorAssumptionsTest).
        for text in ("!\r!", "!\n!"):
            with self.subTest(text=text):
                self.assertEqual(self.ink(text, width=30, height=50, spay=2),
                                 self.ink("! !", width=30, height=50, spay=2))

    def test_wrapping(self):
        self.assertEqual(self.bounds(self.ink("!!!!", width=9))[3], 14)
        self.assertEqual(self.bounds(self.ink("!!!!", width=9, height=50, isbr=1))[3], 34)

    def test_wrapping_is_by_character(self):
        # "! !" fits in 14: the second line holds only the "!" that did not
        # fit, where wrapping at the space would have moved "!!" down.
        ink = self.ink("! !!", width=14, height=50, isbr=1)
        second_line = sorted({x for x, y in ink if y >= 25})
        self.assertEqual(second_line, [1, 2])

    def test_lines_are_aligned_as_one_block(self):
        # Right-aligned, "!" starts where "!!" starts, not where it ends.
        ink = self.ink("!\r\n!!", height=50, xcen=2)
        self.assertEqual(sorted({x for x, y in ink if y < 20}), [13, 14])
        self.assertEqual(sorted({x for x, y in ink if y >= 20}), [13, 14, 17, 18])

    def test_a_password_shows_stars(self):
        self.assertEqual(self.ink("ab", pw=1), self.ink("**"))

    def test_cut_to_the_component(self):
        self.assertEqual(self.ink("!", width=2), [(1, y) for y in range(5, 15)])

    def test_missing_characters(self):
        # A tab, which Sans20 lacks, shows as its first character, the space;
        # a character the encoding cannot write is refused.
        self.assertEqual(self.ink("!\t!"), self.ink("! !"))
        with self.assertRaisesRegex(MissingCharacter, "iso-8859-1 cannot write"):
            self.ink("ā")


class EditorScreenshotTest(unittest.TestCase):
    """The texts of a test page, fixtures/placing/placing.toml, against the
    Editor's simulator showing it, fixtures/placing/editor.png. The screenshot
    starts 10 pixels into the page, right and down, and its program set
    `dim = 80`, which dims every colour to 80%: the texts' white background
    shows as 204."""
    PLACING = Path(__file__).resolve().parent / "fixtures" / "placing"
    FONTS = {"Sans20": SANS20, "Sans100": decode_font((FONTS / "Sans100.zi").read_bytes())}
    START, WHITE = 10, 204

    def test_each_text_as_the_editor_places_it(self):
        screenshot = read_picture((self.PLACING / "editor.png").read_bytes())
        page = tomllib.loads((self.PLACING / "placing.toml").read_text(encoding="utf-8"))
        texts = [entry for entry in page["component"] if entry["font"] in self.FONTS]
        self.assertGreater(len(texts), 10)
        for entry in texts:
            with self.subTest(text=entry["name"]):
                width, height = entry["w"], entry["h"]
                pixels = text_picture(entry["txt"], self.FONTS[entry["font"]], "iso-8859-1",
                                      entry, width, height, (0, 0, 0))
                # A border, drawn apart from the text, is left out.
                inset = entry.get("borderw", 0) if entry.get("style") else 0
                differing = []
                for y in range(max(inset, self.START - entry["y"]), height - inset):
                    for x in range(inset, width - inset):
                        drawn = round(pixels[(y * width + x) * 4 + 3] * 7 / 255)
                        red, green, blue, _ = screenshot.getpixel(
                            (entry["x"] + x - self.START, entry["y"] + y - self.START))
                        shown = round(7 * (self.WHITE - (red + green + blue) / 3) / self.WHITE)
                        if abs(drawn - shown) > 1:
                            differing.append((x, y))
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


class EditorUtf8ScreenshotTest(unittest.TestCase):
    """The texts of fixtures/utf-8-text/texts.page.toml, in a utf-8 project,
    against the Editor's simulator showing them, editor.png, cropped to the
    screen. Their font, NotoSans20-cyrillic (test_zi_font.py), holds U+0000
    to U+007F and U+0400 to U+04FF. Between "А" and "Б", each text holds
    characters it lacks: α and é, which its table holds but not chosen, and
    U+1F600, past the table's end. The simulator drew each as nothing, half
    the height wide."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "utf-8-text"

    def font_named(self, name: str):
        """The decoded font that a text of the page names."""
        return decode_font(utf8_fixture("NotoSans20-cyrillic"))

    def test_each_text_as_the_editor_draws_it(self):
        screenshot = read_picture((self.FOLDER / "editor.png").read_bytes())
        page = tomllib.loads((self.FOLDER / "texts.page.toml").read_text(encoding="utf-8"))
        fonts = {name: self.font_named(name) for name in {entry["font"]
                                                          for entry in page["component"]}}
        for entry in page["component"]:
            with self.subTest(text=entry["txt"]):
                width, height = entry["w"], entry["h"]
                pixels = text_picture(entry["txt"], fonts[entry["font"]], "utf-8", entry, width,
                                      height, (0, 0, 0))
                differing = []
                for y in range(height):
                    for x in range(width):
                        drawn = round(pixels[(y * width + x) * 4 + 3] * 7 / 255)
                        red, green, blue, _ = screenshot.getpixel((entry["x"] + x, entry["y"] + y))
                        shown = round(7 * (255 - (red + green + blue) / 3) / 255)
                        if abs(drawn - shown) > 1:
                            differing.append((x, y))
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


class EditorChosenCharactersScreenshotTest(EditorUtf8ScreenshotTest):
    """The texts of fixtures/chosen-characters-text/texts.page.toml, in a
    utf-8 project, against the Editor's simulator showing them, editor.png,
    cropped to the screen. Their fonts' tables hold only their chosen
    characters (test_zi_font.py, ChosenCharactersTest), and most texts hold
    characters their font lacks, such as "q", "ÿ", and U+1F600. The
    simulator drew each as the font's first character: the space, or in
    NotoSans32-u0001 U+0001's box."""
    FOLDER = Path(__file__).resolve().parent / "fixtures" / "chosen-characters-text"

    def font_named(self, name: str):
        return decode_font(chosen_characters_fixture(name))


class PreviewServerTest(FolderTestCase):
    """The folder's page0 with a text in Sans20, and a picture."""

    def setUp(self):
        super().setUp()
        (self.root / "fonts").mkdir(exist_ok=True)
        (self.root / "fonts" / "Sans20.zi").write_bytes((FONTS / "Sans20.zi").read_bytes())
        (self.root / "pictures").mkdir()
        (self.root / "pictures" / "dot.png").write_bytes(write_png(1, 1, b"\0\0\0\xff"))
        self.write("app.toml", fonts_first(self.text("app.toml"), ["Sans20"])
                   .replace("pictures = []", 'pictures = ["dot"]'))
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml").replace(
            'name = "title"', 'name = "title"\nfont = "Sans20"\nsta = 2\npic = "dot"'))
        self.previews = Previews()

    def draw(self, path: str = "pages/page0.page.toml"):
        return self.previews.drawing(self.root, path, folder_reader(self.root))

    def test_a_drawing(self):
        drawing = self.draw()
        self.assertEqual(drawing["page"], "page0")
        title = [shape["kind"] for shape in drawing["shapes"] if shape["component"] == "title"]
        self.assertEqual(title, ["picture", "text"])
        dot = self.root / "pictures" / "dot.png"
        self.assertEqual(drawing["pictureFiles"],
                         {"dot": {"path": str(dot), "version": str(dot.stat().st_mtime_ns)}})
        self.assertEqual(self.draw("pages/page0.nx")["page"], "page0")

    def test_pictures_opaque_by_the_screens_series(self):
        # The folder's screen, an Intelligent NX8048P050, keeps a picture's
        # alpha; an Enhanced one stores it white.
        def opaque():
            return [shape.get("opaque") for shape in self.draw()["shapes"]
                    if shape["kind"] == "picture"]
        self.assertEqual(opaque(), [None])
        self.write("app.toml", self.text("app.toml").replace('"NX8048P050"', '"NX8048K050"'))
        self.assertEqual(opaque(), [True])

    def test_only_a_pages_own_files(self):
        self.assertIsNone(self.draw("app.toml"))
        self.assertIsNone(self.draw("pages/lib/units.nx"))
        # A .nx file of pages/ that no page owns.
        self.write("pages/notes.nx", "")
        self.assertIsNone(self.draw("pages/notes.nx"))

    def test_a_page_file_that_does_not_read(self):
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml") + "\n[[component]\n")
        drawing = self.draw()
        self.assertEqual(drawing["page"], "page0")
        self.assertIn("pages/page0.page.toml", drawing["error"])

    def test_a_replaced_font_draws_its_new_glyphs(self):
        before = self.draw()["shapes"][-1]["image"]
        # The same name, now a font whose every glyph is a full 20 by 20 square.
        square = pairs_glyph([7] * 400)
        (self.root / "fonts" / "Sans20.zi").write_bytes(
            font_block([(code, 20, 0, 0, square) for code in range(32, 127)], 20))
        self.assertNotEqual(self.draw()["shapes"][-1]["image"], before)

    def test_a_utf8_folders_text_in_its_own_font(self):
        self.write("app.toml", self.text("app.toml").replace('"iso-8859-1"', '"utf-8"'))
        (self.root / "fonts" / "Sans20.zi").write_bytes(utf8_fixture("NotoSans20-cyrillic"))
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml").replace(
            'txt = "x"', 'txt = "Жук"'))
        drawing = self.draw()
        self.assertEqual(drawing["notes"], [])
        self.assertEqual([shape["kind"] for shape in drawing["shapes"]
                          if shape["component"] == "title"], ["picture", "text"])
        # A full table draws a code point not chosen as nothing, and one past
        # U+FFFF alike; the note names them.
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml").replace(
            'txt = "Жук"', 'txt = "Жα😀α"'))
        self.assertEqual(self.draw()["notes"],
                         ["title: font Noto20Cyr lacks U+03B1 and U+1F600; the screen draws "
                          "nothing in their place, half the height wide"])

    def test_a_gb2312_folders_text_in_its_own_font(self):
        self.write("app.toml", self.text("app.toml").replace('"iso-8859-1"', '"gb2312"'))
        (self.root / "fonts" / "Sans20.zi").write_bytes(gb2312_font())
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml").replace(
            'txt = "x"', 'txt = "中a"'))
        drawing = self.draw()
        self.assertEqual(drawing["notes"], [])
        self.assertEqual([shape["kind"] for shape in drawing["shapes"]
                          if shape["component"] == "title"], ["picture", "text"])
        # Text in another encoding than the font's: 81 40 falls before the
        # table's first entry, which is drawn in its place; the note names it
        # by its bytes.
        self.write("app.toml", self.text("app.toml").replace('"gb2312"', '"iso-8859-1"'))
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml").replace(
            'txt = "中a"', 'txt = "\\u0081@"'))
        self.assertEqual(self.draw()["notes"],
                         ["title: font Zh lacks 81 40; the screen draws its first character, "
                          "a1 a1, in its place",
                          "title: font Zh is in gb2312, the project in iso-8859-1"])

    def test_a_character_its_fonts_grid_has_no_place_for(self):
        # In ks_c_5601-1987, the font's grid ends at row c8: the Hanja 伽 (ca
        # a1) falls on an ascii entry, ~, and 漢 (f9 d3) past the table, on
        # its first entry, the ideographic space, named by its bytes.
        self.write("app.toml", self.text("app.toml").replace('"iso-8859-1"',
                                                             '"ks_c_5601-1987"'))
        (self.root / "fonts" / "Sans20.zi").write_bytes(grid_font("ks_c_5601-1987", name="Ko"))
        page = "pages/page0.page.toml"
        self.write(page, self.text(page).replace('txt = "x"', 'txt = "가伽"'))
        self.assertEqual(self.draw()["notes"], ["title: the font Ko has no place for 伽 (ca a1), "
                                                "which the screen shows as ~"])
        self.write(page, self.text(page).replace('txt = "가伽"', 'txt = "伽漢"'))
        self.assertEqual(self.draw()["notes"],
                         ["title: the font Ko has no place for these characters, which the screen "
                          "shows otherwise: 伽 (ca a1) as ~ and 漢 (f9 d3) as a1 a1"])
        # In shift-jis, a half-width katakana is one byte, which the screen
        # takes as a pair with the byte after it: ﾁ (c1) and A give 81 41.
        self.write("app.toml", self.text("app.toml").replace('"ks_c_5601-1987"', '"shift-jis"'))
        (self.root / "fonts" / "Sans20.zi").write_bytes(grid_font("shift-jis", name="Ja"))
        self.write(page, self.text(page).replace('txt = "伽漢"', 'txt = "ﾁA"'))
        self.assertEqual(self.draw()["notes"], ["title: the font Ja has no place for ﾁ (c1), "
                                                "which the screen shows, with the character "
                                                "after it, as 、 (81 41)"])
        # Before a character of two bytes, it takes that character's first
        # byte, and the screen reads on out of step: 亜 (88 9f) and A are not
        # drawn as themselves, and are not named apart.
        self.write(page, self.text(page).replace('txt = "ﾁA"', 'txt = "ﾁ亜A"'))
        self.assertEqual(self.draw()["notes"], ["title: the font Ja has no place for ﾁ (c1), "
                                                "which the screen shows, with the text after "
                                                "it, as other characters"])
        # In gb2312, a folder stores its texts by GBK, whose 丂 (81 40) lies
        # before the grid's first row: the screen shows the first entry.
        self.write("app.toml", self.text("app.toml").replace('"shift-jis"', '"gb2312"'))
        (self.root / "fonts" / "Sans20.zi").write_bytes(gb2312_font())
        self.write(page, self.text(page).replace('txt = "ﾁ亜A"', 'txt = "中丂"'))
        self.assertEqual(self.draw()["notes"], ["title: the font Zh has no place for 丂 (81 40), "
                                                "which the screen shows as a1 a1"])

    def test_a_font_nxwright_cannot_decode_stood_in_for_at_its_height(self):
        # Sans20 marked as in big5 (16), whose fonts nxwright does not
        # decode: the ordinary font stands in at the height its header
        # gives, not at the text's.
        block = bytearray((FONTS / "Sans20.zi").read_bytes())
        block[4] = 16
        (self.root / "fonts" / "Sans20.zi").write_bytes(bytes(block))
        title = [shape for shape in self.draw()["shapes"] if shape["component"] == "title"][-1]
        self.assertEqual((title["kind"], title["size"]), ("plainText", 20))
        self.assertNotEqual(title["h"], 20)

    def test_the_servers_request(self):
        connection = initialized()
        connection.handle({"jsonrpc": "2.0", "id": 2, "method": "nxwright/pageDrawing",
                           "params": {"textDocument": {"uri": uri_of(self.root / "pages/page0.page.toml")}}})
        self.assertEqual(connection.sent[-1]["result"]["page"], "page0")


if __name__ == "__main__":
    unittest.main()
