"""The probes of the Nextion Editor 1.65.0, on T, K, P, and F (release_probes.py),
whose user code is kept as fixtures. Keep them with the Nextion Editor 1.65.0,
from its zip's folder, and an Editor name of its own, with the Editor
tool's Python (tools\\editor\\build\\venv\\Scripts\\python.exe),
from nxwright's folder:

  set NXWRIGHT_EDITOR=<the folder>\\NextionEditor.exe
  set NXWRIGHT_EDITOR_NAME=agent-b-1650
  <the tool's Python> -m tools.tft.probe keep editor_1_65_0_probes --version 1.65.0
"""
from tools.tft.probing import release_probes

VERSION = (1, 65, 0)
PROBES = release_probes.program_probes(VERSION)
