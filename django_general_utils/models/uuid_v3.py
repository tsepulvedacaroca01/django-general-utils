from django.db import models
from django.db.models import Value
from django.db.models.functions import Cast, Concat, Length, Repeat

from ..utils.uuid7 import uuid7
from .uuid_v2 import UUIDModelV2


class UUIDModelV3(UUIDModelV2):
    """
    Same as ``UUIDModelV2`` with two changes:

    - ``uuid`` (the primary key) defaults to a time-ordered UUIDv7 instead of
      a random UUIDv4, which keeps primary-key btree inserts (and therefore
      ``objects.order_by('-uuid')``) sequential instead of random.
    - ``id_as_code`` is a real, indexed column instead of a query-time
      annotation, so filtering/reading it doesn't require recomputing
      ``Concat``/``Repeat``/``Cast`` on every query. It is kept in sync
      automatically wherever ``id`` itself is assigned (single ``save()`` and
      ``bulk_create``); use the ``sync_id_as_code`` management command to
      backfill existing rows after changing ``_ID_AS_CODE_PREFIX_`` /
      ``_ID_AS_CODE_SUFFIX_`` / ``_ID_AS_CODE_LENGTH_``.
    """
    uuid = models.UUIDField(
        default=uuid7,
        editable=False,
        unique=True,
        primary_key=True,
    )
    id_as_code = models.CharField(
        max_length=64,
        editable=False,
        null=True,
        blank=True,
        db_index=True,
    )

    class Meta(UUIDModelV2.Meta):
        abstract = True
        # ``uuid`` (the PK) is now time-ordered, so sorting by it reuses the
        # primary-key index instead of requiring a separate lookup/sort on
        # ``created_at``.
        ordering = ('-uuid',)

    @classmethod
    def _build_id_as_code(cls, id_value: int) -> str:
        padded_id = str(id_value).rjust(cls._ID_AS_CODE_LENGTH_, '0')
        return f'{cls._ID_AS_CODE_PREFIX_}{padded_id}{cls._ID_AS_CODE_SUFFIX_}'

    @classmethod
    def _id_as_code_expression(cls) -> Concat:
        """
        DB-side equivalent of ``_build_id_as_code``, expressed against the
        ``id`` column. Used by the ``sync_id_as_code`` command to detect rows
        whose stored ``id_as_code`` doesn't match the current prefix/suffix/
        length anymore.
        """
        # noinspection PyTypeChecker
        return Concat(
            Value(cls._ID_AS_CODE_PREFIX_),
            Repeat(
                Value('0'),
                cls._ID_AS_CODE_LENGTH_ - Length(Cast('id', output_field=models.CharField()))
            ),
            Cast('id', output_field=models.CharField()),
            Value(cls._ID_AS_CODE_SUFFIX_),
            output_field=models.CharField(),
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

        next_id = cls.get_initial_id() if last_code is None else last_code.id + 1

        return cls._build_id_as_code(next_id)

    def _on_id_assigned(self) -> None:
        if self.id is not None and not self.id_as_code:
            self.id_as_code = self.__class__._build_id_as_code(self.id)

    def _on_id_reset(self) -> None:
        self.id_as_code = None

    @classmethod
    def _on_ids_assigned(cls, objs) -> None:
        for obj in objs:
            if obj.id is not None and not obj.id_as_code:
                obj.id_as_code = cls._build_id_as_code(obj.id)
