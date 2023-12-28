import uuid

from django.db import models
from django.db.models import Case, When, Value, BooleanField
from django.db.models.functions import Now
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_shared_property.decorator import shared_property
from model_utils.fields import AutoCreatedField, AutoLastModifiedField


class UUIDModel(models.Model):
    """
    An abstract base class model that provides self-updating
    ``id``,  ``created_at`` and ``updated_at`` fields.
    """
    _id_length_ = 7
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True
    )
    id_as_code = models.CharField(
        max_length=_id_length_,
        editable=False,
        null=True,
        blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = AutoCreatedField(_('created_at'))
    updated_at = AutoLastModifiedField(_('updated_at'))
    stopped_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        abstract = True
        ordering = ('-id',)

    @shared_property(
        Case(
            When(
                stopped_at__lt=Now(),
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField()
        ),
    )
    def is_stopped(self):
        return self.stopped_at is not None and self.stopped_at < timezone.now()

    def _set_id_as_code(self) -> None:
        self.id_as_code = '0' * (self._id_length_ - len(str(self.id))) + str(self.id)

        return None

    def save(self, *args, **kwargs):
        is_adding = self._state.adding

        data = super().save(**kwargs)

        if is_adding:
            self._set_id_as_code()
            self.__class__.objects.filter(
                pk=self.pk
            ).update(
                id_as_code=self.id_as_code
            )

        return data
