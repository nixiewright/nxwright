"""Writes a project file that contains a block nxwright does not handle, for
the tests in extract.host.cjs. The file is the demo's project as nxwright
builds it, with an added block 2.xb. The next build may lose that block.

  python write_unknown_project.py <project.HMI>

nxwright's checkout must be on Python's import path.
"""
from pathlib import Path
import sys
import tempfile

from nxwright.project.container import HmiContainer
from nxwright.source.project_files import build
from tests.test_container import build_project

DEMO = Path(__file__).resolve().parents[4] / "examples" / "thermostat" / "app"


def main(output: Path):
    with tempfile.TemporaryDirectory() as work:
        built = Path(work) / "demo.HMI"
        build(DEMO, built)
        blocks = dict(HmiContainer.from_file(built).blocks)
    blocks["2.xb"] = b"\x0a\x64\x01\x01" + bytes(12)
    output.write_bytes(build_project([(name, data, 0) for name, data in blocks.items()]))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
