import os
import unittest

import django
from django.conf import settings

if not settings.configured:
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

from django_general_utils.context_processors.envs import export_envs
from django_general_utils.templatetags.call_method import call_method
from django_general_utils.templatetags.dict_get import dict_get


class DictGetTagTests(unittest.TestCase):
    def test_existing_key(self):
        self.assertEqual(dict_get({'a': 1}, 'a'), 1)

    def test_missing_key_returns_default_none(self):
        self.assertIsNone(dict_get({'a': 1}, 'b'))

    def test_missing_key_returns_custom_default(self):
        self.assertEqual(dict_get({'a': 1}, 'b', default='fallback'), 'fallback')

    def test_falsy_value_is_returned_not_default(self):
        self.assertEqual(dict_get({'a': 0}, 'a', default='fallback'), 0)


class CallMethodTagTests(unittest.TestCase):
    def test_calls_method_without_args(self):
        class Obj:
            def greet(self):
                return 'hi'

        self.assertEqual(call_method(Obj(), 'greet'), 'hi')

    def test_calls_method_with_positional_args(self):
        class Obj:
            def add(self, a, b):
                return a + b

        self.assertEqual(call_method(Obj(), 'add', 2, 3), 5)

    def test_calls_method_with_keyword_args(self):
        class Obj:
            def greet(self, name='world'):
                return f'hi {name}'

        self.assertEqual(call_method(Obj(), 'greet', name='Tom'), 'hi Tom')

    def test_missing_method_raises_attribute_error(self):
        class Obj:
            pass

        with self.assertRaises(AttributeError):
            call_method(Obj(), 'does_not_exist')


class ExportEnvsContextProcessorTests(unittest.TestCase):
    def test_returns_env_key_with_os_environ(self):
        os.environ['DJANGO_GENERAL_UTILS_TEST_VAR'] = 'test-value'
        self.addCleanup(os.environ.pop, 'DJANGO_GENERAL_UTILS_TEST_VAR', None)

        context = export_envs(request=None)

        self.assertIn('ENV', context)
        self.assertEqual(context['ENV']['DJANGO_GENERAL_UTILS_TEST_VAR'], 'test-value')

    def test_env_is_the_live_os_environ_mapping(self):
        context = export_envs(request=None)

        self.assertIs(context['ENV'], os.environ)


if __name__ == '__main__':
    unittest.main()
