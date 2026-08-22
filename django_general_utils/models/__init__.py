from ..utils.deprecation import deprecated_alias
from .base import BaseModel, SignalRegister
from .base_v2 import BaseV2
from .base_v3 import BaseV3
from .uuid import UUIDModel

# Backward-compat: `BaseV2` used to be exported here only as `BaseWithoutSafeDeleteModel`. Kept
# reachable (same class, not a copy) but now warns on access — see `__getattr__` (PEP 562).
_MOVED = {
    'BaseWithoutSafeDeleteModel': ('django_general_utils.models.BaseV2', BaseV2),
}


def __getattr__(name):
    if name in _MOVED:
        new_path, obj = _MOVED[name]
        return deprecated_alias(obj, f'{__name__}.{name}', new_path)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
