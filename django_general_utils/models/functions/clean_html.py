import re

from django.db.models import Func, Value, CharField


class CleanHtml(Func):
    output_field = CharField()
    function = 'regexp_replace'

    def __init__(self, field, *args, **kwargs):
        """
        Limpia el campo eliminado las etiquetas html y los espacios en blanco
        @param field: campo
        """
        main_pattern = re.compile(r'<[^>]*>|[\n\r\t]|^\s+|\s+$', re.IGNORECASE)
        sec_pattern = re.compile(r'\s{2,}|&nbsp;', re.IGNORECASE)

        super().__init__(
            Func(
                field,
                Value(main_pattern.pattern),
                Value(''),
                Value('gi'),
                function=self.function,
                output_field=self.output_field
            ),
            Value(sec_pattern.pattern), Value(' '), Value('gi'),
            *args, **kwargs
        )
