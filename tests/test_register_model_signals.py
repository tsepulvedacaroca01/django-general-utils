import unittest
from unittest import mock

import django
from django.conf import settings

if not settings.configured:
    import os

    settings.configure(
        BASE_DIR=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'django_general_utils')),
        DEBUG=True,
        SECRET_KEY='test-secret-key',
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        INSTALLED_APPS=(
            'django.contrib.auth',
            'django.contrib.contenttypes',
        ),
        TIME_ZONE='UTC',
        USE_TZ=True,
        DEFAULT_AUTO_FIELD='django.db.models.AutoField',
    )
    django.setup()

from django.core.management import call_command
from django.db import connection, models
from django.db.models.signals import post_save

from django_general_utils.models import BaseV3
from django_general_utils.models.base import SignalRegister, register_model_signals

_signal_calls = []


def _record_call(sender, instance, **kwargs):
    _signal_calls.append(instance.pk)


class SignalRegisterV3Model(BaseV3):
    name = models.CharField(max_length=64, null=True, blank=True)

    class Meta(BaseV3.Meta):
        app_label = 'tests'
        db_table = 'test_signal_register_v3_model'
        signals = [SignalRegister(callback=_record_call, signal=post_save)]


class _FakeAppConfig:
    def __init__(self, models_list):
        self._models = models_list

    def get_models(self):
        return self._models


class RegisterModelSignalsBaseV3Tests(unittest.TestCase):
    """
    Regression: `register_model_signals` only recognized `(BaseModel, BaseWithoutSafeDeleteModel)`
    — a concrete `BaseV3` model with `Meta.signals` declared would silently fall into the `else`
    branch. `issubclass(_model, models.Model)` still passed there (`BaseV3` *is* a `models.Model`),
    so nothing crashed — the signal connection was just never made, silently. Uses a fake
    `AppConfig` (via `apps.get_app_config`) instead of a real installed app, since this repo's test
    settings don't register a real `AppConfig` for the `app_label='tests'` throwaway pattern (see
    `docs/00-contexto-libreria.md`).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command('migrate', 'contenttypes', verbosity=0)
        call_command('migrate', 'auth', verbosity=0)
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(SignalRegisterV3Model)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(SignalRegisterV3Model)
        super().tearDownClass()

    def setUp(self):
        SignalRegisterV3Model.objects.all().delete()
        _signal_calls.clear()

    def test_registers_signals_declared_on_a_basev3_model(self):
        with mock.patch('django.apps.apps.get_app_config', return_value=_FakeAppConfig([SignalRegisterV3Model])):
            register_model_signals('tests')

        instance = SignalRegisterV3Model.objects.create(name='x')

        self.assertIn(instance.pk, _signal_calls)

    def test_does_not_crash_for_basev3_model_without_signals(self):
        class _NoSignalsModel(BaseV3):
            class Meta(BaseV3.Meta):
                app_label = 'tests'
                db_table = 'test_no_signals_v3_model'

        with mock.patch('django.apps.apps.get_app_config', return_value=_FakeAppConfig([_NoSignalsModel])):
            self.assertIsNone(register_model_signals('tests'))


if __name__ == '__main__':
    unittest.main()
