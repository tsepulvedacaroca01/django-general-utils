import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Case, When, Value, BooleanField
from django.db.models.functions import Now, Concat, Length, Cast, Repeat
from django.utils.translation import gettext_lazy as _
from django_middleware_global_request import get_request
from model_utils.fields import AutoCreatedField, AutoLastModifiedField
from queryable_properties.properties import queryable_property

from .simple_history import HistoricalRecords

try:
    from asgiref.local import Local as LocalContext
except ImportError:
    from threading import local as LocalContext


class UUIDModel(models.Model):
    """
    An abstract base class model that provides self-updating
    ``id``,  ``created_at`` and ``updated_at`` fields.
    """
    _ID_AS_CODE_LENGTH_ = 7
    _ID_AS_CODE_PREFIX_ = '' # VE-0000001
    _ID_AS_CODE_SUFFIX_ = '' # 0000001-VE
    # BOTH PREFIX AND SUFFIX -> VE-0000001-VE
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True
    )
    is_active = models.BooleanField(default=True)
    created_at = AutoCreatedField(_('created_at'))
    created_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name='%(class)s_created_by',
    )
    updated_at = AutoLastModifiedField(_('updated_at'))
    updated_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name='%(class)s_updated_by',
    )
    stopped_at = models.DateTimeField(
        null=True,
        blank=True
    )
    history = HistoricalRecords(
        inherit=True
    )

    class Meta:
        abstract = True
        ordering = ('-id',)

    @queryable_property(annotation_based=True)
    @classmethod
    def is_stopped(cls) -> bool:
        # noinspection PyTypeChecker
        return Case(
            When(
                stopped_at__lt=Now(),
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField()
        )

    @queryable_property(annotation_based=True)
    @classmethod
    def id_as_code(cls) -> str:
        # noinspection PyTypeChecker
        return Concat(
            Value(cls._ID_AS_CODE_PREFIX_),
            Repeat(
                Value('0'),
                cls._ID_AS_CODE_LENGTH_ - Length(Cast('id', output_field=models.CharField()))
            ),
            Cast('id', output_field=models.CharField()),
            Value(cls._ID_AS_CODE_SUFFIX_)
        )

    @classmethod
    def next_code(cls) -> str:
        """
        @summary: Get next code
        @return: str
        """
        # TODO: TEST
        last_code = cls.objects.all_with_deleted().order_by(
            '-id'
        ).first()

        if last_code is None:
            next_code = '0' * (cls._ID_AS_CODE_LENGTH_ - 1) + '1'
        else:
            next_code = '0' * (cls._ID_AS_CODE_LENGTH_ - len(str(last_code.id + 1))) + str(last_code.id + 1)

        return f'{cls._ID_AS_CODE_PREFIX_}{next_code}{cls._ID_AS_CODE_SUFFIX_}'

    @property
    def _history_user(self):
        return self.updated_by

    @_history_user.setter
    def _history_user(self, value):
        self.updated_by = value

    def _set_created_by(self) -> None:
        """Set user from middleware."""
        request = get_request()

        if request is None:
            return None

        if request.user.is_anonymous:
            return None

        self.created_by = request.user

        return None

    def save(self, *args, **kwargs):
        """
        Save instance and set created_by.
        """
        if self._state.adding:
            self._set_created_by()

        super().save(*args, **kwargs)
