import warnings


def deprecated_alias(obj, old_path: str, new_path: str):
    """
    Return `obj` after emitting a `DeprecationWarning` pointing from `old_path` to `new_path`.
    Meant to be called from a module-level `__getattr__` (PEP 562) so the warning fires on
    every access to the deprecated name, not just once at module-definition time.
    """
    warnings.warn(
        f"'{old_path}' is deprecated and will be removed in a future release; use '{new_path}' instead.",
        DeprecationWarning,
        stacklevel=3,
    )

    return obj
