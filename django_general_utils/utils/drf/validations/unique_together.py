from django.db import models
from typing import Type


def validate_unique_together(
        instance: models.Model,
        model: Type[models.Model],
        model_filter: dict
) -> bool:
    """
    Check if exists a row in database
    @param instance: instance from serializer
    @param model: Model to Filter
    @param model_filter: Fields to Filter
    @return: True if exists
    """
    instance_id = None

    if instance is not None:
        instance_id = instance.id

    return model.objects.filter(**model_filter).exclude(id=instance_id).exists()
