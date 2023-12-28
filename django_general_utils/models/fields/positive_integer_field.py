from django.db import models

from .formated_number_field import FormattedNumberField


class PositiveIntegerField(FormattedNumberField, models.PositiveIntegerField):
    pass
