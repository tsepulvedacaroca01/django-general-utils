from django.db.models.fields.related_descriptors import ReverseOneToOneDescriptor
from django.core.exceptions import ObjectDoesNotExist
from django.db import models


class SingleRelatedObjectDescriptorReturnsNone(ReverseOneToOneDescriptor):
    def __get__(self, *args, **kwargs):
        try:
            return super().__get__(*args, **kwargs)
        except ObjectDoesNotExist:
            return None


class OneToOneField(models.OneToOneField):
    """A OneToOneField that returns None if the related object doesn't exist"""
    related_accessor_class = SingleRelatedObjectDescriptorReturnsNone
