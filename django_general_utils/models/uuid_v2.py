import hashlib
import uuid

from django.conf import settings
from django.db import IntegrityError, connections, models, router, transaction
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
    _MAX_AUTO_ID_RETRIES_ = 10
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
        ordering = ('-created_at',)

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
        last_code = cls._id_queryset().filter(id__isnull=False).order_by(
            '-id'
        ).first()

        if last_code is None:
            next_code = '0' * (cls._ID_AS_CODE_LENGTH_ - 1) + '1'
        else:
            next_id = last_code.id + 1
            next_code = '0' * (cls._ID_AS_CODE_LENGTH_ - len(str(next_id))) + str(next_id)

        return f'{cls._ID_AS_CODE_PREFIX_}{next_code}{cls._ID_AS_CODE_SUFFIX_}'

    @classmethod
    def _id_queryset(cls, using=None):
        manager = cls.objects

        if hasattr(manager, 'all_with_deleted') and callable(manager.all_with_deleted):
            queryset = manager.all_with_deleted()
        else:
            queryset = manager.all()

        if using is not None:
            queryset = queryset.using(using)

        return queryset

    @classmethod
    def _id_lock_key(cls) -> int:
        digest = hashlib.blake2b(
            cls._meta.db_table.encode('utf-8'),
            digest_size=8,
        ).digest()
        return int.from_bytes(digest, byteorder='big', signed=True)

    @classmethod
    def _lock_id_generation(cls, using=None) -> None:
        connection = connections[using or router.db_for_write(cls)]

        if connection.vendor != 'postgresql':
            return None

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT pg_advisory_xact_lock(%s)',
                [cls._id_lock_key()],
            )

        return None

    @classmethod
    def max_id(cls, using=None) -> int:
        """
        """
        return cls._id_queryset(using=using).aggregate(id__max=Max('id')).get('id__max', 0) or 0

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

        if self.id is not None or not self._state.adding:
            return super().save(*args, **kwargs)

        using = kwargs.get('using') or router.db_for_write(self.__class__, instance=self)

        for attempt in range(self._MAX_AUTO_ID_RETRIES_):
            try:
                with transaction.atomic(using=using):
                    self.__class__._lock_id_generation(using=using)
                    self.id = self.max_id(using=using) + 1
                    return super().save(*args, **kwargs)
            except IntegrityError:
                conflicting_id = self.id
                self.id = None

                if conflicting_id is None:
                    raise

                id_already_exists = self.__class__._id_queryset(using=using).filter(id=conflicting_id).exists()

                if (not id_already_exists) or attempt == (self._MAX_AUTO_ID_RETRIES_ - 1):
                    raise

        raise RuntimeError(_('Could not generate a unique automatic id after several retries.'))
