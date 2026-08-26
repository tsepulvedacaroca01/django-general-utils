from django.db import models
from django.db.models.expressions import RawSQL
from django.db.models.lookups import IsNull
from django_middleware_global_request import get_request
from safedelete.config import FIELD_NAME


class ForeignKey(models.ForeignKey):
    def get_extra_restriction(self, alias, related_alias):
        request = get_request()

        if request is not None and request.path.startswith('/admin/'):
            return None

        from ..base import BaseModel

        # `related_alias` puede referirse a la tabla de `self.model` o a la de
        # `self.remote_field.model` según el sentido del join (Django invierte los alias al
        # atravesar la relación en reversa, ver ForeignObjectRel.get_extra_restriction). Como no
        # se puede distinguir el sentido desde acá, solo se agrega la restricción cuando AMBOS
        # lados siguen siendo BaseModel — así `related_alias` tiene `deleted_at` sin importar cuál
        # de los dos modelos termine siendo.
        related_model = self.remote_field.model

        if not (isinstance(related_model, type) and issubclass(related_model, BaseModel)):
            return None

        if not issubclass(self.model, BaseModel):
            return None

        return IsNull(
            RawSQL(f'{related_alias}.{FIELD_NAME}',
                   [], output_field=models.DateField()),
            True
        )
