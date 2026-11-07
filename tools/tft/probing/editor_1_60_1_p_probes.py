"""The probes of the Nextion Editor 1.60.1 of P's component types
(release_probes.py), whose user code is kept as fixtures, so that the slots
of the releases before 1.63 can be named for each type. They are:
  - a probe of P of two of a type that T and K have too, or of one with
    pictures, crops, or borders, as the probes of the Nextion Editor 1.63.3
    keep (older_editor_probes.py);
  - a waveform of four channels, and a progress bar of pictures and a
    slider of pictures and crops, which fill slots no other probe does;
  - each of the types that only P has, at its defaults and in each variant
    that gives it other attributes, as the probes of 1.63.3 keep them
    (older_editor_probes.P_OWN_TYPES), but for those below;
  - each type that has a place, and the page, with an effect, and a
    dragged text with a disup of 1, as the probes of 1.63.3 keep them
    (older_editor_probes.P_EFFECTS, P_DRAGGED, and P_DISUP).
There is no touch capture's and no audio's: 1.60.1 has neither on P
("Unknown Component was found"). There is no gmov's at a from of 1 either:
1.60.1 refuses it ("Gmov ID ERROR"), even beside an animation.

Keep them with the Nextion Editor 1.60.1, from its zip's folder, and an
Editor name of its own, with the Editor tool's Python
(tools\\editor\\build\\venv\\Scripts\\python.exe), from nxwright's
folder:

  set NXWRIGHT_EDITOR=<the folder>\\NextionEditor.exe
  set NXWRIGHT_EDITOR_NAME=agent-b-1601
  <the tool's Python> -m tools.tft.probe keep editor_1_60_1_p_probes --version 1.60.1
"""
from tools.tft.probing import older_editor_probes, p_probes, release_probes

VERSION = (1, 60, 1)
# The probes of P_OWN_TYPES that 1.60.1 refuses: the audio's, and the
# gmov's at a from of 1.
_REFUSED = ("p-media-a-sound", "p-audio-from-a-file", "p-gmov-of-from-1")
# The probes of P whose projects these take.
_PROJECTS = ("p-text-two", "p-text-of-a-picture-and-a-crop", "p-text-of-borders",
             "p-button-two", "p-button-of-pictures-and-crops", "p-button-of-borders",
             "p-dual-state-button-two", "p-dual-state-button-of-pictures-and-crops",
             "p-timer-two", "p-variable-two", "p-progress-bar-two", "p-hotspot-two",
             "p-picture-two", "p-number-two", "p-xfloat-two", "p-checkbox-two", "p-radio-two",
             "p-crop-two", "p-slider-two", "p-gauge-two", "p-qr-code-two",
             "p-waveform-four-channels-wide", "p-scrolling-text-two",
             "p-progress-bar-of-pictures", "p-slider-of-pictures-and-crops"
             ) + tuple(name for name in older_editor_probes.P_OWN_TYPES if name not in _REFUSED
                       ) + (older_editor_probes.P_EFFECTS + older_editor_probes.P_DRAGGED
                            + older_editor_probes.P_DISUP)

PROBES = release_probes.layout_probes(VERSION, {
    "P": [probe for probe in p_probes.PROBES if probe.name in _PROJECTS]})
