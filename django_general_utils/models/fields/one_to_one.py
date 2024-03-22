from django.db import models
from django.db.models.expressions import RawSQL
from django.db.models.fields.related_descriptors import ReverseOneToOneDescriptor, ForwardOneToOneDescriptor
from django.db.models.lookups import IsNull
from django_middleware_global_request import get_request
from safedelete.config import FIELD_NAME


class SingleRelatedObjectDescriptorReturnsNone(ReverseOneToOneDescriptor):
    def get_queryset(self, **hints):
        from ..base import BaseModel

        filter_args = {}

        if issubclass(self.related.related_model, BaseModel):
            filter_args |= {
                f'{FIELD_NAME}__isnull': True,
            }

        return self.related.related_model._base_manager.db_manager(hints=hints).filter(**filter_args)

    def __get__(self, instance, cls=None):
        try:
            return super().__get__(instance, cls)
        except self.RelatedObjectDoesNotExist:
            return None


class CustomForwardOneToOneDescriptor(ForwardOneToOneDescriptor):
    def get_object(self, instance):
        from ..base import BaseModel

        if self.field.remote_field.parent_link:
            deferred = instance.get_deferred_fields()
            # Because it's a parent link, all the data is available in the
            # instance, so populate the parent model with this data.
            rel_model = self.field.remote_field.model
            fields = [field.attname for field in rel_model._meta.concrete_fields]

            # If any of the related model's fields are deferred, fallback to
            # fetching all fields from the related model. This avoids a query
            # on the related model for every deferred field.
            if not any(field in fields for field in deferred):
                kwargs = {field: getattr(instance, field) for field in fields}
                obj = rel_model(**kwargs)
                obj._state.adding = instance._state.adding
                obj._state.db = instance._state.db
                return obj

        qs = self.get_queryset(instance=instance)

        if issubclass(self.field.related_model, BaseModel):
            return qs.get(self.field.get_reverse_related_filter(instance) & models.Q(**{f'{FIELD_NAME}__isnull': True}))

        # Assuming the database enforces foreign keys, this won't fail.
        return qs.get(self.field.get_reverse_related_filter(instance))


class OneToOneField(models.OneToOneField):
    """A OneToOneField that returns None if the related object doesn't exist"""
    related_accessor_class = SingleRelatedObjectDescriptorReturnsNone
    forward_related_accessor_class = CustomForwardOneToOneDescriptor

    def __init__(self, to, on_delete, to_field=None, **kwargs):
        from django.db.models import OneToOneField

        super(OneToOneField, self).__init__(to, on_delete, to_field=to_field, **kwargs)

    def get_extra_restriction(self, alias, related_alias):
        """
        get extra restriction
        @param alias:
        @param related_alias:
        @return:
        """
        request = get_request()

        if request is not None and request.path.startswith('/admin/'):
            return None

        return IsNull(
            RawSQL(f'{related_alias}.{FIELD_NAME}',
                   [], output_field=models.DateField()),
            True
        )
