from django.db.models import Case, Value, When, CharField
from django.utils.encoding import force_str
from django.utils.translation import gettext_lazy as _


class WithChoices(Case):
    def __init__(self, model, field, default=None, output_field=None, **kwargs):
        """
        Muestra el valor completo del campo y no el abreviado
        @param model: Modelo
        @param field: campo
        """
        fields = field.split('__')

        for f in fields:
            model = model._meta.get_field(f)

            if model.related_model:
                model = model.related_model

        default = default or Value(force_str(_('Indefinido')))
        output_field = output_field or CharField()
        choices = dict(model.flatchoices)
        whens = [When(**{field: k, 'then': Value(force_str(v))}) for k, v in choices.items()]

        super().__init__(*whens, default=default, output_field=output_field, **kwargs)
