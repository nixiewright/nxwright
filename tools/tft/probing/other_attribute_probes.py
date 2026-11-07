"""The probes of components' attributes in code other than those each type's
own probes showed, such as a text's bco or a component's x: every attribute
each type writes, read into sys0; every one code can change on T, set; and
some in the conditions of if, while, and for, and in each family of
commands. Run them with `tools.tft.probe run other_attribute_probes`.

Each compares the blocks of page0's Touch Release event, beside one
component of each type, and keeps them as its fixtures (statement_probes.py
gives both). The last is on K, for K's own commands.
"""
from nxwright.project.attribute_descriptions import code_cannot_change
from nxwright.project.editor_limits import code_cannot_change_on_series

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.checkbox_probes import checkbox_component
from tools.tft.probing.crop_probes import crop_component
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tools.tft.probing.gauge_probes import gauge_component
from tools.tft.probing.hotspot_probes import hotspot_component
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import (StrictPicturesChange, picture_component,
                                          with_pictures_and_code)
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.progress_bar_probes import progress_bar_component
from tools.tft.probing.qr_code_probes import qr_code_component
from tools.tft.probing.radio_probes import radio_component
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tools.tft.probing.slider_probes import slider_component
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.touch_capture_probes import touch_capture_component
from tools.tft.probing.variable_probes import text_variable_component, variable_component
from tools.tft.probing.waveform_probes import waveform_component
from tools.tft.probing.xfloat_probes import xfloat_component

FIXTURES = "other-attributes"

# One component of each type, each where it overlaps no other.
_COMPONENTS = [
    text_component(), number_component(y=50), button_component(y=90), checkbox_component(y=150),
    radio_component(y=180), dual_state_button_component(y=210), gauge_component(x=150, y=10),
    hotspot_component(x=150, y=120), progress_bar_component(x=150, y=180),
    qr_code_component(x=150, y=220), scrolling_text_component(y=330), slider_component(y=370),
    timer_component(), variable_component(), text_variable_component("va1"),
    waveform_component(x=10, y=400, h=60), xfloat_component(x=220, y=10),
    touch_capture_component()]
# The attributes each of them writes, by the component's name and type. A
# txt is left out, as it is no number.
ATTRIBUTES = {
    ("t0", "text"): "type id vscope x y w h endx endy sta style font bco pco xcen ycen isbr "
                    "txt_maxl pw spax spay",
    ("n0", "number"): "type id vscope x y w h endx endy sta style font bco pco xcen ycen val "
                      "lenth format isbr spax spay",
    ("b0", "button"): "type id vscope x y w h endx endy sta style font bco bco2 pco pco2 xcen "
                      "ycen val txt_maxl isbr spax spay",
    ("c0", "checkbox"): "type id vscope x y w h endx endy style bco pco val",
    ("r0", "radio"): "type id vscope x y w h endx endy bco pco val",
    ("bt0", "dual-state-button"): "type id vscope x y w h endx endy sta style font bco bco2 pco "
                                  "pco2 xcen ycen val txt_maxl isbr spax spay",
    ("z0", "gauge"): "type id vscope x y w h endx endy sta bco val pco wid",
    ("m0", "hotspot"): "type id vscope x y w h endx endy",
    ("j0", "progress-bar"): "type id vscope x y w h endx endy sta dez val dis bco pco",
    ("qr0", "qr-code"): "type id vscope x y w h endx endy sta dis bco pco txt_maxl",
    ("g0", "scrolling-text"): "type id vscope x y w h endx endy sta style font bco pco xcen ycen "
                              "dir dis tim en txt_maxl isbr spax spay vvs0 vvs1 vvs2 vvs3",
    ("h0", "slider"): "type id vscope x y w h endx endy mode sta psta wid hig bco bco1 pco val "
                      "maxval minval ch",
    ("tm0", "timer"): "type id vscope tim en",
    ("va0", "variable"): "type id vscope sta val",
    ("va1", "variable"): "type id vscope sta txt_maxl",
    ("s0", "waveform"): "type id vscope x y w h endx endy sta dir ch bco gdc gdw gdh pco0 dis",
    ("x0", "xfloat"): "type id vscope x y w h endx endy sta style font bco pco xcen ycen val "
                      "vvs0 vvs1 isbr spax spay",
    ("tc0", "touch-capture"): "type id vscope val",
}
# A picture and a crop, which show the pictures below, and a QR code with a
# logo and a waveform of 4 channels, whose entries differ from those of the
# QR code and the waveform above.
_PICTURES = [("red", (8, 4), (255, 0, 0)), ("bg", (320, 480), (0, 0, 255))]
_MORE_COMPONENTS = [
    picture_component(), crop_component(y=30), qr_code_component(x=150, y=10, sta=1, pic="red"),
    waveform_component(x=10, y=150, ch=4)]
_MORE_ATTRIBUTES = {
    ("p0", "picture"): "type id vscope x y w h endx endy pic",
    ("q0", "crop"): "type id vscope x y w h endx endy picc vvs0 vvs1",
    ("qr0", "qr-code"): "type id vscope x y w h endx endy sta dis bco pco pic txt_maxl",
    ("s0", "waveform"): "type id vscope x y w h endx endy sta dir ch bco gdc gdw gdh pco0 pco1 "
                        "pco2 pco3 dis",
}


# Attributes in each family of commands (the probe in-commands), and in
# K's own commands (in-k-commands), each the line's words.
IN_COMMANDS = [
    "cls t0.bco", "fill t0.x,t0.y,t0.w,t0.h,t0.bco+1", "line m0.x,m0.y,m0.endx,m0.endy,b0.pco2",
    "cir z0.x,z0.y,z0.wid,z0.pco", "xstr 0,0,100,30,t0.font,t0.pco,t0.bco,t0.xcen,t0.ycen,"
    "t0.sta,t0.txt", "xstr 0,0,100,30,0,RED,WHITE,0,0,1,t0.bco",
    "vis b0,j0.dis", "tsw b0,va0.sta", "randset h0.minval,h0.maxval", "page t0.pco",
    "get t0.bco", "print s0.gdc", "prints t0.txt,t0.txt_maxl", "prints n0.lenth,1",
    "covx t0.bco,t0.txt,0,0", "covx n0.val,t0.txt,n0.lenth,n0.format",
    "cov t0.txt,t0.bco,0", "strlen t0.txt,t0.x", "btlen t0.txt,g0.vvs0",
    "substr t0.txt,b0.txt,t0.spax,t0.spay", 'spstr t0.txt,b0.txt,",",z0.sta',
    "crcrest 1,t0.bco", "crcputs t0.pco,0", "crcputu t0.x,t0.y",
    "add s0.id,0,t0.bco", "addt s0.id,0,s0.gdw", "cle s0.id,s0.ch",
    "ucopy t0.bco,0,2,0", "ucopy t0.x,0,2,0", "udelete tm0.tim", "udelete t0.font"]
IN_K_COMMANDS = ["wepo t0.bco,0", "wepo t0.txt,t0.x", "repo t0.pco,10", "repo t0.x,10",
                 "wept t0.w,t0.h", "rept n0.lenth,4", "cfgpio 2,t0.sta,b0"]


def reads(attributes: dict) -> list:
    """Returns a line that reads each of `attributes` into sys0."""
    return ["sys0=%s.%s" % (name, attribute)
            for (name, _), names in attributes.items() for attribute in names.split()]


def sets(attributes: dict, series: str) -> list:
    """Returns a line that sets each of `attributes` from sys0, of those
    code can change on `series`, as nxwright gives them."""
    return ["%s.%s=sys0" % (name, attribute)
            for (name, type_name), names in attributes.items() for attribute in names.split()
            if not (code_cannot_change(type_name, attribute)
                    or code_cannot_change_on_series(type_name, attribute, series))]


def _with_pictures_and_attributes(lines: list) -> StrictPicturesChange:
    """Returns a probe's change: adds _PICTURES, puts _MORE_COMPONENTS on
    page0, and gives page0's Touch Release event `lines`, in strict Nextion
    syntax (picture_probes.with_pictures_and_code)."""
    return with_pictures_and_code(_PICTURES, lines, *_MORE_COMPONENTS)


def _probe(name: str, lines: list, series: str = "T") -> Probe:
    return Probe("other-attributes-" + name, series, with_attributes(lines, _COMPONENTS),
                 ours_in_event, theirs_in_event, FIXTURES)


PROBES = [
    # Every attribute of each type, read.
    _probe("read", reads(ATTRIBUTES)),
    # Those of a picture, a crop, a QR code with a logo, and a waveform of 4
    # channels, read.
    Probe("other-attributes-read-of-pictures-and-variants", "T",
          _with_pictures_and_attributes(reads(_MORE_ATTRIBUTES)), ours_in_event,
          theirs_in_event, FIXTURES),
    # Every attribute of each type that code can change on T, set; then
    # some added to, cut, stepped, and set from others.
    _probe("set", sets(ATTRIBUTES, "T") + [
        "t0.bco+=1", "t0.pco-=n0.font", "b0.bco2++", "h0.maxval--", "n0.lenth=t0.bco*2+n0.font",
        "g0.vvs2=g0.vvs3", "va0.val=va1.txt_maxl+va1.sta"]),
    # Attributes compared in the conditions of if, else if, while, and for,
    # and set as a for's start and step.
    _probe("in-conditions", [
        "if(t0.bco==t0.pco)", "{", "sys0=1", "}else if(b0.x>10&&h0.maxval<=100)", "{",
        "sys0=2", "}",
        "while(t0.bco<10)", "{", "t0.bco++", "}",
        "for(n0.font=0;n0.font<z0.wid||g0.dir!=1;n0.font+=1)", "{", "sys0++", "}"]),
    # Attributes in each family of commands: where a number goes, as a
    # source, and as a destination, a component's x among them, which code
    # cannot set on T.
    _probe("in-commands", IN_COMMANDS),
    # K's own commands, with attributes as values, addresses, lengths, and
    # where a value goes, on K.
    _probe("in-k-commands", IN_K_COMMANDS, "K"),
]
