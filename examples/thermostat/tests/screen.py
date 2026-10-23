"""What the demo's tests share: the source folder, a runner for its code, and
the IDs of its pictures."""
from pathlib import Path
import tomllib

from nxwright.testing import SourceFolderRunner

APP = Path(__file__).resolve().parent.parent / "app"
PROJECT = APP.parent / "thermostat.HMI"
SCREEN = SourceFolderRunner(APP)

with open(APP / "app.toml", "rb") as _file:
    _PICTURES = tomllib.load(_file)["pictures"]


def picture(name: str) -> int:
    """The ID of the picture `name`, as code compiled from @pic(name) holds it."""
    return _PICTURES.index(name)
