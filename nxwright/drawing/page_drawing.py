"""Drawing a page as the screen shows it, for the page preview of a code
editor: what to paint, in screen pixels.

The drawing is computed from a page's Components (page_source.py) and their
values, as the screen stores them. The preview takes those of the page's
file; a simulation could give the values its code has left. It is a dict,
ready to send as JSON:
  - "width", "height": the page's size;
  - "transparent": whether the page has no background, and is drawn
    over what the screen showed before;
  - "shapes": what to paint, in order, each naming its "component", with a
    "kind" and the rectangle "x", "y", "w", "h" it covers:
      - "colour": filled with "colour", as "#rrggbb";
      - "picture": the picture "picture" (its name), its pixel ("sx", "sy")
        at the rectangle's corner, cut to the rectangle; with "opaque" true,
        a picture of the folder on a screen that stores pictures without
        alpha, which the webview flattens on white, as the build stores it;
        with "card" true, a file of an SD card, shown in its own colours;
      - "text": the picture "image", a "data:" URL of PNG data, or of JPEG
        data, in place, cut to the rectangle, in its own colours: a text, a
        rounded progress bar, a QR code, a line or circle a drawing command
        painted, or a frame of an animation or a video;
      - "plainText": "text" in an ordinary font, for a font that cannot be
        drawn: "colour", "size" in pixels, and "xcen" and "ycen";
      - "outline": a frame, with a "label";
      - "backdrop": on a page without background, the screen as the page
        found it, which the webview keeps, shown again, or black after a
        start;
    and, of any kind, "aph", from 1 to 126, when its component is drawn
    less than opaque, which the webview paints it as;
    and, on a "picture" or a "text", "rotation", when the stored picture
    is turned for a screen turned that many degrees, which the webview
    turns back, from the shape's top left, cut to its size, as the screen
    does: a card's file in its component's box, its padding shown (below);
    a frame in the frame's own box, its padding not shown
    (media_drawing.py);
  - "components": the page and each component with a place on the screen,
    in ID order: "name", "type", "x", "y", "w", "h", "global", whether its
    `vscope` is 1, global, so that other pages' code can reach it, and
    "locked", whether its `lockobj` is 1, which the Editor's design view
    shows with a padlock, and "group", its group as "groupid0/groupid1",
    when it is in one (component_groups.py);
  - "unplaced": each component without a place, such as a timer or a
    variable, in ID order: "name", "type", and "global";
  - "notes": what could not be drawn as the screen would, and why.

Components are painted in ID order, the page first. What each attribute
means was worked out from files the Editor saved, the demo's among them:
`sta` chooses a component's background, 0 the part of the picture `picc`
under it, 1 the colour `bco`, and 2 the picture `pic` at its corner; a
page's `sta` 2 is the picture `pic`, and 1 the colour `bco`. A page's
`sta` 0 draws no background: the screen draws the page over what it showed
before, as a dialog opens over the page that opened it. So does a page's
`sta` 2 with no picture, or one the folder does not have, as the user saw
the Editor do. A component's `sta` 3 draws no background, as the Editor's
simulator showed the page through a text
(tests/fixtures/drawing-assumptions/). Texts are drawn in their colour
`pco`, in the font `font` (text_pictures.py), placed and cut inside their
border (border_width), as the Editor's simulator places them, at a corner
as centred (tests/fixtures/borders/). Picture components draw
`pic`, and crop components the part of `picc` under them, moved right and
down by their `vvs0` and `vvs1`. A hotspot, which the screen does not show,
is not drawn.

A component of `style` 1 has a border `borderw` pixels wide, inside its
rectangle, in the colour `borderc`, on a colour background (`sta` 1)
alone, as does a checkbox, which has no `sta`. On a crop, a picture, or no
background (`sta` 0, 2, and 3), the Editor's simulator drew no border on a
text, a button, or a number, and placed their text at the component's
corner, not inside a border (tests/fixtures/drawing-assumptions/); it drew
none on a keypad's buttons on pictures, nor on a dual-state button, a
scrolling text, an xfloat, a combo box, a sliding text, a file browser, a
data record, or a select, on any of the three (tests/fixtures/
drawing-assumptions/, page7 and page8): every type with a `style` and a
`sta`.

The 3D styles have edges a pixel wide, whatever `borderw` and `borderc`
say, of two fixed colours, a dark gray and a light gray (DARK_EDGE,
LIGHT_EDGE): style 2, sunk, has the dark edge on its top and left and the
light one on its bottom and right, and style 3, raised, the other way
round; the left and right edges run the full height, taking the corners.
Style 4, a button's and a dual-state button's, is raised, and sunk in
their second look: a button's while it is pressed, a dual-state button's
while its `val` is 1. They are drawn only on a colour background (`sta`
1). A pressed button shows its pressed colours and pictures, `bco2`,
`pco2`, `pic2`, and `picc2`, whatever its style. All of this matched the Editor's simulator
pixel for pixel (tests/fixtures/styles/).

A slider draws its track, the filled part of it from its start to the
knob's middle, and the knob, `wid` by `hig`, centred across the track, its
left edge at (val - minval) / (maxval - minval) of the way from the start
to the end less its width, cut toward zero. With `mode` 1, the slider is
vertical, filled from the bottom. After a touch, the knob stands where
the touch put it, until code stores `val` (`scrolled`, Simulation._slide),
as the Editor's simulator drew it (tests/fixtures/drawing-assumptions/,
page40).

A track of pictures (`sta` 0, the part of `picc` under it, or 2, the
picture `pic`) covers the slider, its filled part alike from `picc1` or
`pic1`, as the Editor showed for the demo's. A track of colours (`sta` 1,
`bco`, filled with `bco1`) is a bar `ch` hundredths of the slider's breadth,
cut toward zero (none at 0), centred across it, one pixel inside its ends,
or two at its bottom when vertical. `dis` rounds its ends, by `dis`
hundredths of its breadth less a pixel, at most half of that, drawn as a
progress bar is: square under LEAST_ROUNDING pixels, else smoothed.

The knob is round (`psta` 0), the picture `pic2` (1), or square (2), in the
colour `pco`, as the Editor describes `psta`. `wid` or `hig` 255 is the
knob picture's size, or the slider's breadth; 0 draws no knob. A round knob
is an ellipse, smoothed. Its even size counts one less, given or chosen by
the Editor, in its drawing and its place alike, so a knob 40 high is drawn
39 high. All of this matched the Editor's simulator (tests/fixtures/slider/
and tests/fixtures/slider-knobs/) where it shows its own colours, and its
smoothed edges within 80, black on white (slider_drawing.py).

A waveform draws its background as a slider's track, then, when `gdw` or
`gdh` is not 0, its grid in the colour `gdc`: a line up and down at its
left edge and every `gdw` pixels right of it, and a line across at its
bottom row and every `gdh` pixels above it. A simulation gives the points
its code added to each channel: each of its first `ch` channels is drawn
in its colour, `pco0` to `pco3`, a point per column. The points `add` gives
a channel past them are not drawn, as in the Editor's simulator
(tests/fixtures/drawing-assumptions/, page6). With `dir` 0, the default, a new
point enters at the left and pushes the others right; with `dir` 1, at the
right, pushing them left, the first point at the left edge until they
fill the waveform; with `dir` 2, in the same order, the last point at the
right edge. The Editor refuses other values as it compiles, and the build
too (page_source._RANGES); code cannot change `dir` at all, as the build
refuses such a line (attribute_descriptions.code_cannot_change). A value
of v is v * `dis` / 100 pixels up from the bottom row, cut toward zero,
and each point is joined to its neighbour on the left by a line in its
own column.
The points matched the Editor's simulator pixel for pixel, at `dis` 100
and `dir` 0 and 1, on the demo's Day page (tests/fixtures/waveform/); so
did the grid, `dis` 33, 50, and 200, and `dir` 2
(tests/fixtures/drawing-assumptions/). It is drawn in waveform_drawing.py.

A progress bar fills the part `val` of 100 of its length, cut toward zero:
from the left, or from the bottom when `dez` is 1. With `sta` 1, the filled
part shows the picture `ppic`, and the rest `bpic`, each at the bar's
corner. Otherwise they are the colours `pco` and `bco`, and `dis` rounds
the corners, by `dis` hundredths of half the bar's breadth less a pixel:
the Editor's simulator then draws the rest of the bar from a cap's width
before the fill's end, and the fill over it, each half a pixel inside the
bar, with smoothed edges. A rounding under LEAST_ROUNDING pixels is drawn
square. The bars matched its screenshot (tests/fixtures/progress/) to the
pixel, but for the smoothing of rounded edges, which the drawing does
alike on each corner, where the Editor's corners are not alike. A bar of
pictures is drawn square, whatever its `dis`, and a part that is not a
whole number of pixels is cut toward zero, across and down, as the
Editor's simulator drew them (tests/fixtures/drawing-assumptions/). It is
drawn in progress_bar_drawing.py.

An external picture shows a file of the screen's SD card, `path`: a PNG,
a JPEG, or PictureBox's .xi file (project/media_files.py, read_card_picture).
When the drawing's resources find that file, as a simulation's do on a card
given a folder, its picture shape is marked "card", and carries the
screen's rotation. The Editor's simulator showed each kind of file in its
own colours, rather than the screen's 16 bits, and with its transparency.
The screen draws
the file's pixels as they are stored, so a file for a turned screen is
stored turned: the webview turns the stored pixels back by the screen's
rotation, so that such a file shows upright, as the user sees it. The
turned picture's top left corner is at the component's, and the component
cuts it at its right and bottom. The Editor's simulator showed each kind of
file so at 90, 180, and 270 degrees, whatever rotation a .xi file was made
for: one stored upright then shows turned
(tests/fixtures/drawing-assumptions/turned/). Otherwise nothing is drawn;
so the preview, which has no card, draws none.

A file browser draws its background and its border as a text does, then
the entries a simulation lists (the preview, which has no SD card, lists
none). Each entry is its icon with its name under it: `pic1` for a folder;
for a file, the picture `vvs2` gives its type ("*.txt/2*.data/3", matched
as `filter` is), else `pic2`. The name is drawn as a text with `isbr` 1 is,
in the browser's font and `pco`, wrapped at the icon's width, centred as a
block, `dis` lines high. The columns are an icon's width and `spax` apart,
as many as fit inside the border, centred on the width; the rows an icon's
height, `dis` lines, and `spay` apart, from inside the border
(browser_layout). The entries are scrolled up by `val_y`, and cut to the
inside of the border, less a row at the bottom. The selected entry (`val`)
is drawn over a box of `bco2` as large as its icon and name, its name in
`pco2`. With `left` 2, or `left` 1 while a touch scrolls it, the scroll
bar's thumb, a fixed size and a grey drawn half opaque over what is under
it (scroll_thumb), sits inside the border at the right, placed by `val_y`
of `maxval_y`; none shows when every entry fits, as for a sliding text's.
All of this matched the Editor's simulator (tests/fixtures/files/) but for
its 16-bit colours. The icons are as large as the file icon, `pic2`, each
cut to its size, and laid out by it; with no file icon, no entry is drawn
(browser_icon_size), as the Editor's simulator drew icons of other sizes,
and none without one (tests/fixtures/drawing-assumptions/, page16). It is
drawn in file_browser_drawing.py.

A select draws its background and its border, then the lines of `path`,
`hig` apart, each centred in a band `hig` high: the line `val` picks in
the middle band, the others before and after it, repeating round. A line
is in `pco2` where it is the one `val` picks, wherever it repeats, else in
`pco`. On a colour background (`sta` 1), within `hig` pixels of the
select's top or bottom, a line's pixel keeps only its distance from that
edge in `hig`ths of its colour, fading into what is under it; on a crop, a
picture, or none, the Editor's simulator drew the lines unfaded
(tests/fixtures/drawing-assumptions/). With `dis` 1, a rule of `pco1`
runs along the top and bottom rows of the middle band. While a press
moves the lines, they are drawn moved by as much; the rules stay. These
matched the Editor's simulator (tests/fixtures/files/), but for the lines
moving, which the screenshots could not show. A band the screen's right
or bottom edge cuts has its line placed in the part the screen shows, at
the part's top when the line is taller, as a text taller than its
component is placed. A band the screen's top cuts is not placed so: on a
select near the top, the Editor showed none of such a band's line, where
placing it in the part shown would have. So the Editor's simulator drew
them (tests/fixtures/drawing-assumptions/, page17 to page21). A select
past the screen's left, as while an opening effect slides it in, keeps
its lines in their whole bands, as an open combo box's item there keeps
its text in the whole item (combo_box_drawing.py). It is drawn in
select_drawing.py.

A QR code draws a square of `bco` as high as the component is wide,
whatever its height, so past its bottom when it is wider than high. On it,
`dis` pixels inside, is the QR code of `txt` in the project's encoding
(project/qr_code.py), `w` - 2 * `dis` pixels wide, its dark modules in
`pco`. Module i of n covers the pixels from ceil(i * that width / n) up to
ceil((i + 1) * that width / n), across and down. The run of dark modules
in the code's last column that ends at its bottom right corner lacks the
code's last column of pixels. An empty `txt`, or a code of less than a
pixel a module, draws no code. With `sta` 1, the picture `pic` is drawn
over it at its own size, in the square's middle, its corner rounded
down, when each of its sides is at most the code's width less
LOGO_MARGIN; past it, no logo is drawn. All of this matched the Editor's
simulator pixel for pixel (tests/fixtures/qr-codes/, and drawing-
assumptions/, for logos at and past the bound at three sizes), but for the
codes of the few texts it splits otherwise than nxwright does
(qr_code_drawing.py).

A number and an xfloat are drawn as a text is, their `val` written out in
place of `txt` (number_drawing.py).

A checkbox draws a box of `bco` with its `style`'s edges, and when `val` is
1 a square tick of `pco` (checkbox_drawing.py). A radio draws a smoothed
disc as wide as itself, ringed in the dark edge colour, and when `val` is 1
a dot of `pco` (radio_drawing.py). Both go by their width alone, so one
wider than high draws past its bottom, as the Editor's simulator does.

A dual-state button is drawn as a button is, in its second look, as a
button shows it while pressed, while its `val` is 1
(dual_state_button_drawing.py).

A switch draws a pill of `bco` or, while on, `bco2`, rounded as a progress
bar is, a knob at its start or, while on, its end, and the word of `txt` its
state chooses, in `pco1` (switch_drawing.py).

A gauge draws its background, its needle at `val` plus `format` degrees, 0
pointing left, as a smoothed polygon, and the disc at its middle
(gauge_drawing.py).

A scrolling text is drawn as a text is, its text where a simulation has
moved it, cut to its rectangle; the preview, which runs nothing, draws the
text at rest, where a text would show it (scrolling_text_drawing.py).

An animation (gmov) and a video draw the frame their `tim` falls on, at
their top left corner, in the frame's own colours (media_drawing.py).

A sliding text draws its lines from its top inside its border, scrolled up
by `val_y` and cut to that inside, and its scroll bar's thumb by `left`
(sliding_text_drawing.py).

A combo box draws its box, rounded by `dis`, with its text and an arrow
pointing the way its list opens, and, while `down` is 1, its list of the
items of `path`, beyond its rectangle, in ID order with the rest
(combo_box_drawing.py).

A data record draws a table: a row of titles, then a row per record of its
data file, the chosen one in its own colours, scrolled by `val_y` and
`val_x`. The preview, which has no SD card, draws the titles and the lines
alone (data_record_drawing.py).

A component of any other type with a place is drawn as an outline,
labelled with its name and type.

A component is drawn as opaque as its `aph`, out of 127 (OPAQUE): each of
its shapes is marked with it, and painted that opaque over what lies under
it, in turn, as the Editor's simulator blends a text's background, then its
words. A component of `aph` 0 draws nothing; a page and a hotspot are drawn
opaque, as the Editor's panel never shows their `aph`, and a page of `aph`
50 looked no different in the Editor's simulator; and so is an outline,
which stands in for what cannot be drawn. The Editor blends
each channel as under + (colour - under) * aph / 127, the change cut toward
zero; a canvas blends within a level of it.

A simulation also gives what the drawing commands painted, in order, as
the test machine records it (testing/editor_machine.py, "painted"). It
marks ("redraw", component) where the code changed a component, even to
the value it had, or where a button was pressed or released. At a mark,
the page's own background comes back within the component's box, and
within the box of each shown component linked to it by overlaps: each
component it meets, each component those meet, and so on. Then those
components are drawn again whole, in ID order, their earlier drawing
gone. So what was painted there goes, a smoothed edge does not blend
twice, and a shortened text's old words do not show. Where code moved or
resized a component, ("left", component, box) marks the box it left. The
page's background comes back there too, and the components linked to
that box are drawn again. The Editor's simulator drew a text, a number,
a button, a progress bar, a checkbox, an xfloat, and a slider so, each
over a `fill` (tests/fixtures/drawing-assumptions/, page29 to page33), a
`ref` alike (page34), texts linked in turn (page36 and page38), and a
button pressed and released, and a slider pressed on its track (page40).
On a page of no background, a "backdrop" shape brings back the screen as
the page found it instead, as the Editor's simulator showed, the page
entered after a `fill` or not (page35). A checkbox a press toggles, the
simulation's own change, is drawn so too (page44); a drag's moves are
assumed alike. A sliding text, a file browser, or a data record that is
pressed is not drawn again until a touch scrolls it or the touch ends,
as in that simulator (page44 and page45). So too, as that simulator
showed: a box a moved component left links in turn too (page46); the
page's background comes back under the boxes of those linked in turn
(page47); and a hidden component, not drawn, links none in turn
(page48). The page drawn again is drawn over everything, then each of
its components, as the Editor's simulator drew it after a `fill`
(page36). On a page of no background, what drawing commands painted
before it is cut, so the screen as the page found it shows under its
components, as in that simulator (page35).

Between `ref_stop` and `ref_star`, a component code changes keeps showing
as it was, and one `vis` hides keeps showing, until `ref_star`; one `vis`
shows is drawn at once. A page change meanwhile leaves the page before
showing until `ref_star`, which draws the new page with what its code
painted (the simulation's drawing_inputs). The Editor's simulator showed
it so (tests/fixtures/drawing-assumptions/, page7 and page30). A
component that is not shown is not drawn again, and what was painted
where it is stays, as the Editor's simulator showed for a hidden text
that code set and moved (page37).

What drawing commands paint is drawn pixel by pixel. `fill` fills its
rectangle, and `draw` outlines one from corner to corner, both included. A
line steps a pixel at a time along its longer side, from end to end, the
other coordinate moving by the largest whole number below the next step's
share of the way. A circle
of radius r steps round its centre as the midpoint method does, filled by
`cirs`; the Editor's simulator smooths circles' edges, which the drawing
does not. `xstr` draws its text as a text component would, on the
background its `sta` chooses: 0 the part of the picture `bco` under it, 1
the colour `bco`, 2 the picture `bco` at its corner, and 3 none. `pic`,
`picq`, and `xpic` draw their pictures. On a page painting one of each,
the Editor's simulator drew the same pixels, but for the smoothed edges of
circles (tests/fixtures/drawing/ keeps the fill, the outline, and the line). So did
lines of other slopes, each way, and `xstr` on a crop, a picture, and none
(tests/fixtures/drawing-assumptions/, page9 and page11). They are painted
in drawing_commands.py, its _moved stepping a line.
"""
import functools

from nxwright import NxwrightError
from nxwright.drawing.checkbox_drawing import paint_checkbox
from nxwright.drawing.combo_box_drawing import paint_combo_box
from nxwright.drawing.data_record_drawing import paint_data_record
from nxwright.drawing.drawing_commands import CommandPainter
from nxwright.drawing.drawing_shared import (MOST_PICTURE_PIXELS, NO_RESOURCE, PLACE, border_width,
                                             box_of, part_within)
from nxwright.drawing.dual_state_button_drawing import paint_dual_state_button
from nxwright.drawing.file_browser_drawing import paint_file_browser
from nxwright.drawing.gauge_drawing import paint_gauge
from nxwright.drawing.media_drawing import paint_animation, paint_video
from nxwright.drawing.number_drawing import paint_number, paint_xfloat
from nxwright.drawing.progress_bar_drawing import paint_progress_bar
from nxwright.drawing.qr_code_drawing import paint_qr_code
from nxwright.drawing.radio_drawing import paint_radio
from nxwright.drawing.scrolling_text_drawing import paint_scrolling_text
from nxwright.drawing.select_drawing import paint_select
from nxwright.drawing.slider_drawing import paint_slider
from nxwright.drawing.sliding_text_drawing import paint_sliding_text
from nxwright.drawing.switch_drawing import paint_switch
from nxwright.drawing.text_pictures import MissingCharacter, lacking_note, text_picture
from nxwright.drawing.waveform_drawing import paint_waveform
from nxwright.project.pictures import data_url, write_png
from nxwright.project.screen_colours import rgb565_to_hex, rgb565_to_rgb
from nxwright.source.component_groups import group_of
from nxwright.source.page_source import Component

# A component's `aph` when it is drawn wholly opaque, every type's default.
OPAQUE = 127
# The types drawn as a text component is: background, `txt`, and border.
_WITH_TEXT = ("text", "button")
# The colours of a 3D style's edges, as the Editor's simulator draws them.
DARK_EDGE, LIGHT_EDGE = 0x4228, 0xE71C
class DrawingResources:
    """What drawing needs beyond the page: subclasses give the folder's
    pictures and fonts.
      - picture(id): the picture's name, or None for none or an unknown ID;
      - picture_size(id): its (width, height), or None when it cannot be read;
      - font(id): its decoded zi_font.Font; raises NxwrightError when it
        cannot be read or decoded;
      - font_height(id): its height in pixels, from its header, which a font
        nxwright cannot decode has too, or None when it cannot be read (by
        default: the decoded font's, or None);
      - card_picture(path): the name under which a picture shape shows the
        file an external picture's `path` names on an SD card, or None when
        there is none such (by default: there are no cards);
      - frames(kind, id): the media_files.Frames of the folder's animation or
        video `id`, `kind` being ANIMATION or VIDEO (resource_names.py), or
        None when there is none such (by default: there are none); raises
        NxwrightError when its file cannot be read;
      - card_frames(path): the Frames of the video file `path` names on an
        SD card, or None when there is none such (by default: there are no
        cards); raises NxwrightError when it cannot be read;
      - encoding: the project's character encoding;
      - rotation: the screen's rotation, in degrees;
      - opaque_pictures: whether the screen stores the folder's pictures
        without alpha, their transparent share white, as the Editor's
        simulator showed on an Enhanced screen, where an Intelligent one
        keeps it (screen_copy.py, stored_pixels)."""
    encoding = "iso-8859-1"
    rotation = 0
    opaque_pictures = False

    def card_picture(self, path: str):
        return None

    def frames(self, kind: str, media_id: int):
        return None

    def card_frames(self, path: str):
        return None

    def picture(self, picture_id: int):
        raise NotImplementedError

    def picture_size(self, picture_id: int):
        raise NotImplementedError

    def font(self, font_id: int):
        raise NotImplementedError

    def font_height(self, font_id: int):
        try:
            return self.font(font_id).height
        except NxwrightError:
            return None


def draw_page(components: list, resources: DrawingResources, painted=(),
              spacing: tuple = (0, 0), hidden=(), waves: dict = None,
              pressed: str = None, listings: dict = None, select_moves: dict = None,
              scrolled: dict = None) -> dict:
    """Returns the drawing of a page's Components, the page first, then of
    what drawing commands `painted`, as the module's docstring says.
    `spacing` is the system variables spax and spay, which `xstr` uses. The
    components named in `hidden`, which `vis` hid, are not drawn; they keep
    their place in the ID order that `ref` counts by. `waves` gives the
    waveforms' points, {waveform: {channel: [values, oldest first]}};
    `pressed` the component held down, a button drawn with its pressed look;
    `listings` the entries each file browser lists, {browser: [names]};
    `select_moves` how far a press has moved a select's lines, {select:
    pixels, down being more}; and `scrolled` where a simulation has moved
    each scrolling text, {scrolling text: its text's left, or its top when
    it moves up or down, in page pixels}, one left out being drawn at rest;
    one moved is placed across its way by its `vvs2` or `vvs3`, the size
    the simulation keeps (scrolling_text_drawing.py). `scrolled` also says
    how far the simulation has scrolled each combo box's open list, {combo
    box: the number of its first item shown}, one left out showing its
    chosen item; and where a touch put each slider's knob, {slider: the
    knob's start along its track, from its start, or its bottom when
    upright}, one left out placed by its `val`."""
    waves, listings, select_moves = waves or {}, listings or {}, select_moves or {}
    scrolled = scrolled or {}

    def paint(component):
        held = component.name == pressed
        painter = ComponentPainter(drawing, component, resources, waves.get(component.name, {}),
                                   held, listings.get(component.name),
                                   select_moves.get(component.name, 0),
                                   scrolled.get(component.name))
        if held and component.type == "button":
            painter = painter.second_look()
        painter.paint()

    page = components[0].values
    drawing = {"width": page["w"], "height": page["h"],
               "transparent": _page_without_background(page, resources),
               "shapes": [], "components": [], "unplaced": [], "notes": []}
    placed = {}
    for component in components:
        values = component.values
        entry = {"name": component.name, "type": component.type,
                 "global": values.get("vscope") == 1}
        if not all(key in values for key in PLACE):
            drawing["unplaced"].append(entry)   # such as a timer or a variable
            continue
        entry["locked"] = values.get("lockobj") == 1
        group = group_of(values)
        if group is not None:
            entry["group"] = group
        if component.name in hidden:
            continue
        placed[component.name] = component
        drawing["components"].append(dict(entry, **{key: values[key] for key in PLACE}))
        paint(component)
    _paint_commands(drawing, components, placed, resources, painted, spacing, paint)
    return drawing


def _page_without_background(values: dict, resources: DrawingResources) -> bool:
    """Whether a page draws no background of its own, and so is drawn over
    what the screen showed before: `sta` 0, or `sta` 2, a picture, with no
    picture set or one the folder does not have, as the user saw the Editor
    do."""
    sta = values.get("sta")
    if sta == 2:
        picture_id = values.get("pic", NO_RESOURCE)
        return picture_id == NO_RESOURCE or resources.picture(picture_id) is None
    return sta == 0


def _paint_commands(drawing: dict, components: list, placed: dict, resources, painted,
                    spacing: tuple, paint):
    """Adds the shapes of what drawing commands painted, in order;
    `paint(component)` draws a component again."""
    waiting, stopped = [], False
    by_id = {str(index): component.name for index, component in enumerate(components)}
    page = components[0]
    painter = ComponentPainter(drawing, page, resources)
    commands = CommandPainter(painter)
    with_background = not _page_without_background(page.values, resources)

    def redraw(redrawn: list):
        # A component's earlier drawing goes: what lies under it shows, and
        # its smoothed edges are not blended twice. The page's stays, being
        # also what drawing commands painted; drawn again, it covers them.
        gone = {component.name for component in redrawn} - {page.name}
        if gone:
            drawing["shapes"] = [shape for shape in drawing["shapes"]
                                 if shape["component"] not in gone]
        for component in redrawn:
            paint(component)

    others = [component for name, component in placed.items() if name != page.name]
    meeting = {}

    def linked(box: dict, marked) -> list:
        # The components linked to `box` by overlaps, in ID order: those it
        # meets, then those they meet, and so on. Which components meet is
        # found once, at the first mark, as their boxes do not change
        # within a drawing.
        if not meeting:
            places = {component.name: _place_of(component) for component in others}
            meeting.update({name: [other for other, place in places.items() if other != name
                                   and part_within(place, own) is not None]
                            for name, own in places.items()})
        found = {component.name for component in others
                 if component is marked or part_within(_place_of(component), box) is not None}
        unvisited = list(found)
        while unvisited:
            for name in meeting[unvisited.pop()]:
                if name not in found:
                    found.add(name)
                    unvisited.append(name)
        return [component for component in others if component.name in found]

    def uncover(box: dict, marked=None):
        # The page's own background comes back under `box`, and under the
        # box of each component linked to it by overlaps, then those are
        # drawn again whole, in ID order: what was painted there goes. On a
        # page without one, the screen as the page found it comes back
        # there instead, which the panel keeps.
        met = linked(box, marked)
        boxes = []
        for each in [box] + [_place_of(component) for component in met]:
            if each not in boxes:
                boxes.append(each)
        for each in boxes:
            shown = part_within(each, painter.box)
            if shown is None:
                continue
            if with_background:
                painter.background({1: "bco", 2: "pic"}, shown)
            else:
                painter.add("backdrop", shown)
        redraw(met)

    def again(entry: tuple):
        command, name, *box = entry
        name = by_id.get(name, name)
        if command == "left":
            uncover(dict(zip(PLACE, box[0])))
        elif name == page.name:
            # The page drawn again draws every component again.
            redraw(list(placed.values()))
        elif name in placed:
            uncover(_place_of(placed[name]), placed[name])

    for command, *arguments in painted:
        if command in ("redraw", "left"):
            if stopped:
                waiting.append((command, *arguments))
            else:
                again((command, *arguments))
        elif command == "ref":
            again(("redraw", arguments[0]))
        elif command == "ref_stop":
            stopped = True
        elif command == "ref_star":
            stopped = False
            for entry in dict.fromkeys(waiting):
                again(entry)
            waiting = []
        else:
            commands.paint(command, arguments, spacing)


def _place_of(component) -> dict:
    """A component's rectangle, from its attributes."""
    return {key: component.values[key] for key in PLACE}


def inside_box(values: dict) -> dict:
    """The rectangle inside a component's border (border_width), from its
    attributes `values`, its place among them."""
    border = border_width(values)
    return box_of(values["x"] + border, values["y"] + border, values["w"] - 2 * border,
                  values["h"] - 2 * border)


# A scroll bar's thumb, a file browser's or a sliding text's: this size,
# whatever the component's, a grey drawn this opaque, of 255, over what is
# under it. The Editor's simulator drew a sliding text's (175, 174, 175)
# over white and (175, 174, 38) over yellow; a file browser's was seen over
# white only, and is taken to be alike.
THUMB_WIDTH, THUMB_HEIGHT = 4, 20
_THUMB_GREY, _THUMB_OPACITY = (82, 80, 82), 118
class ComponentPainter:
    """Adds one component's shapes to a drawing. A type drawn in a module of
    its own, nxwright/drawing/<type>_drawing.py, draws through its methods:
    `add` and `note`, `background`, `picture`, `folder_picture`, `border`,
    `edges`, `text`, `text_component`, `inside`, `scroll_thumb`, `pixels`,
    `too_large`, and, for what lies partly outside a rectangle,
    `before_screen_end`, `colour_within`, and `text_within`. A method such a
    module needs is added here, so that every type shares it."""

    def __init__(self, drawing: dict, component, resources: DrawingResources,
                 waves: dict = None, pressed: bool = False, listing: list = None,
                 moved: int = 0, scrolled: int = None):
        self.waves = waves or {}     # a waveform's points, by channel
        self.pressed = pressed       # whether it is held down
        self.second = False          # whether it shows its second look (second_look)
        self.listing = listing       # a file browser's entries, when known
        self.moved = moved           # how far a press has moved a select's lines
        # Where a scrolling text's text has moved, or a combo box's list's
        # first item shown, or a slider's knob a touch placed, or None.
        self.scrolled = scrolled
        self.drawing, self.component, self.resources = drawing, component, resources
        self.values = component.values
        self.box = {key: self.values[key] for key in PLACE}

    def paint(self):
        kind = self.component.type
        if kind == "page":
            if not _page_without_background(self.values, self.resources):
                self.background({1: "bco", 2: "pic"})
            elif self.values.get("sta") == 2 and self.values.get("pic", NO_RESOURCE) != NO_RESOURCE:
                self.note("pic %d is not a picture of the folder" % self.values["pic"])
        elif kind in _WITH_TEXT:
            self.text_component()
        elif kind == "number":
            paint_number(self)
        elif kind == "xfloat":
            paint_xfloat(self)
        elif kind == "checkbox":
            paint_checkbox(self)
        elif kind == "radio":
            paint_radio(self)
        elif kind == "dual-state-button":
            paint_dual_state_button(self)
        elif kind == "switch":
            paint_switch(self)
        elif kind == "gauge":
            paint_gauge(self)
        elif kind == "scrolling-text":
            paint_scrolling_text(self)
        elif kind == "gmov":
            paint_animation(self)
        elif kind == "video":
            paint_video(self)
        elif kind == "sliding-text":
            paint_sliding_text(self)
        elif kind == "combo-box":
            paint_combo_box(self)
        elif kind == "data-record":
            paint_data_record(self)
        elif kind == "picture":
            self.picture("pic", (0, 0))
        elif kind == "crop":
            # The picture's part from vvs0 right of the crop and vvs1 below
            # it.
            self.picture("picc", (self.box["x"] + self.values.get("vvs0", 0),
                                  self.box["y"] + self.values.get("vvs1", 0)))
        elif kind == "slider":
            paint_slider(self)
        elif kind == "waveform":
            paint_waveform(self)
        elif kind == "progress-bar":
            paint_progress_bar(self)
        elif kind == "file-browser":
            paint_file_browser(self)
        elif kind == "select":
            paint_select(self)
        elif kind == "external-picture":
            name = self.resources.card_picture(self.values.get("path", ""))
            if name is not None:
                self.add("picture", picture=name, sx=0, sy=0, rotation=self.resources.rotation,
                         card=True)
        elif kind == "qr-code":
            paint_qr_code(self)
        elif kind == "hotspot":
            pass
        else:
            self.add("outline", label="%s (%s)" % (self.component.name, kind))

    def add(self, kind: str, box: dict = None, **shape):
        """Adds a shape covering `box`, the component's rectangle by default,
        marked with the component's `aph` when it is drawn less than opaque.
        A component of `aph` 0 adds none, but for an outline, which stands
        in for what the preview cannot draw, not for the screen's pixels,
        and is drawn whole."""
        opacity = OPAQUE if kind == "outline" else self._opacity()
        if opacity == 0:
            return
        if opacity < OPAQUE:
            shape["aph"] = opacity
        self.drawing["shapes"].append(dict({"component": self.component.name, "kind": kind},
                                           **(box or self.box), **shape))

    def _opacity(self) -> int:
        """How opaque the component is drawn, its `aph`, from 0 to OPAQUE: a
        value past it, which code may set though the build refuses it, is
        opaque, as the Editor's simulator drew a text whose `aph` code set to
        200 (tests/fixtures/drawing-assumptions/, page13). A page and a
        hotspot are opaque: the Editor's panel never shows their `aph`, and a
        page of `aph` 50 looked no different in the Editor's simulator."""
        aph = self.values.get("aph", OPAQUE)
        if self.component.type in ("page", "hotspot") or not isinstance(aph, int):
            return OPAQUE
        return min(max(aph, 0), OPAQUE)

    def note(self, text: str):
        """Notes something drawn otherwise than the screen would, or of note,
        once for the component, though several of its texts may say it."""
        line = "%s: %s" % (self.component.name, text)
        if line not in self.drawing["notes"]:
            self.drawing["notes"].append(line)

    def background(self, by_sta: dict, box: dict = None):
        """Paints over `box`, the component's rectangle by default, the
        background that `sta` chooses: the attribute by_sta names, a colour
        (bco...), the part of a picture under the box (picc...), or a picture
        at the component's corner (pic...)."""
        box = box or self.box
        attribute = by_sta.get(self.values.get("sta"))
        if attribute is None:
            return
        if attribute.startswith("bco"):
            self.add("colour", box, colour=rgb565_to_hex(self.values.get(attribute, 0)))
        elif attribute.startswith("picc"):
            self.picture(attribute, (box["x"], box["y"]), box)
        else:
            self.picture(attribute, (box["x"] - self.box["x"], box["y"] - self.box["y"]), box)

    def picture(self, attribute: str, corner: tuple, box: dict = None):
        """Paints over `box`, the component's rectangle by default, the
        picture `attribute` names, its pixel `corner` at the box's corner, or
        notes why it cannot."""
        picture_id = self.values.get(attribute, NO_RESOURCE)
        if picture_id != NO_RESOURCE:
            self.picture_by_id(picture_id, corner, box, attribute, outlined=True)

    def picture_by_id(self, picture_id: int, corner: tuple, box: dict, named: str,
                      outlined: bool = False):
        """Paints over `box` the folder's picture `picture_id`, its pixel
        `corner` at the box's corner. For a picture the folder lacks, it
        notes so, the ID `named` as the note says it, and outlines `box`
        when `outlined`."""
        name = self.resources.picture(picture_id)
        if name is None or self.resources.picture_size(picture_id) is None:
            self.note("%s %d is not a picture of the folder" % (named, picture_id))
            if outlined:
                self.add("outline", box, label=self.component.name)
            return
        self.folder_picture(box, name, corner)

    def folder_picture(self, box: dict, name: str, corner: tuple):
        """Adds the folder's picture `name` over `box`, its pixel `corner` at
        the box's corner, marked opaque where the screen keeps no alpha."""
        opaque = {"opaque": True} if self.resources.opaque_pictures else {}
        self.add("picture", box, picture=name, sx=corner[0], sy=corner[1], **opaque)

    def border(self):
        """Paints a `style` 1 border, `borderw` wide, inside the rectangle, or
        a 3D style's edges, each on a colour background alone, as the
        module's docstring says."""
        style = self.values.get("style")
        if style in (2, 3, 4):
            # Style 4 sinks in the second look.
            if self.values.get("sta") == 1:
                self.edges(sunk=style == 2 or (style == 4 and self.second))
            return
        if style != 1:
            return
        x, y, w, h = (self.box[key] for key in PLACE)
        size = border_width(self.values)
        if size <= 0:
            return
        colour = rgb565_to_hex(self.values.get("borderc", 0))
        sides = ((x, y, w, size), (x, y + h - size, w, size),
                 (x, y + size, size, h - 2 * size), (x + w - size, y + size, size, h - 2 * size))
        for side in sides:
            self.add("colour", dict(zip(PLACE, side)), colour=colour)

    def edges(self, sunk: bool):
        """Paints a 3D style's edges: dark on the top and left when `sunk`,
        else on the bottom and right, and light on the others. The left and
        right edges run the full height, so the corners take their colours.
        They belong on a colour background: border() draws them only on
        one, and a checkbox, which always has one, draws them itself."""
        x, y, w, h = (self.box[key] for key in PLACE)
        if w < 2 or h < 2:
            return
        dark, light = rgb565_to_hex(DARK_EDGE), rgb565_to_hex(LIGHT_EDGE)
        before, after = (dark, light) if sunk else (light, dark)
        for side, colour in (((x + 1, y, w - 2, 1), before), ((x + 1, y + h - 1, w - 2, 1), after),
                             ((x, y, 1, h), before), ((x + w - 1, y, 1, h), after)):
            self.add("colour", dict(zip(PLACE, side)), colour=colour)

    def too_large(self, width: int, height: int, what: str) -> bool:
        """Whether a picture `width` by `height` is too large to make, as one
        far larger than the page, from a mistyped size, would stall the
        drawing. Notes that `what`, such as "its code", is not drawn when it
        is."""
        if width * height <= MOST_PICTURE_PIXELS:
            return False
        self.note("%s is not drawn: %d by %d pixels is too large" % (what, width, height))
        return True

    def second_look(self):
        """Returns a painter of the component in its second look: its second
        colours and pictures, `bco2`, `pco2`, `pic2`, and `picc2`, in place
        of its first, a style 4 sunk. A button shows it while pressed, and a
        dual-state button while its `val` is 1."""
        values = dict(self.values)
        for attribute in ("bco", "pco", "pic", "picc"):
            if attribute + "2" in self.values:
                values[attribute] = self.values[attribute + "2"]
        look = ComponentPainter(self.drawing, Component(self.component.name, self.component.type,
                                                        values),
                                self.resources, self.waves, self.pressed, self.listing,
                                self.moved)
        look.second = True
        return look

    @staticmethod
    def edge_colours() -> tuple:
        """The (dark, light) colours, as RGB, of a 3D style's edges, which a
        radio's ring shares."""
        return rgb565_to_rgb(DARK_EDGE), rgb565_to_rgb(LIGHT_EDGE)

    def inside(self) -> dict:
        """The rectangle inside the component's border (inside_box)."""
        return inside_box(self.values)

    def scroll_thumb(self, scrolled: int, most: int, track: dict = None):
        """Paints a scroll bar's thumb, at the right of `track`, the
        rectangle inside the border by default, by `left`: 2 always, 1 while
        the component is drawn pressed, which a simulation gives while a
        touch scrolls it (Simulation._drawn_pressed), 0 never. It is placed
        by `scrolled` of `most`, the farthest the content scrolls, and none
        shows when the content all shows (`most` 0). The Editor's simulator
        placed it so, but for a pixel higher at some values, by a rule no
        probe settled: at 5, 10, and 20 of 50, but not 25."""
        # A table marked defaults = false may leave `left` out: the types' default is 1.
        left = self.values.get("left", 1)
        if most <= 0 or not (left == 2 or left == 1 and self.pressed):
            return
        track = track or self.inside()
        travel = max(track["h"] - THUMB_HEIGHT, 0)
        top = track["y"] + min(max(scrolled, 0), most) * travel // most
        self.add("text", box_of(track["x"] + track["w"] - THUMB_WIDTH, top, THUMB_WIDTH,
                                THUMB_HEIGHT), image=_thumb_picture())

    def before_screen_end(self, box: dict):
        """The part of the rectangle `box` left of the screen's right edge and
        above its bottom edge, or None for none, in which a text the screen's
        edge cuts is placed. A part above the screen's top, or left of its
        left edge, stays: the Editor's simulator placed a text there in the
        whole box."""
        return part_within(box, box_of(box["x"], box["y"], self.drawing["width"] - box["x"],
                                       self.drawing["height"] - box["y"]))

    def colour_within(self, box: dict, inside: dict, colour: int):
        """Paints the part of `box` within `inside` in the RGB565 `colour`."""
        shown = part_within(box, inside)
        if shown is not None:
            self.add("colour", shown, colour=rgb565_to_hex(colour))

    def text_within(self, text: str, font, placing: dict, box: dict, colour: int, inside: dict,
                    fading=None):
        """Paints `text` in `font` and the RGB565 `colour`, placed in `box`
        as a text component's attributes `placing` place it, cut to the part
        within `inside`: the webviews paint a text's picture whole.
        `fading(row)`, when given, is how much of its colour a pixel of the
        page's row keeps, from 0 to 1."""
        shown = part_within(box, inside)
        if shown is None or not 0 < box["w"] * box["h"] <= MOST_PICTURE_PIXELS:
            return
        try:
            pixels = text_picture(text, font, self.resources.encoding, placing, box["w"], box["h"],
                                  rgb565_to_rgb(colour))
            lacking = lacking_note(text, font, self.resources.encoding, placing)
        except NxwrightError as error:
            self.note(str(error))
            return
        if lacking:
            self.note(lacking)
        rgba = bytearray()
        for row in range(shown["y"], shown["y"] + shown["h"]):
            start = ((row - box["y"]) * box["w"] + shown["x"] - box["x"]) * 4
            part = bytearray(pixels[start:start + shown["w"] * 4])
            if fading is not None:
                keep = fading(row)
                part[3::4] = bytes(round(alpha * keep) for alpha in part[3::4])
            rgba += part
        self.add("text", shown, image=data_url(write_png(shown["w"], shown["h"], bytes(rgba))))

    def text_component(self, text: str = None, at: tuple = (None, None)):
        """Paints a component as a text component is drawn: the background
        its `sta` chooses, `text`, its `txt` by default, and its border. The
        text is placed, and cut, inside the border (inside); `at`, where
        given, is from that inside's corner (text)."""
        self.background({0: "picc", 1: "bco", 2: "pic"})
        inside = self.inside()
        # A border that fills the component leaves no room for its text,
        # which is then not drawn; an empty component's is noted (text).
        if inside["w"] > 0 and inside["h"] > 0 or border_width(self.values) == 0:
            self.text(text, inside, at=at)
        self.border()

    def text(self, text: str = None, box: dict = None, placing: dict = None,
             at: tuple = (None, None)):
        """Paints `text`, the component's `txt` by default, in `box`, its
        rectangle by default, in its font, or in an ordinary font when the
        font cannot draw it, with a note saying why. `placing` gives the
        attributes that place and colour it, as a text component's do
        (`font`, `pco`, `xcen`, `ycen`, ...): its own by default. `at`, the
        text's left and top within the box where not None, places it there
        in place of `xcen` and `ycen` (text_pictures.text_picture)."""
        if text is None:
            text = self.values.get("txt", "")
        box, placing = box or self.box, placing or self.values
        if not text:
            return
        width, height = box["w"], box["h"]
        # A text's picture is as large as its box: one far larger than the
        # page, as from a mistyped size, is not drawn.
        if not 0 < width * height <= MOST_PICTURE_PIXELS:
            self.note("its text is not drawn: a %d by %d component is too large or empty"
                      % (width, height))
            return
        colour = rgb565_to_rgb(placing.get("pco", 0))
        try:
            font = self.resources.font(placing.get("font", NO_RESOURCE))
            pixels = text_picture(text, font, self.resources.encoding, placing,
                                  width, height, colour, at)
            lacking = lacking_note(text, font, self.resources.encoding, placing)
        except NxwrightError as error:
            reason = str(error) if isinstance(error, MissingCharacter) else (
                "font %s: %s" % (placing.get("font"), error))
            self.note("drawn in an ordinary font: %s" % reason)
            self.add("plainText", box, text=text, colour=rgb565_to_hex(placing.get("pco", 0)),
                     size=self._font_height(), xcen=placing.get("xcen", 1),
                     ycen=placing.get("ycen", 1))
            return
        if lacking:
            self.note(lacking)
        if font.encoding != self.resources.encoding:
            # The screen looks the text's bytes up in the font as they are, so
            # it shows other characters; the drawing does too.
            self.note("font %s is in %s, the project in %s" % (font.name, font.encoding,
                                                                self.resources.encoding))
        self.add("text", box, image=data_url(write_png(width, height, pixels)))

    def pixels(self, points: list, colour: int):
        """Paints single pixels, as one picture over the box holding them."""
        points = [(x, y) for x, y in points
                  if 0 <= x < self.drawing["width"] and 0 <= y < self.drawing["height"]]
        if not points:
            return
        left, top = min(x for x, _ in points), min(y for _, y in points)
        width = max(x for x, _ in points) - left + 1
        height = max(y for _, y in points) - top + 1
        rgba = bytearray(width * height * 4)
        red, green, blue = rgb565_to_rgb(colour)
        for x, y in points:
            index = ((y - top) * width + x - left) * 4
            rgba[index:index + 4] = bytes((red, green, blue, 255))
        self.add("text", box_of(left, top, width, height),
                 image=data_url(write_png(width, height, bytes(rgba))))

    def _font_height(self) -> int:
        """The height of the component's font when its header can be read,
        whether or not the font can be decoded, or the component's height."""
        return self.resources.font_height(self.values.get("font", NO_RESOURCE)) or self.box["h"]


@functools.lru_cache(maxsize=1)
def _thumb_picture() -> str:
    """Returns a scroll bar's thumb, as a data: URL of its PNG: its grey, as
    opaque as _THUMB_OPACITY, over what is under it."""
    pixel = bytes(_THUMB_GREY + (_THUMB_OPACITY,))
    return data_url(write_png(THUMB_WIDTH, THUMB_HEIGHT, pixel * (THUMB_WIDTH * THUMB_HEIGHT)))
