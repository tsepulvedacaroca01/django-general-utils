from django.db import models
from safedelete.config import FIELD_NAME

from .base_constraint import BaseConstraint


class CheckConstraint(BaseConstraint, models.CheckConstraint):
    pass
