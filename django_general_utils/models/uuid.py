import uuid

from django.db import models
from django.db.models import Case, When, Value, BooleanField
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _
from model_utils.fields import AutoCreatedField, AutoLastModifiedField
from queryable_properties.properties import queryable_property


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

    @queryable_property(annotation_based=True)
    @classmethod
    def is_stopped(cls):
        return Case(
            When(
                stopped_at__lt=Now(),
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField()
        )

    def _set_id_as_code(self) -> None:
        self.id_as_code = '0' * (self._id_length_ - len(str(self.id))) + str(self.id)

        return None

    def get_next_code(self) -> str:
        """
        @summary: Get next code
        @return: str
        """
        # TODO: TEST
        last_code = self.__class__.objects.all_with_deleted().order_by(
            '-id'
        ).first()

        if last_code is None:
            return '0' * (self._id_length_ - 1) + '1'

        return '0' * (self._id_length_ - len(str(last_code.id + 1))) + str(last_code.id + 1)

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
