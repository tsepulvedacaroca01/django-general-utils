from ordered_model.models import OrderedModel

from .base_v2 import ModelBaseV2Meta
from .managers.base_v2 import BaseV2Manager
from .uuid_v3 import UUIDModelV3


class BaseV3(OrderedModel, UUIDModelV3, metaclass=ModelBaseV2Meta):
    """
    Same as ``BaseV2``, on top of ``UUIDModelV3`` instead of ``UUIDModelV2`` — uuid7 primary
    key and a real ``id_as_code`` column. Reuses ``ModelBaseV2Meta``/``BaseV2Manager`` as-is:
    neither cares which ``UUIDModelV*`` a concrete model mixes in.
    """
    __FORMAT_LOCALE__ = 'es_CL'
    objects = BaseV2Manager()

    class Meta:
        abstract = True
        ordering = ('-created_at',)

    def save(self, **kwargs):
        full_clean = kwargs.pop('full_clean', True)

        if full_clean:
            self.full_clean()

        super().save(**kwargs)
