"""The Editor's screen models, and what a project file stores for each.

A project specifies its screen model by a device ID, manifest bytes 16 to 19, and
its series by manifest byte 11. Part of the manifest's stamp comes from values
the Editor keeps per model, which are not known; their combined effect is one
number per model, the same at every rotation (stamp.py). The screen size is
the one the Editor lists for the model, which sizes a new project's pages;
some models are listed taller than wide, though their names read the other way
(NX3224T024 is 240 by 320).

All of it was read off projects the Editor saved, one per model, and the
Editor's list of models.
"""
from dataclasses import dataclass

from nxwright import NxwrightError
from nxwright.project.screen_copy import FORMAT_COMPRESSED, FORMAT_RAW, FORMAT_RAW_WITH_HEADER

# Manifest byte 11, by series: Basic (T), Enhanced (K), Intelligent (P),
# Edge (E), and Discovery (F).
_SERIES = {"T": 0, "K": 1, "P": 3, "E": 6, "F": 100}
# The format a series stores its pictures' screen copies in (screen_copy.py).
_PICTURE_FORMATS = {"T": FORMAT_RAW, "K": FORMAT_RAW, "F": FORMAT_RAW_WITH_HEADER,
                    "P": FORMAT_COMPRESSED, "E": FORMAT_COMPRESSED}


@dataclass(frozen=True)
class ScreenModel:
    """One of the Editor's screen models. `device_id` is manifest bytes 16 to
    19 as stored; `stamp_number` is the model's part of the manifest stamp."""
    name: str
    device_id: bytes
    stamp_number: int
    width: int
    height: int

    @property
    def series(self) -> str:
        """The series letter in the model's name: T, K, P, E, or F."""
        return self.name[6]

    @property
    def series_code(self) -> int:
        """The series as manifest byte 11 stores it."""
        return _SERIES[self.series]

    @property
    def picture_format(self) -> int:
        """The format of the model's screen copies (screen_copy.py)."""
        return _PICTURE_FORMATS[self.series]


def _model(name: str, device_id: str, stamp_number: int, width: int, height: int) -> ScreenModel:
    return ScreenModel(name, bytes.fromhex(device_id), stamp_number, width, height)


MODELS = (
    _model("NX3224T024", "a77796f5", 0x42ea5540, 240, 320),
    _model("NX3224T028", "3b384314", 0x5c947e7b, 240, 320),
    _model("NX4024T032", "a94d496d", 0xcfba3f9a, 240, 400),
    _model("NX4832T035", "18c03bb2", 0x60a078b9, 320, 480),
    _model("NX4827T043", "b16e29ca", 0x99808f3f, 480, 272),
    _model("NX8048T050", "e33aad87", 0x2057cc05, 800, 480),
    _model("NX8048T070", "ccbd1f08", 0x3962c43b, 800, 480),
    _model("NX3224F024", "bcc1495b", 0x097c92bd, 240, 320),
    _model("NX3224F028", "208e9cba", 0x1702b986, 240, 320),
    _model("NX4832F035", "0376e41c", 0x2b36bf44, 320, 480),
    _model("NX3224K024", "01937e5c", 0x82067632, 240, 320),
    _model("NX3224K028", "9ddcabbd", 0x9c785d09, 240, 320),
    _model("NX4024K032", "0fa9a1c4", 0x0f561ce8, 240, 400),
    _model("NX4832K035", "be24d31b", 0xa04c5bcb, 320, 480),
    _model("NX4827K043", "178ac163", 0x596cac4d, 480, 272),
    _model("NX8048K050", "45de452e", 0xe0bbef77, 800, 480),
    _model("NX8048K070", "6a59f7a1", 0xf98ee749, 800, 480),
    _model("NX4827P043", "da691118", 0x57d45f43, 480, 272),
    _model("NX8048P043", "23a359a8", 0x7e395d71, 800, 480),
    _model("NX8048P050", "883d9555", 0xee031c79, 800, 480),
    _model("NX8048P070", "a7ba27da", 0xf7361447, 800, 480),
    _model("NX1060P070", "c27334c4", 0x56a8cda1, 1024, 600),
    _model("NX1060P101", "a04fc44f", 0x1570cbcb, 1024, 600),
    _model("NX4848E021", "fe0a77a2", 0x528557eb, 480, 480),
    _model("NX4848E028", "4bb13d0b", 0xbf81fb57, 480, 480),
    _model("NX4848E040", "65afb221", 0xd25c2cb3, 480, 480),
    _model("NX4880E043", "7c0da0b7", 0x7e7b6d4d, 480, 800),
)
_BY_NAME = {model.name: model for model in MODELS}
_BY_ID = {model.device_id: model for model in MODELS}


def model_named(name: str) -> ScreenModel:
    """Returns the model called `name`, such as "NX8048P050". Raises
    NxwrightError for a name the table does not hold."""
    model = _BY_NAME.get(name)
    if model is None:
        raise NxwrightError("unknown screen model %r; known: %s" % (name, ", ".join(_BY_NAME)))
    return model


def model_with_id(device_id: bytes):
    """Returns the model whose device ID is `device_id`, or None."""
    return _BY_ID.get(bytes(device_id))
