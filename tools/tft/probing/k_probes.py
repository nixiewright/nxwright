"""The K series' probes: the T probes that show each piece nxwright writes, on
the K base folder (probes/K), NX4832K035 at 0 degrees or, for the
rotations' probes, turned, and a probe of K's own system variables, which
T has not. Each compares the whole file, part
by part, compiled as the compile command compiles it, as a series' probes
do. Run them with `tools.tft.probe run k_probes`.

K writes every block as T does, but for the numbers of some commands,
system variables, and colours (ResearchNotes/tft/k-series.md). The whole
compile of a blank project keeps fixtures, made on zeros for the firmware.
The probe of K's own system variables keeps its blocks. The other probes
keep none: T's fixtures and the comparisons in test_series_followers.py
guard their user code, allowing the differences in series_differences.py."""
from dataclasses import replace

from tools.tft.probing import (attribute_probes, button_border_and_picture_probes, button_probes,
                           checkbox_probes, code_form_probes, command_operand_probes,
                           compile_probes, condition_probes, crc_command_probes, crop_probes,
                           device_and_buffer_command_probes, drawing_probes,
                           dual_state_button_probes, eeprom_and_gpio_probes, encoding_probes,
                           for_probes, frame_probes, gauge_probes, goto_probes, hex_number_probes,
                           hotspot_probes, if_probes, indirect_probes, key_probes, macro_probes,
                           number_border_and_picture_probes, number_probes, other_attribute_probes,
                           other_page_probes, overlap_probes, page_command_probes, page_probes,
                           picture_probes, pinyin_probes, progress_bar_probes, qr_code_probes,
                           radio_probes, rotation_probes, screen_command_probes,
                           scrolling_text_probes, serial_command_probes, shared_attribute_probes,
                           slider_probes, statement_probes, text_assignment_probes,
                           text_border_and_picture_probes, text_character_probes,
                           text_command_probes, text_condition_probes, text_probes,
                           text_room_probes, timer_probes, touch_capture_probes,
                           undocumented_command_probes, variable_probes, waveform_command_probes,
                           waveform_probes, while_probes, xfloat_probes)
from tools.tft.probing.component_probes import editor_file, whole_file
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_program, program_lines, theirs_in_program
from nxwright.tft.statements import SYSTEM_VARIABLES

FIXTURES = "k"


def _on_k(probe: Probe) -> Probe:
    """Returns `probe` on the K base folder, compared as a whole file. The
    blank project's probe and the probe of K's own system variables keep
    fixtures; the other probes use T's fixtures and the follower test."""
    fixtures = probe.name in _KEEPING
    kept = (probe.kept or probe.ours) if fixtures else None
    return replace(probe, name="k-" + probe.name, base="K", ours=whole_file, theirs=editor_file,
                   fixtures=FIXTURES if fixtures else None, kept=kept)


def _named(module, *names: str) -> list:
    """Returns the probes of `module` named `names`, in that order."""
    probes = {probe.name: probe for probe in module.PROBES}
    return [probes[name] for name in names]


_KEEPING = {"compile-T-blank", "statements-own-system-variables"}

# K's own system variables, which T has not, each read into sys0 and set from
# it in program.s, as statement_probes.py's probe of T's.
_OWN_VARIABLES = sorted(set(SYSTEM_VARIABLES["K"]) - set(SYSTEM_VARIABLES["T"]))
_OWN_VARIABLES_PROBE = Probe(
    "statements-own-system-variables", "K",
    program_lines(["sys0=%s" % name for name in _OWN_VARIABLES]
                  + ["%s=sys0" % name for name in _OWN_VARIABLES]),
    ours_in_program, theirs_in_program)

PROBES = [_on_k(probe) for probe in (
    compile_probes.PROBES
    + statement_probes.PROBES
    + _named(drawing_probes, "drawing-each-command", "drawing-pictures", "drawing-texts",
             "drawing-xstr-text-operands")
    + _named(text_command_probes, "text-commands-each", "text-commands-operands",
             "text-commands-vals", "text-commands-vals-of-more-types",
             "text-commands-gauge-val", "text-commands-other-attributes",
             "text-commands-other-attributes-as-destinations",
             "text-commands-touch-capture-val")
    + _named(screen_command_probes, "screen-commands-each", "screen-commands-operands",
             "screen-commands-ids-and-the-page")
    + _named(serial_command_probes, "serial-commands-each", "serial-commands-operands",
             "serial-commands-vals-and-a-timer", "serial-commands-touch-capture-val")
    + _named(crc_command_probes, "crc-commands-each", "crc-commands-operands",
             "crc-commands-bytes", "crc-commands-in-program", "crc-commands-system-variables",
             "crc-commands-system-variables-in-program")
    + _named(device_and_buffer_command_probes, "device-and-buffer-commands-each",
             "device-and-buffer-commands-ucopy-operands",
             "device-and-buffer-commands-udelete-operands",
             "device-and-buffer-commands-touch-capture-val",
             "device-and-buffer-commands-in-program")
    # The undocumented commands are also compared with T in the tests.
    + undocumented_command_probes.PROBES
    # Macros, call, and return. On K they keep no fixtures, as they show no
    # number of K's own.
    + macro_probes.PROBES
    + _named(hex_number_probes, "hex-numbers-in-assignments", "hex-numbers-in-conditions",
             "hex-numbers-in-program")
    + _named(if_probes, "if-comparisons", "if-nested", "if-or-empty-body", "if-event")
    + _named(while_probes, "while-conditions", "while-nested")
    + _named(for_probes, "for-conditions", "for-nested", "for-longest-start")
    # A declaration past the 767 characters other lines may have on K.
    + _named(frame_probes, "frame-int-line-of-1000-characters")
    + attribute_probes.PROBES
    + _named(button_probes, "button-txt-and-val-in-code", "button-txt-and-val-in-commands")
    + _named(variable_probes, "variable-of-a-text-beside-one-of-a-number",
             "variable-txt-in-code")
    + _named(progress_bar_probes, "progress-bar-among-the-types-matched",
             "progress-bar-val-in-code", "progress-bar-of-other-looks", "progress-bar-upward",
             "progress-bar-of-pictures",
             "progress-bar-of-no-pictures-and-of-colours-with-pictures",
             "progress-bar-pictures-in-code")
    # Pages of more objects than the others, up to the frame's page rule's
    # 41: the run of 0xFF bytes that starts a page's memory grows with them.
    + _named(text_probes, "text-eight-on-a-page", "text-forty-on-a-page",
             "text-one-then-four-on-a-page")
    # A text's attributes away from their defaults: its looks, its spacing,
    # and a second font.
    + _named(text_probes, "text-of-other-looks", "text-of-pw-apart-from-isbr", "text-of-spacing",
             "text-in-a-second-font")
    # Its borders, and the pictures behind it, in drawings and in code.
    + _named(text_border_and_picture_probes, "text-of-each-style", "text-of-borders",
             "text-of-a-picture-and-a-crop",
             "text-of-no-picture-and-of-a-colour-with-pictures",
             "text-of-a-picture-in-a-project-of-none", "text-borders-and-pictures-in-code")
    # And a number's: its looks, its lenths and formats, and a second font.
    + _named(number_probes, "number-of-other-looks", "number-of-lenths-and-formats",
             "number-in-a-second-font")
    + _named(number_border_and_picture_probes, "number-of-each-style", "number-of-borders",
             "number-of-a-picture-and-a-crop",
             "number-of-no-picture-and-of-a-colour-with-pictures",
             "number-of-a-picture-in-a-project-of-none", "number-borders-and-pictures-in-code")
    # A page's bco, its swipe targets, its effect and swipe targets in its own
    # code, and what lies behind it, its sta and pic,
    # then a page of the most components.
    + _named(page_probes, "page-of-other-colours", "page-of-swipes",
             "page-of-its-effect-and-swipes-in-code", "page-of-an-effect-in-code",
             "page-of-no-background",
             "page-of-pictures", "page-of-a-picture-past-the-last",
             "page-of-a-picture-without-pictures", "page-of-hidden-backgrounds",
             "page-of-no-background-and-code",
             "page-every-type-on-no-background", "page-every-type-on-a-picture",
             "page-of-250-texts")
    # Encodings: each of two-byte characters, utf-8, ascii, and three of one
    # byte a character; a txt on each type that has one; the entries of every
    # type; and texts in code. K's own wepo is in encoding_probes.py.
    + _named(encoding_probes, "encoding-gb2312", "encoding-big5", "encoding-shift-jis",
             "encoding-ks_c_5601-1987", "encoding-utf-8", "encoding-ascii", "encoding-koi8-r",
             "encoding-iso-8859-2", "encoding-windows-1258", "encoding-every-txt-in-gb2312",
             "encoding-every-type-in-utf-8", "encoding-code-in-gb2312",
             "encoding-code-in-utf-8", "encoding-code-in-shift-jis",
             "encoding-code-read-in-pairs-in-shift-jis")
    # Rotations: a text at each, a component of each type, and pictures.
    + _named(rotation_probes, "rotation-90", "rotation-180", "rotation-270",
             "rotation-90-every-type-on-a-picture", "rotation-180-every-type-on-a-picture",
             "rotation-270-every-type-on-a-picture", "rotation-270-pictures")
    + _named(button_probes, "button-ten-on-a-page", "button-of-other-colours",
             "button-of-other-placing", "button-pressed-from-the-start", "button-of-spacing",
             "button-in-a-second-font")
    # The attributes every component with a place has, and the page too.
    + shared_attribute_probes.PROBES
    + _named(button_border_and_picture_probes, "button-of-each-style", "button-of-borders",
             "button-of-pictures-and-crops",
             "button-of-no-picture-and-of-a-colour-with-pictures",
             "button-of-pictures-in-a-project-of-none", "button-borders-and-pictures-in-code")
    + _named(hotspot_probes, "hotspot-two", "hotspot-before-a-text", "hotspot-in-commands")
    + _named(timer_probes, "timer-two", "timer-on-three-pages", "timer-tim-and-en-in-code")
    + _named(picture_probes, "picture-two", "picture-pic-in-code")
    + _named(crop_probes, "crop-two", "crop-picc-in-code")
    + _named(checkbox_probes, "checkbox-two", "checkbox-val-in-code", "checkbox-of-each-style",
             "checkbox-of-borders", "checkbox-borders-in-code")
    + _named(radio_probes, "radio-two", "radio-val-in-code")
    + _named(dual_state_button_probes, "dual-state-button-two",
             "dual-state-button-txt-and-val-in-code", "dual-state-button-of-other-colours",
             "dual-state-button-of-other-placing", "dual-state-button-of-spacing",
             "dual-state-button-in-a-second-font", "dual-state-button-of-each-style",
             "dual-state-button-of-borders", "dual-state-button-of-pictures-and-crops",
             "dual-state-button-of-no-picture-and-of-a-colour-with-pictures",
             "dual-state-button-of-pictures-in-a-project-of-none",
             "dual-state-button-borders-and-pictures-in-code")
    + _named(page_command_probes, "page-by-name", "page-by-variable", "page-values")
    + _named(xfloat_probes, "xfloat-two", "xfloat-val-in-code", "xfloat-of-other-looks",
             "xfloat-in-a-second-font", "xfloat-of-each-style", "xfloat-of-borders",
             "xfloat-of-a-picture-and-a-crop",
             "xfloat-of-no-picture-and-of-a-colour-with-pictures",
             "xfloat-of-a-picture-in-a-project-of-none", "xfloat-borders-and-pictures-in-code")
    + _named(slider_probes, "slider-two", "slider-after-a-timer", "slider-val-in-code",
             "slider-colours-and-sizes", "slider-upright", "slider-val-outside-its-bounds",
             "slider-of-pictures-and-crops", "slider-of-a-picture-cursor",
             "slider-of-no-pictures-and-of-colours-with-pictures", "slider-pictures-in-code")
    + _named(qr_code_probes, "qr-code-two", "qr-code-txt-maxl-154", "qr-code-txt-in-code",
             "qr-code-colours-and-margin", "qr-code-logos")
    + _named(text_assignment_probes, "text-from-a-txt", "text-joined",
             "text-added-to-and-cut", "text-of-printable-ascii", "text-long",
             "text-with-spaces", "text-of-a-qr-code", "text-added-to-joined-and-cut-by-operands")
    # Components that overlap: the probes that keep fixtures on T, which show
    # each part of the refs' walk (overlap_probes.py). On K they keep none, as
    # they show no number of K's own.
    + _named(overlap_probes, "overlap-two", "overlap-chain-1-4-5-3-6-beside-2",
             "overlap-ids-past-9", "overlap-types-under-a-picture",
             "overlap-more-types-under-a-picture", "overlap-hotspot-and-xfloat-under-a-picture",
             "overlap-slider-gauge-qr-code-and-waveform-under-a-picture",
             "overlap-scrolling-text-under-a-picture", "overlap-scrolling-text-in-a-chain")
    + _named(gauge_probes, "gauge-two", "gauge-taller-than-wide", "gauge-val-in-code",
             "gauge-of-other-looks", "gauge-of-a-picture-and-a-crop",
             "gauge-of-no-picture-and-of-a-colour-with-pictures", "gauge-pictures-in-code")
    + [_OWN_VARIABLES_PROBE]
    + _named(waveform_probes, "waveform-two", "waveform-among-the-types-matched",
             "waveform-on-second-page", "waveform-id-in-code", "waveform-channels",
             "waveform-attributes", "waveform-of-a-picture-and-a-crop",
             "waveform-of-no-picture-and-of-a-colour-with-pictures",
             "waveform-of-hidden-values", "waveform-of-molloc", "waveform-pic-and-picc-in-code")
    + _named(waveform_command_probes, "waveform-commands-each", "waveform-commands-operands",
             "waveform-commands-in-program")
    # K's own commands, whose probe keeps its own fixtures on K.
    + _named(eeprom_and_gpio_probes, "eeprom-and-gpio-each")
    + _named(text_condition_probes, "text-conditions-in-if", "text-conditions-joined",
             "text-conditions-each-comparison", "text-conditions-in-loops",
             "text-conditions-two-texts", "text-conditions-of-printable-ascii",
             "text-conditions-of-more-types", "text-conditions-long")
    + _named(touch_capture_probes, "touch-capture-two", "touch-capture-among-the-types-matched",
             "touch-capture-val-in-code")
    + _named(scrolling_text_probes, "scrolling-text-two",
             "scrolling-text-among-the-types-matched", "scrolling-text-on-second-page",
             "scrolling-text-between-timers", "scrolling-text-txt-tim-and-en-in-code",
             "scrolling-text-of-each-dir", "scrolling-text-at-the-ends-of-dis-and-tim",
             "scrolling-text-of-other-looks", "scrolling-text-of-set-vvs",
             "scrolling-text-of-each-style", "scrolling-text-of-borders",
             "scrolling-text-of-a-picture-and-a-crop",
             "scrolling-text-of-no-picture-and-of-a-colour-with-pictures",
             "scrolling-text-in-a-second-font", "scrolling-text-borders-and-pictures-in-code")
    # Commands' operands: expressions, attributes, hexadecimal numbers, and
    # escapes. On K they keep no fixtures, as they show no number of K's
    # own. The probe of K's own commands runs on K itself.
    + _named(command_operand_probes, "command-operands-expressions-in-drawing-commands",
             "command-operands-expressions-in-other-commands",
             "command-operands-attributes-in-drawing-and-screen-commands",
             "command-operands-hex-numbers", "command-operands-hex-numbers-in-other-places",
             "command-operands-crcputh-253-bytes",
             "command-operands-escapes", "command-operands-escapes-in-conditions",
             "command-operands-in-program")
    # Labels and goto, beside timers, a button, a slider, and a scrolling
    # text. On K they keep no fixtures, as they show no number of K's own.
    + goto_probes.PROBES
    # Conditions of many comparisons, of texts holding && or ||, and of long
    # texts. On K they keep no fixtures, as they show no number of K's own.
    + condition_probes.PROBES
    # Attributes reached through the screen's arrays. On K they keep no
    # fixtures, as they show no number of K's own.
    + indirect_probes.PROBES
    # Another page's global components named by their page. On K they keep
    # no fixtures, as they show no number of K's own.
    + other_page_probes.PROBES
    # Components with a key, beside nxwright's keyboard pages.
    + key_probes.PROBES
    # The pinyin commands. On K they keep no fixtures; K numbers both its own
    # way, which the whole files show.
    + pinyin_probes.PROBES
    # Texts of other characters than ASCII letters and digits, in txts and in
    # code. On K they keep no fixtures; the probe of K's own command runs on
    # K itself.
    + _named(text_character_probes, "text-characters-txt-of-printable-ascii",
             "text-characters-txt-of-latin-1", "text-characters-txt-on-the-other-types",
             "text-characters-in-code")
    # Other attributes in code, read, set, in conditions, and in commands.
    # On K they keep no fixtures; the probe of K's own commands runs on K
    # itself.
    + _named(other_attribute_probes, "other-attributes-read",
             "other-attributes-read-of-pictures-and-variants", "other-attributes-set",
             "other-attributes-in-conditions", "other-attributes-in-commands")
    # The forms of code the Nextion Editor writes as plainer ones.
    + code_form_probes.PROBES
    # A txt's room over what earlier pages left in the scratch image.
    + text_room_probes.PROBES)]
