"""The helpers of the tests that build whole projects by design, such as the
sample of whole files (tests/tft/test_whole_files.py) and the whole compile
(tests/tft/test_compile.py): a project nxwright builds from a base folder. The
unit tests make their input in memory instead (tests/tft/unit_inputs.py).
"""
from pathlib import Path
import shutil
import tempfile

from nxwright.source.project_files import build

from tools.tft.probing import probe_runner
from nxwright.tft.project import Project


def built_project(base: str, change=None) -> Project:
    """Returns the project nxwright builds from the base folder of `base`,
    changed by `change`, as the probe runner builds it."""
    with tempfile.TemporaryDirectory() as work:
        source = Path(work) / "source"
        shutil.copytree(probe_runner.BASES / base, source)
        if change is not None:
            change(source)
        build(source, Path(work) / "probe.HMI")
        return Project.from_file(Path(work) / "probe.HMI")
