import uuid

from django.conf import settings
from django.db import models
from django.db.models import Case, When, Value, BooleanField
from django.db.models import Max
from django.db.models.functions import Now, Concat, Length, Cast, Repeat
from django.utils.translation import gettext_lazy as _
from django_middleware_global_request import get_request
from model_utils.fields import AutoCreatedField, AutoLastModifiedField
from queryable_properties.properties import queryable_property


class UUIDModelV2(models.Model):
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
        unique=True,
        primary_key=True,
    )
    id = models.PositiveBigIntegerField(
        editable=False,
        null=True,
        blank=True,
        unique=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = AutoCreatedField(_('created_at'))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name='%(class)ss_created_by',
    )
    updated_at = AutoLastModifiedField(_('updated_at'))
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name='%(class)ss_updated_by',
    )
    stopped_at = models.DateTimeField(
        null=True,
        blank=True
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

    @queryable_property(annotation_based=True, cached=True)
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
        last_code = cls.objects.all_with_deleted().order_by(
            '-id'
        ).first()

        if last_code is None:
            next_code = '0' * (cls._ID_AS_CODE_LENGTH_ - 1) + '1'
        else:
            next_code = '0' * (cls._ID_AS_CODE_LENGTH_ - len(str(last_code.pk + 1))) + str(last_code.pk + 1)

        return f'{cls._ID_AS_CODE_PREFIX_}{next_code}{cls._ID_AS_CODE_SUFFIX_}'

    @classmethod
    def max_id(cls) -> int:
        """
        """
        return cls.objects.all().aggregate(id__max=Max('id')).get('id__max', 0) or 0

    def set_created_by(self, user = None) -> None:
        """
        Set created_by field.
        @param user:
        """
        if self.created_by is not None:
            return None

        if user is not None:
            self.created_by = user
            return None

        # """Set user from middleware."""
        request = get_request()

        if request is None:
            return None

        if request.user.is_anonymous:
            return None

        self.created_by = request.user

        return None

    def set_updated_by(self, user = None) -> None:
        """
        Set updated_by field.
        @param user:
        """
        if user is not None:
            self.updated_by = user
            return None

        # """Set user from middleware."""
        request = get_request()

        if request is None:
            return None

        if request.user.is_anonymous:
            return None

        self.updated_by = request.user

        return None

    def save(self, *args, **kwargs):
        """
        Save instance and set created_by.
        """
        if self._state.adding:
            self.set_created_by()

        self.set_updated_by()

        if self.id is None:
            self.id = self.max_id() + 1

        super().save(*args, **kwargs)
