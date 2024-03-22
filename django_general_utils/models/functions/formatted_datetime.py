from django.db.models import Func, Value, CharField
from django.db.models.functions import Trunc
from django.utils import timezone


class FormattedDatetime(Func):
    function = 'to_char'
    output_field = CharField()

    def __init__(self, field, kind='seconds', tzinfo=None, format='DD/MM/YYYY HH24:MI:SS', output_field=None, **extra):
        """
        Cambia el formato de un campo de fecha y hora a un formato específico utilizando la función to_char
        """
        expressions = [
            Trunc(
                field,
                kind,
                tzinfo=tzinfo or timezone.get_current_timezone()
            ),
            Value(format)
        ]
        output_field = output_field or self.output_field
        super().__init__(*expressions, output_field=output_field, **extra)
