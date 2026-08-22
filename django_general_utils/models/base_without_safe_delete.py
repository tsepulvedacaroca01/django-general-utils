from ..utils.deprecation import deprecated_alias
from .base_v2 import BaseV2, ModelBaseV2Meta

# Backward-compat shim: this module was renamed to `base_v2.py` (`BaseV2` matches the
# `UUIDModelV2` naming pattern). Every name below still resolves to the exact same class (not a
# copy) so existing `issubclass()`/identity checks keep working, but accessing it now emits a
# DeprecationWarning pointing at the new location — see `__getattr__` (PEP 562) below.
_MOVED = {
    'BaseWithoutSafeDeleteModel': ('django_general_utils.models.base_v2.BaseV2', BaseV2),
    'ModelBaseWithOutSafeDeleteMeta': (
        'django_general_utils.models.base_v2.ModelBaseV2Meta', ModelBaseV2Meta,
    ),
}


def __getattr__(name):
    if name in _MOVED:
        new_path, obj = _MOVED[name]
        return deprecated_alias(obj, f'{__name__}.{name}', new_path)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
