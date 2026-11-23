"""The device settings as app.toml writes them (docs/source-folder.md).

`screen`, `rotation`, and `encoding` come together, or not at all: a project
whose screen model nxwright does not know has none of them. nxwright still
reads its texts in the project's own encoding, which does not depend on the
model (dump_folder.dump_encoding). The other keys appear only when their
setting is not the Editor's default.
"""
from nxwright import NxwrightError
from nxwright.project.device_settings import (NO_PASSWORD, DeviceSettings, encoding_code,
                                              is_password_hash_text, is_unknown_encoding)
from nxwright.project.screen_copy import ROTATIONS
from nxwright.project.screen_models import model_named

# In the order app.toml lists them.
DEVICE_KEYS = ("screen", "rotation", "encoding", "one_time_update", "memory_file_storage_size",
               "ignore_library_resources", "ignore_image_resources", "password_hash")
_REQUIRED = DEVICE_KEYS[:3]
_FLAGS = ("one_time_update", "ignore_library_resources", "ignore_image_resources")


def app_encoding(name: str):
    """Returns the encoding `name` in the form app.toml stores it. That is
    the name itself, or the number of an encoding nxwright does not know,
    such as 37 for "encoding-37" (is_unknown_encoding)."""
    return encoding_code(name) if is_unknown_encoding(name) else name


def device_keys(settings: DeviceSettings) -> dict:
    """Returns the app.toml keys for `settings`, in DEVICE_KEYS order."""
    keys = {"screen": settings.model.name, "rotation": settings.rotation,
            "encoding": app_encoding(settings.encoding)}
    for flag in _FLAGS:
        if getattr(settings, flag):
            keys[flag] = True
    if settings.memory_file_storage_size:
        keys["memory_file_storage_size"] = settings.memory_file_storage_size
    if settings.password_hash != NO_PASSWORD:
        keys["password_hash"] = settings.password_hash.hex()
    return {key: keys[key] for key in DEVICE_KEYS if key in keys}


def screen_model(app: dict):
    """Returns the ScreenModel that `app`, the keys of an app.toml, names,
    or None when it holds no screen settings. Raises NxwrightError as
    settings_from_keys does."""
    settings = settings_from_keys(app)
    return None if settings is None else settings.model


def memory_file_storage_size(app: dict) -> int:
    """Returns the number of bytes that `app`, the keys of an app.toml,
    sets aside for the files the screen keeps in its memory, or 0 if `app`
    has no screen settings. The settings are read with settings_from_keys,
    which raises NxwrightError for a key that is missing or wrong."""
    settings = settings_from_keys(app)
    return 0 if settings is None else settings.memory_file_storage_size


def settings_from_keys(app: dict):
    """Returns the DeviceSettings that `app`, the keys of an app.toml,
    contains, or None when it contains none. Raises NxwrightError for the
    first key that is missing or wrong. The error's `key` is the wrong key.
    For a missing key, it is the first device key that app.toml gives."""
    given = [key for key in DEVICE_KEYS if key in app]
    if not given:
        return None
    missing = [key for key in _REQUIRED if key not in app]
    if missing:
        raise NxwrightError("%s needs %s too" % (given[0], " and ".join(missing)),
                            key=given[0])
    if not isinstance(app["screen"], str):
        raise NxwrightError("screen must be a model name, such as \"NX8048P050\"",
                            key="screen")
    try:
        model = model_named(app["screen"])
    except NxwrightError as error:
        raise NxwrightError(str(error), key="screen") from None
    if not isinstance(app["encoding"], str):
        raise NxwrightError("encoding must be a name, such as \"iso-8859-1\", or the "
                            "number of one nxwright does not know", key="encoding")
    try:
        encoding_code(app["encoding"])
    except NxwrightError as error:
        raise NxwrightError(str(error), key="encoding") from None
    rotation = app["rotation"]
    if not _is_number(rotation) or rotation not in ROTATIONS:
        raise NxwrightError("rotation must be 0, 90, 180, or 270", key="rotation")
    for flag in _FLAGS:
        if not isinstance(app.get(flag, False), bool):
            raise NxwrightError("%s must be true or false" % flag, key=flag)
    size = app.get("memory_file_storage_size", 0)
    if not _is_number(size) or not 0 <= size < 2 ** 32:
        raise NxwrightError("memory_file_storage_size must be a number of bytes",
                            key="memory_file_storage_size")
    password = app.get("password_hash", NO_PASSWORD.hex())
    if not is_password_hash_text(password):
        raise NxwrightError("password_hash must be 8 lower-case hexadecimal digits",
                            key="password_hash")
    return DeviceSettings(model=model, rotation=rotation, encoding=app["encoding"],
                          one_time_update=app.get("one_time_update", False),
                          memory_file_storage_size=size,
                          ignore_library_resources=app.get("ignore_library_resources", False),
                          ignore_image_resources=app.get("ignore_image_resources", False),
                          password_hash=bytes.fromhex(password))


def _is_number(value) -> bool:
    # TOML's true is Python's True, which equals 1: only a real number counts.
    return isinstance(value, int) and not isinstance(value, bool)
