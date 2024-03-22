from django.conf import settings
from django.core.cache import cache


def delete_cache(key_cache) -> None:
    """
    Elimina el cache de redis
    """
    CACHES = getattr(settings, 'CACHES', {})

    if len(CACHES) == 0:
        return None

    if CACHES.get('default', {}).get('BACKEND', '') != 'django_redis.cache.RedisCache':
        return None

    keys = cache.keys(f'*{key_cache}*')

    if len(keys) == 0:
        return None

    cache.delete_many(keys)

    return None
