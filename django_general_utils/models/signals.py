from django.db import models
from django.db.models.signals import m2m_changed
from django.utils.translation import gettext_lazy as _


def register_model_signals(app_name: str):
    from django.apps import apps
    from .base_without_safe_delete import BaseWithoutSafeDeleteModel
    from .base import BaseModel

    app_config = apps.get_app_config(app_name)

    for _model in app_config.get_models():
        if issubclass(_model, (BaseModel, BaseWithoutSafeDeleteModel)):
            for _signal in _model._signals:
                _signal.set_model(_model)
                _signal.register()
        else:
            assert issubclass(_model, models.Model), _('Model "%s" is not a subclass of BaseModel or BaseWithoutSafeDeleteModel') % _model.__name__

    return None


class SignalRegister:
    callback = None
    signal = None
    model = None

    def __init__(self, callback, signal, through_field=None, **kwargs):
        self.callback = callback
        self.signal = signal
        self.through_field = through_field
        self.kwargs = kwargs

        if signal is m2m_changed:
            assert through_field is not None, _('through_field is required for m2m_changed signal')

    def set_model(self, model):
        if self.signal is m2m_changed:
            assert hasattr(model, self.through_field), _('Model "%s" does not have the field "%s"') % (model.__name__, self.through_field)

            self.model = getattr(model, self.through_field).through

            return

        self.model = model

    def register(self):
        assert self.model is not None, _('Model is not set')

        self.signal.connect(self.callback, sender=self.model, **self.kwargs)
