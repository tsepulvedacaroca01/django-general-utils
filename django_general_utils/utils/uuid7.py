import os
import time
import uuid

_48_BITS = 0xFFFFFFFFFFFF
_12_BITS = 0x0FFF
_62_BITS = 0x3FFFFFFFFFFFFFFF


def uuid7() -> uuid.UUID:
    """
    Generate an RFC 9562 UUIDv7 (48-bit unix-epoch-ms timestamp in the most
    significant bits, version 7, variant 10, remaining bits random).

    Reimplemented with stdlib primitives instead of relying on ``uuid.uuid7``
    because that function only exists from Python 3.14 onward, and this
    library supports ``>=3.9``.
    """
    unix_ts_ms = int(time.time() * 1000) & _48_BITS
    rand_a = int.from_bytes(os.urandom(2), 'big') & _12_BITS
    rand_b = int.from_bytes(os.urandom(8), 'big') & _62_BITS

    uuid_int = (
        (unix_ts_ms << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )

    return uuid.UUID(int=uuid_int)
