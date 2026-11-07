"""The probes of the Nextion Editor 1.60.1, on T, K, and P (release_probes.py),
whose user code is kept as fixtures: each series' probe of program.s, and its
blank project and one of three pages with ints and code, which show the
layout of the releases before 1.63; and on T and K, four projects of texts,
numbers, buttons, and variables, which show how such a release keeps
components. Keep them with the Nextion Editor 1.60.1,
from its zip's folder, and an Editor name of its own, with the Editor
tool's Python (tools\\editor\\build\\venv\\Scripts\\python.exe),
from nxwright's folder:

  set NXWRIGHT_EDITOR=<the folder>\\NextionEditor.exe
  set NXWRIGHT_EDITOR_NAME=agent-b-1601
  <the tool's Python> -m tools.tft.probe keep editor_1_60_1_probes --version 1.60.1
"""
from tools.tft.probing import compile_probes, k_probes, p_probes, release_probes

VERSION = (1, 60, 1)
# The probes of the whole compile whose projects show the layout, by series.
_LAYOUT = {"T": ("compile-T-blank", "compile-T-pages-ints-code"),
           "K": ("k-compile-T-blank", "k-compile-T-pages-ints-code"),
           "P": ("p-compile-T-blank", "p-compile-T-pages-ints-code")}
# Those whose projects hold components, on T and K.
_COMPONENTS = ("compile-T-texts", "compile-T-numbers-and-a-text",
               "compile-T-buttons-and-a-text", "compile-T-variables-and-a-text")
_PROJECTS = {"T": _LAYOUT["T"] + _COMPONENTS,
             "K": _LAYOUT["K"] + tuple("k-" + name for name in _COMPONENTS), "P": _LAYOUT["P"]}
_MODULES = {"T": compile_probes, "K": k_probes, "P": p_probes}

PROBES = release_probes.program_probes(VERSION) + release_probes.layout_probes(VERSION, {
    series: [probe for probe in _MODULES[series].PROBES if probe.name in names]
    for series, names in _PROJECTS.items()})
