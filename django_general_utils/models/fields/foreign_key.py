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

        return IsNull(
            RawSQL(f'{related_alias}.{FIELD_NAME}',
                   [], output_field=models.DateField()),
            True
        )
