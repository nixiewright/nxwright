"""The probes of an older Nextion Editor, 1.63.3, whose TFT files nxwright does
not write: each is kept as the Editor writes it, compared with nothing
(probe_runner.kept_from_the_editor), so that the decompiler's tests read
real files of that version (ResearchNotes/tft/older-editors.md).

Six of them take the project of a probe of the whole compile, on the
series' base folder: a blank project, and one of three pages with int
variables and code, on T, K, and P.

The rest take the project of a probe of one type. On K, there is a page of
texts. On P, there are:
  - two of each of the types that T and K have too, such as the text, the
    number, and the touch capture, and a waveform of four channels;
  - the text, the button, and the dual-state button behind pictures and
    crops, and the text and the button with borders, as those fill the
    slots of their backgrounds, and a progress bar of pictures and a slider
    of pictures and crops, which fill slots no other probe does;
  - each of the types that only P has, at its defaults and in each variant
    that gives it other attributes, some in a project of a picture or a
    resource that 1.63.3 needs (P_OWN_TYPES);
  - each type that has a place, and the page, with an effect, which gives
    its first and its time an entry, most of them with a drag too, which
    gives a disup an entry (P_EFFECTS, P_DRAGGED), and a dragged text with
    a disup of 1 (P_DISUP).
These probes show which attribute each slot of a record of P gives on
1.63.3.

Each probe's fixtures are its user code, in the parts the frame's probes
keep (frame_probes.pieces), never the firmware. Keep them with the
Nextion Editor 1.63.3, from its zip's folder, and an Editor name
of its own, with the Editor tool's Python
(tools\\editor\\build\\venv\\Scripts\\python.exe), from nxwright's
folder:

  set NXWRIGHT_EDITOR=<the folder>\\NextionEditor.exe
  set NXWRIGHT_EDITOR_NAME=agent-b-1633
  <the tool's Python> -m tools.tft.probe keep older_editor_probes --version 1.63.3
"""
from tools.tft.probing import compile_probes, frame_probes, k_probes, p_probes
from tools.tft.probing.probe_runner import Probe

# The folder of these probes' fixtures, by the Nextion Editor's version,
# which starts each probe's name too.
FIXTURES = "editor-1-63-3"
# The probes of p_probes of the types that only P has: each at its
# defaults, and in each variant that gives it other attributes, such as a
# crop or a picture behind it, a border style, or a gmov, a video, or an
# audio from a file. The probes of the Nextion Editor 1.60.1 take them too
# (editor_1_60_1_p_probes.py).
# The Nextion Editor 1.63.3 refuses a file browser whose pic1 or pic2 gives
# no picture, and a gmov, a video, or an audio whose vid gives no resource
# of its kind, which 1.68.2 takes. So each of those at its defaults, and
# the bordered file browsers, are taken in a project that has a picture or
# a resource of that kind: the file browsers among pictures, and the gmov,
# the video, and the audio as media_probes' probes of one animation, one
# video, and one sound.
P_OWN_TYPES = (
    "p-combo-box-at-its-defaults", "p-combo-box-with-a-crop-behind",
    "p-combo-box-with-a-picture-behind", "p-combo-box-of-style-1", "p-combo-box-of-style-2",
    "p-combo-box-of-style-3",
    "p-sliding-text-at-its-defaults", "p-sliding-text-with-a-crop-behind",
    "p-sliding-text-with-a-picture-behind", "p-sliding-text-of-style-1",
    "p-sliding-text-of-style-2", "p-sliding-text-of-style-3",
    "p-file-browser-at-its-defaults-among-pictures", "p-file-browser-with-a-crop-behind",
    "p-file-browser-with-a-picture-behind", "p-file-browser-bordered-among-pictures",
    "p-file-browser-bordered-without-folders-among-pictures",
    "p-data-record-at-its-defaults", "p-data-record-with-a-crop-behind",
    "p-data-record-with-a-picture-behind", "p-data-record-bordered",
    "p-select-at-its-defaults", "p-select-without-its-line", "p-select-with-a-crop-behind",
    "p-select-with-a-picture-behind", "p-select-of-style-1",
    "p-switch-at-its-defaults", "p-external-picture-at-its-defaults",
    "p-file-stream-at-its-defaults",
    "p-media-an-animation", "p-gmov-of-from-1", "p-media-a-video", "p-video-from-a-file",
    "p-media-a-sound", "p-audio-from-a-file")
# The probes of p_probes of an effect, its first, and its time, which give
# a component two more entries: on a text, a number, and a button, and on
# a second page; the first and the time without an effect, which give
# none; and on a gmov and a video, which play a resource of their kind, as
# above. The probes of the Nextion Editor 1.60.1 take them too.
P_EFFECTS = (
    "p-shared-attributes-effects", "p-shared-attributes-effects-and-a-second-page",
    "p-shared-attributes-first-and-time-without-an-effect",
    "p-media-an-animation-with-an-effect", "p-media-a-video-with-an-effect")
# The probes of p_probes of each other type that has a place, with an
# effect, and with a drag of 1 and the other attributes every component
# has, away from their defaults. The probes of the Nextion Editor 1.60.1
# take them too. A file browser's is among pictures, as above. For the
# drag, their records fill slot 79, the entry of a disup of 0, which 1.68.2
# does not have.
P_DRAGGED = (
    "p-checkbox-shared-attributes", "p-radio-shared-attributes",
    "p-dual-state-button-shared-attributes", "p-progress-bar-shared-attributes",
    "p-picture-shared-attributes", "p-xfloat-shared-attributes", "p-qr-code-shared-attributes",
    "p-crop-shared-attributes", "p-slider-shared-attributes", "p-gauge-shared-attributes",
    "p-scrolling-text-shared-attributes", "p-waveform-shared-attributes",
    "p-hotspot-shared-attributes", "p-switch-shared-attributes",
    "p-external-picture-shared-attributes", "p-select-shared-attributes",
    "p-combo-box-shared-attributes", "p-sliding-text-shared-attributes",
    "p-data-record-shared-attributes", "p-file-browser-shared-attributes-among-pictures")
# The probe of p_probes of a dragged text with a disup of 1. The probes of
# the Nextion Editor 1.60.1 take it too.
P_DISUP = ("p-shared-attributes-a-drag-and-a-disup",)
# The probes of the whole compile whose projects these take, on each series:
# its probes' module, and the prefix of their names there.
_SERIES = (("T", compile_probes, ""), ("K", k_probes, "k-"), ("P", p_probes, "p-"))
_PROJECTS = ("compile-T-blank", "compile-T-pages-ints-code")
# The probes of one type whose projects these take, by series.
_TYPES = (("K", k_probes, ("k-text-eight-on-a-page",)),
          ("P", p_probes, ("p-text-two", "p-text-of-a-picture-and-a-crop", "p-text-of-borders",
                           "p-button-two", "p-button-of-pictures-and-crops", "p-button-of-borders",
                           "p-dual-state-button-two", "p-dual-state-button-of-pictures-and-crops",
                           "p-timer-two", "p-variable-two", "p-progress-bar-two", "p-hotspot-two",
                           "p-picture-two", "p-number-two", "p-xfloat-two", "p-checkbox-two",
                           "p-radio-two", "p-crop-two", "p-slider-two", "p-gauge-two",
                           "p-qr-code-two", "p-waveform-four-channels-wide",
                           "p-scrolling-text-two", "p-touch-capture-two",
                           "p-progress-bar-of-pictures", "p-slider-of-pictures-and-crops")
           + P_OWN_TYPES + P_EFFECTS + P_DRAGGED + P_DISUP))


def _probes() -> list:
    """Returns a probe of each project of _PROJECTS on each series of
    _SERIES, and of each probe of _TYPES, named after it, as the Nextion
    Editor 1.63.3 writes it."""
    taken = [(module, [prefix + project for project in _PROJECTS])
             for _, module, prefix in _SERIES]
    taken += [(module, names) for _, module, names in _TYPES]
    found = []
    for module, names in taken:
        named = {probe.name: probe for probe in module.PROBES}
        for name in names:
            whole = named[name]
            found.append(Probe("%s-%s" % (FIXTURES, whole.name), whole.base, whole.change, None,
                               frame_probes.editor_pieces, FIXTURES))
    return found


PROBES = _probes()
