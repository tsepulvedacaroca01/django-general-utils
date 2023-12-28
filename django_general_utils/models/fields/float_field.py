from django.db import models

from .formated_number_field import FormattedNumberField


class FloatField(FormattedNumberField, models.FloatField):
    pass
