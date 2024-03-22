from django.db import models
from django.db.models import Case, When, Value, BooleanField, TextField
from django.db.models.base import ModelBase
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _
from model_utils import FieldTracker
from ordered_model.models import OrderedModel
from queryable_properties.properties import queryable_property
from safedelete import SOFT_DELETE_CASCADE
from safedelete.config import FIELD_NAME
from safedelete.models import SafeDeleteModel
from .managers.base import BaseModelManager
from .querysets.base import BaseModelQuerySet
from .simple_history import HistoricalRecords
from .uuid import UUIDModel
from ..models import fields
from ..models.constraints import UniqueConstraint
from ..utils.image.blur_img_to_base64 import blur_img_to_base64, DEFAULT_BLUR_CODE


def register_model_signals(app_name: str):
    from django.apps import apps

    app_config = apps.get_app_config(app_name)

    for _model in app_config.get_models():
        if issubclass(_model, BaseModel):
            for _signal in _model._signals:
                _signal.set_model(_model)
                _signal.register()

    return None


def set_blur_fields(cls):
    fields = getattr(cls, '_images_field_to_blur')
    suffix = getattr(cls, '_suffix_blur_code')

    for _field in fields:
        cls.add_to_class(
            f'{_field}_{suffix}',
            TextField(
                editable=False,
                default=DEFAULT_BLUR_CODE
            )
        )

    return cls


class SignalRegister:
    callback = None
    signal = None
    model = None

    def __init__(self, callback, signal, **kwargs):
        self.callback = callback
        self.signal = signal
        self.kwargs = kwargs

    def set_model(self, model):
        self.model = model

    def register(self):
        assert self.model is not None, _('Model is not set')

        self.signal.connect(self.callback, sender=self.model, **self.kwargs)

class ModelBaseMeta(ModelBase):
    def __new__(cls, name, bases, attrs):
        super_new = super().__new__

        if 'Meta' in attrs and getattr(attrs['Meta'], 'abstract', False):
            return super_new(cls, name, bases, attrs)

        if 'history' not in attrs:
            attrs['history'] = HistoricalRecords()

        if 'tracker' not in attrs:
            attrs['tracker'] = FieldTracker()

        Meta = attrs.get('Meta', None)
        signals = []

        if Meta is not None and hasattr(Meta, 'signals'):
            signals = Meta.signals
            del Meta.signals

        model_class = super_new(cls, name, bases, attrs)

        meta = model_class._meta

        if not hasattr(meta, 'constraints'):
            meta.constraints = []

        cls._validate_related_fields(model_class, meta, attrs)
        model_class.add_to_class('_signals', signals)

        return model_class

    @staticmethod
    def _validate_related_fields(model_class, meta, attrs) -> None:
        for field_name, field in attrs.items():
            if isinstance(field, models.OneToOneField):
                if not isinstance(field, fields.OneToOneField):
                    raise TypeError(
                        _(f'Field "{field_name}" OneToOneField is not supported when inheriting from BaseModel. Use django_general_utils.models.fields.OneToOneField instead.')
                    )
                else:
                    meta.constraints.append(
                        UniqueConstraint(
                            prefix=model_class.__name__.lower(),
                            fields=[field_name],
                            violation_error_message={
                                field_name: _('Ya existe un registro con este valor.'),
                            },
                        )
                    )

            if isinstance(field, models.ForeignKey) and (not isinstance(field, (fields.ForeignKey, fields.OneToOneField))):
                raise TypeError(
                    _(f'Field "{field_name}" model.ForeignKey is not supported when inheriting from BaseModel. Use django_general_utils.models.fields.ForeignKey instead.')
                )

        return None

class BaseModel(SafeDeleteModel, OrderedModel, UUIDModel, metaclass=ModelBaseMeta):
    _images_field_to_blur = []
    _queryable_property_params = {}
    _suffix_blur_code = 'blur_code'
    _safedelete_policy = SOFT_DELETE_CASCADE
    _signals = []
    objects = BaseModelManager(BaseModelQuerySet)

    class Meta:
        abstract = True
        ordering = ('-id',)

    @classmethod
    def get_queryable_property_params(cls, key: str, default=None):
        """
        Get the filter to be used when querying queryable properties.
        """
        return cls._queryable_property_params.get(key, default)

    @queryable_property(annotation_based=True)
    @classmethod
    def is_deleted(cls) -> bool:
        # noinspection PyTypeChecker
        return Case(
            When(**{f'{FIELD_NAME}__lt': Now(), 'then': Value(True)}),
            default=Value(False),
            output_field=BooleanField()
        )

    def set_blur_image(self, field: str) -> None:
        """
        _set_blur_image
        @return:
        """
        setattr(
            self,
            f'{field}_{self._suffix_blur_code}',
            blur_img_to_base64(getattr(self, field))
        )

        return None

    def save(self, **kwargs):
        keep_deleted = kwargs.pop('keep_deleted', False)
        full_clean = kwargs.pop('full_clean', True)

        if not keep_deleted:
            if getattr(self, FIELD_NAME) and self.pk:
                # if the object was undeleted, we need to reset the order
                self.order = self.get_ordering_queryset().get_next_order()

            setattr(self, FIELD_NAME, None)

        for _field in self._images_field_to_blur:
            self.set_blur_image(_field)

        if full_clean:
            self.full_clean()

        super().save(keep_deleted, **kwargs)
