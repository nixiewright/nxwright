"""The probes of a component's key (component_types.key_lines): a text, a
number, an xfloat, and a scrolling text, global as a key needs, each beside
one of nxwright's keyboard pages, the keypad, the full keyboard, and the
speed dial; a caller with its own Touch Release code, which the key's lines
follow; keyed components on two pages, beside one keyboard; and each
keyed type with key 4 beside nxwright's Chinese keyboard, in gb2312. Run
them with `tools.tft.probe run key_probes`. A sliding text's key, which P and
E alone have, is probed in sliding_text_probes.py.

Each compares the whole file, part by part, and the first keeps the user
code alone as its fixtures (component_probes.py gives both).
"""
from dataclasses import dataclass
from pathlib import Path

from tools.tft.probing.component_probes import on_pages, type_probe, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.xfloat_probes import xfloat_component


def _keyed(component: str, key: int) -> str:
    """Returns `component`, in a page file's form, global and with `key`."""
    return component + "vscope = 1\nkey = %d\n" % key


@dataclass(frozen=True, eq=False)
class KeyboardChange:
    """A probe's change: `change`, then nxwright's keyboard page `keyboard`
    added, as nxwright's keyboard command adds it, after the pages `change`
    adds, with its font. A unit test reads both, to make the same pages in
    memory (tests/tft/unit_inputs.py). Two changes are equal only if they are
    the same one, as two functions are."""
    change: object
    keyboard: str

    def __call__(self, folder: Path):
        from nxwright.source.keyboard_adding import add_keyboard
        self.change(folder)
        add_keyboard(folder, self.keyboard)


def _beside(keyboard: str, *components: str, code: str = "", page1: tuple = ()) -> KeyboardChange:
    """Returns a probe's change: `components` on page0, with `code`, and
    `page1`'s on a second page, then nxwright's keyboard page `keyboard`
    (KeyboardChange)."""
    change = with_components(*components, code=code)
    if page1:
        change = on_pages(change, with_components(*page1, page="page1"))
    return KeyboardChange(change, keyboard)


# The height of the Chinese keyboard's font: one its keys fit on T's screen.
_CHINESE_FONT_HEIGHT = 16


def _beside_the_chinese_keyboard(*components: str):
    """Returns a probe's change: `components` on page0, the folder's
    encoding gb2312, then nxwright's Chinese keyboard. Its font, Zh, holds
    every character of gb2312, each a pattern of pixels of its own, as
    nxwright's own tests make one, so that the probe needs no typeface."""
    def change(folder: Path):
        from nxwright.project.zi_font import Glyph, encode_font, grid_table_codes
        from nxwright.source.device_change import change_device
        from nxwright.source.keyboard_adding import add_keyboard
        from nxwright.source.resource_adding import add_font_file
        with_components(*components)(folder)
        change_device(folder, encoding="gb2312")
        height = _CHINESE_FONT_HEIGHT
        glyphs = [Glyph(code, 1 if code < 0x80 else 2, 0, 0,
                        tuple((index + pixel) % 8
                              for pixel in range((1 if code < 0x80 else 2) * height)))
                  for index, code in enumerate(grid_table_codes("gb2312"))]
        font = folder.parent / "Zh.zi"
        font.write_bytes(encode_font("Zh", "gb2312", height, 0, glyphs))
        add_font_file(folder, font, "Zh")
        add_keyboard(folder, "chinese-input", font="Zh")
    return change


PROBES = [
    # Key 2, the keypad, after the text's own code.
    type_probe("key", "text-on-the-keypad", _beside(
        "keypad", _keyed(text_component(), 2), code="on t0.up:\n  sys0=7\n"), fixtures=True),
    # Key 1, the full keyboard.
    type_probe("key", "number-on-the-keyboard", _beside(
        "keyboard", _keyed(number_component(), 1))),
    # Key 3, the speed dial.
    type_probe("key", "xfloat-on-the-speed-dial", _beside(
        "speed-dial", _keyed(xfloat_component(), 3))),
    # A scrolling text and a number on page0, IDs 1 and 2, and a text on
    # page1, each with key 2, beside one keypad.
    type_probe("key", "callers-on-two-pages", _beside(
        "keypad", _keyed(scrolling_text_component(), 2),
        _keyed(number_component("n0", y=60), 2),
        page1=(_keyed(text_component(), 2),))),
    # Key 4, Chinese input, whose page runs pa_q and pa_txt.
    type_probe("key", "text-on-the-chinese-keyboard", _beside_the_chinese_keyboard(
        _keyed(text_component(), 4))),
    # Key 4 on each other keyed type.
    type_probe("key", "others-on-the-chinese-keyboard", _beside_the_chinese_keyboard(
        _keyed(number_component(), 4), _keyed(xfloat_component("x0", y=60), 4),
        _keyed(scrolling_text_component("g0", y=110), 4))),
    # Keys of no keyboard, 0 and 5, beside no keyboard page.
    type_probe("key", "of-no-keyboard", with_components(
        _keyed(text_component(), 0), _keyed(number_component("n0", y=60), 5))),
]
