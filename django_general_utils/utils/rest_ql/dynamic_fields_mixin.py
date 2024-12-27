from django.utils.functional import cached_property
from django_restql import mixins
from django_restql.fields import DynamicSerializerMethodField
from rest_framework import serializers
from rest_framework.serializers import ValidationError


class DynamicFieldsMixin(mixins.DynamicFieldsMixin):
    @cached_property
    def ref_name(self):
        return '%s-%s' % (
            self.__class__.__name__,
            '-'.join(self.allowed_fields.keys())
        )

    @staticmethod
    def is_nested_field(field_name, field, raise_exception=False):
        from ..drf.fields import NestedPrimaryKeyRelatedField, LazyRefSerializerField

        nested_classes = (
            serializers.Serializer, serializers.ListSerializer,
            DynamicSerializerMethodField, NestedPrimaryKeyRelatedField, LazyRefSerializerField
        )

        if isinstance(field, nested_classes):
            return True
        else:
            if raise_exception:
                msg = "`%s` is not a nested field" % field_name
                raise ValidationError(msg, code="invalid")
            return False
