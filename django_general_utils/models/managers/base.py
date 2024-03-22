from django.core.exceptions import ValidationError
from django.db.models import ForeignKey, Manager
from django.utils.translation import gettext_lazy as _
from ordered_model.models import OrderedModelManager
from queryable_properties import managers
from safedelete.config import FIELD_NAME
from safedelete.managers import SafeDeleteManager

from ..querysets.base import BaseModelQuerySet
from ...utils.drf.validation_errors import ListValidationError


class BaseModelManager(
    Manager.from_queryset(BaseModelQuerySet),
    managers.QueryablePropertiesManagerMixin,
    SafeDeleteManager,
    OrderedModelManager
):
    def select_properties(self, *names, **kwargs):
        """
        Return a new queryset and add the annotations of the queryable
        properties with the specified names to this query. The annotation
        values will be cached in the properties of resulting model instances,
        regardless of the regular caching behavior of the queried properties.

        :param names: Names of queryable properties.
        :return: A copy of this queryset with the added annotations.
        :rtype: QuerySet
        """
        self.filter_queryable_property(**kwargs.get('property_params', {}))
        return self.get_queryset().select_properties(*names)

    def get_queryset(self):
        from ..base import BaseModel

        through = getattr(self, 'through', None)

        # through m2m attribute
        if through and issubclass(through, BaseModel):
            for field in through._meta.get_fields():
                # Check if the field is a `ForeignKey` to the current model
                if (
                        isinstance(field, ForeignKey)
                        and field.related_model == self.model
                ):
                    # Filter out objects based on deleted through objects using related name or model name
                    through_lookup = (
                            field.remote_field.related_name or through._meta.model_name
                    )
                    self.core_filters.update(
                        {f"{through_lookup}__{FIELD_NAME}__isnull": True}
                    )

        return super().get_queryset()

    def bulk_create_or_update_dict(
            self,
            values: list[dict],
            update_fields: list,
            unique_fields: list,
            full_clean: bool = True,
            # NO DELETE CREATED AND UPDATED. FILTER ONLY TAKE UNIQUE FIELDS NOT IN UPDATE FIELDS
            delete_others: bool = False,
    ):
        assert len(update_fields) > 0, _('update_fields is required')
        assert len(unique_fields) > 0, _('unique_fields is required')

        instance_created = []

        models_to_create = []
        models_to_update = []

        for _unique_field in unique_fields:
            for _value in values:
                if _value.get(_unique_field) is None:
                    raise ValueError(_('Field "{field}" is required').format(field=_unique_field))

        to_create_update = {
            str([
                str(_value[_unique])
                for _unique in unique_fields
            ]): _value
            for _value in values
        }
        filter_query = {
            f'{_unique}__in': [_value[_unique] for _value in values]
            for _unique in unique_fields
        }

        to_update = {
            str([
                str(getattr(_obj, _unique))
                for _unique in unique_fields
            ]): _obj
            for _obj in self.filter(**filter_query).in_bulk().values()
        }
        to_create = [
            _value for _key, _value in to_create_update.items()
            if _key not in to_update.keys()
        ]

        errors = {
            _key: ValidationError({})
            for _key in to_create_update.keys()
        }

        if len(to_create) > 0:
            models_to_create = [
                self.model(**_value)
                for _value in to_create
            ]

            if full_clean:
                for _obj in models_to_create:
                    try:
                        _obj.full_clean()
                    except ValidationError as e:
                        errors[
                            str([
                                str(getattr(_obj, _unique))
                                for _unique in unique_fields
                            ])
                        ] = e

        if len(to_update) > 0:
            for _obj in to_update.values():
                for _field in update_fields:
                    setattr(
                        _obj,
                        _field,
                        to_create_update[
                            str([
                                str(getattr(_obj, _unique))
                                for _unique in unique_fields])
                        ][_field]
                    )

                models_to_update.append(_obj)

            if full_clean:
                for _obj in models_to_update:
                    try:
                        _obj.full_clean()
                    except ValidationError as e:
                        errors[
                            str([
                                str(getattr(_obj, _unique))
                                for _unique in unique_fields
                            ])
                        ] = e

        if full_clean and any([len(_error.message_dict) > 0 for _error in errors.values()]):
            raise ListValidationError(errors.values())

        if len(models_to_create) > 0:
            try:
                instance_created = self.bulk_create(
                    models_to_create,
                    full_clean=False,
                )
            except ListValidationError as e:
                for _model, _error in zip(models_to_create, e.args[0]):
                    errors[
                        str([
                            getattr(_model, _unique)
                            for _unique in unique_fields
                        ])
                    ] = _error

        if len(models_to_update) > 0:
            try:
                self.bulk_update(
                    models_to_update,
                    fields=update_fields,
                    batch_size=100,
                    full_clean=False,
                )
            except ListValidationError as e:
                for _model, _error in zip(models_to_create, e.args[0]):
                    errors[
                        str([
                            getattr(_model, _unique)
                            for _unique in unique_fields
                        ])
                    ] = _error

        if any([len(_error.message_dict) > 0 for _error in errors.values()]):
            raise ListValidationError(errors.values())

        if delete_others:
            self.filter(**{
                f'{_unique}__in': [_value[_unique] for _value in values]
                for _unique in set(unique_fields) - set(update_fields)
            }).exclude(
                **{
                    f'id__in': [_instance.id for _instance in (instance_created + models_to_update)]
                }
            ).delete()

        self.model._delete_cache()

        return instance_created, models_to_update
