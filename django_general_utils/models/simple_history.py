from django.contrib import admin
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import ManyToManyField, DateTimeField, CharField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from simple_history import models, utils


class HistoricalRecords(models.HistoricalRecords):
    def fields_included(self, model):
        """
        Return a list of fields to include in the historical record. By default,
        all fields are included.
        """
        fields = []
        field_from_blur_codes = []

        if hasattr(model, '_images_field_to_blur') and hasattr(model, '_suffix_blur_code'):
            field_from_blur_codes = [
                f'{field}_{model._suffix_blur_code}'
                for field in model._images_field_to_blur
            ]

        for field in model._meta.fields:
            if field.name not in self.excluded_fields and field.name not in field_from_blur_codes:
                fields.append(field)

        return fields

    def get_history_user(self, instance):
        """Get the modifying user from instance or middleware."""
        request = None

        try:
            if self.context.request.user.is_authenticated:
                request = self.context.request
        except AttributeError:
            pass

        user = self.get_user(instance=instance, request=request)

        if user is not None:
            instance._history_user = user
            instance.__class__.objects.filter(id=instance.id).update(
                updated_by=user
            )

        return user

    def get_extra_fields(self, model, fields):
        """Return dict of extra fields added to the historical record model"""

        def revert_url(self):
            """URL for this change in the default admin site."""
            opts = model._meta
            app_label, model_name = opts.app_label, opts.model_name
            return reverse(
                f"{admin.site.name}:{app_label}_{model_name}_simple_history",
                args=[getattr(self, opts.pk.attname), self.history_id],
            )

        def get_instance(self):
            attrs = {
                field.attname: getattr(self, field.attname) for field in fields.values()
            }
            if self._history_excluded_fields:
                # We don't add ManyToManyFields to this list because they may cause
                # the subsequent `.get()` call to fail. See #706 for context.
                excluded_attnames = [
                    model._meta.get_field(field).attname
                    for field in self._history_excluded_fields
                    if not isinstance(model._meta.get_field(field), ManyToManyField)
                ]
                try:
                    values = (
                        model.objects.filter(pk=getattr(self, model._meta.pk.attname))
                        .values(*excluded_attnames)
                        .get()
                    )
                except ObjectDoesNotExist:
                    pass
                else:
                    attrs.update(values)
            result = model(**attrs)
            result._state.adding = False
            # this is the only way external code could know an instance is historical
            setattr(result, models.SIMPLE_HISTORY_REVERSE_ATTR_NAME, self)
            return result

        def get_next_record(self):
            """
            Get the next history record for the instance. `None` if last.
            """
            history = utils.get_history_manager_from_history(self)
            return (
                history.filter(history_date__gt=self.history_date)
                .order_by("history_date")
                .first()
            )

        def get_prev_record(self):
            """
            Get the previous history record for the instance. `None` if first.
            """
            history = utils.get_history_manager_from_history(self)
            return (
                history.filter(history_date__lt=self.history_date)
                .order_by("history_date")
                .last()
            )

        def get_default_history_user(instance):
            """
            Returns the user specified by `get_user` method for manually creating
            historical objects
            """
            return self.get_history_user(instance)

        extra_fields = {
            "history_id": self._get_history_id_field(),
            "history_date": DateTimeField(db_index=self._date_indexing is True),
            "history_change_reason": self._get_history_change_reason_field(),
            "history_type": CharField(
                max_length=1,
                choices=(("+", _("Created")), ("~", _("Changed")), ("-", _("Deleted"))),
            ),
            "history_object": models.HistoricalObjectDescriptor(
                model, self.fields_included(model)
            ),
            "instance": property(get_instance),
            "instance_type": model,
            "next_record": property(get_next_record),
            "prev_record": property(get_prev_record),
            "revert_url": revert_url,
            "__str__": lambda self: "{} as of {}".format(
                self.history_object, self.history_date
            ),
            "get_default_history_user": staticmethod(get_default_history_user),
        }

        extra_fields.update(self._get_history_related_field(model))
        extra_fields.update(self._get_history_user_fields())

        return extra_fields
