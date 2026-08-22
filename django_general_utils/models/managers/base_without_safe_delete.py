from ...utils.deprecation import deprecated_alias
from .base_v2 import BaseV2Manager

# Backward-compat shim: this module was renamed to `base_v2.py` (`BaseV2Manager` matches the
# `BaseV2` model naming). See `django_general_utils/models/base_without_safe_delete.py` for the
# rest of the rationale — same PEP 562 `__getattr__` pattern.
_MOVED = {
    'BaseWithoutSafeDeleteModelManager': (
        'django_general_utils.models.managers.base_v2.BaseV2Manager', BaseV2Manager,
    ),
}


def __getattr__(name):
    if name in _MOVED:
        new_path, obj = _MOVED[name]
        return deprecated_alias(obj, f'{__name__}.{name}', new_path)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
