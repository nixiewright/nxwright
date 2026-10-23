"""The device settings as app.toml writes them (docs/source-folder.md).

`screen`, `rotation`, and `encoding` come together, or not at all: a project
whose screen model nxwright does not know has none of them. The other keys
appear only when their setting is not the Editor's default.
"""
from nxwright import NxwrightError
from nxwright.project.device_settings import (NO_PASSWORD, DeviceSettings, encoding_code,
                                              is_password_hash_text)
from nxwright.project.screen_copy import ROTATIONS
from nxwright.project.screen_models import model_named

# In the order app.toml lists them.
DEVICE_KEYS = ("screen", "rotation", "encoding", "one_time_update", "memory_file_storage_size",
               "ignore_library_resources", "ignore_image_resources", "password_hash")
_REQUIRED = DEVICE_KEYS[:3]
_FLAGS = ("one_time_update", "ignore_library_resources", "ignore_image_resources")


def device_keys(settings: DeviceSettings) -> dict:
    """Returns the app.toml keys for `settings`, in DEVICE_KEYS order."""
    keys = {"screen": settings.model.name, "rotation": settings.rotation,
            "encoding": settings.encoding}
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


def settings_from_keys(app: dict):
    """Returns the DeviceSettings that `app`, the keys of an app.toml, holds,
    or None when it holds none. Raises NxwrightError naming the first key
    that is missing or wrong."""
    given = [key for key in DEVICE_KEYS if key in app]
    if not given:
        return None
    missing = [key for key in _REQUIRED if key not in app]
    if missing:
        raise NxwrightError("app.toml: %s needs %s too" % (given[0], " and ".join(missing)))
    if not isinstance(app["screen"], str):
        raise NxwrightError("app.toml: screen must be a model name, such as \"NX8048P050\"")
    try:
        model = model_named(app["screen"])
        if not isinstance(app["encoding"], str):
            raise NxwrightError("encoding must be a name, such as \"iso-8859-1\"")
        encoding_code(app["encoding"])
    except NxwrightError as error:
        raise NxwrightError("app.toml: %s" % error) from None
    rotation = app["rotation"]
    if not _is_number(rotation) or rotation not in ROTATIONS:
        raise NxwrightError("app.toml: rotation must be 0, 90, 180, or 270")
    for flag in _FLAGS:
        if not isinstance(app.get(flag, False), bool):
            raise NxwrightError("app.toml: %s must be true or false" % flag)
    size = app.get("memory_file_storage_size", 0)
    if not _is_number(size) or not 0 <= size < 2 ** 32:
        raise NxwrightError("app.toml: memory_file_storage_size must be a number of bytes")
    password = app.get("password_hash", NO_PASSWORD.hex())
    if not is_password_hash_text(password):
        raise NxwrightError("app.toml: password_hash must be 8 lower-case hexadecimal digits")
    return DeviceSettings(model=model, rotation=rotation, encoding=app["encoding"],
                          one_time_update=app.get("one_time_update", False),
                          memory_file_storage_size=size,
                          ignore_library_resources=app.get("ignore_library_resources", False),
                          ignore_image_resources=app.get("ignore_image_resources", False),
                          password_hash=bytes.fromhex(password))


def _is_number(value) -> bool:
    # TOML's true is Python's True, which equals 1: only a real number counts.
    return isinstance(value, int) and not isinstance(value, bool)
