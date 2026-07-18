import unittest
from importlib import import_module
from unittest.mock import MagicMock

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

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import override_settings
from rest_framework import serializers
from rest_framework.exceptions import NotFound

from django_general_utils.utils.delete_cache import delete_cache
from django_general_utils.utils.drf.exception_handler import exception_handler
from django_general_utils.utils.drf.fields.multiple_choice_field import MultipleChoiceField
from django_general_utils.utils.drf.validation_errors import (
    ListValidationError,
    ValidationError400,
    ValidationError401,
    ValidationError404,
    ValidationError406,
    ValidationError429,
    ValidationError501,
)
from django_general_utils.utils.drf.validations.fields import MinMaxElementsValidator
from django_general_utils.utils.forms.field.select import DataAttributesSelect


class _ItemsSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.CharField(), required=True)


class MinMaxElementsValidatorConstructorTests(unittest.TestCase):
    def test_keys_is_required(self):
        with self.assertRaises(AssertionError):
            MinMaxElementsValidator(min=1, keys=None)

    def test_min_or_max_is_required(self):
        with self.assertRaises(AssertionError):
            MinMaxElementsValidator(keys=['items'])

    def test_min_only_is_valid(self):
        validator = MinMaxElementsValidator(min=1, keys=['items'])

        self.assertEqual(validator.min, 1)


class MinMaxElementsValidatorCallTests(unittest.TestCase):
    def test_within_bounds_passes(self):
        validator = MinMaxElementsValidator(min=1, max=3, keys=['items'])
        serializer = _ItemsSerializer(data={'items': ['a', 'b']})

        validator({'items': ['a', 'b']}, serializer)

    def test_below_min_raises(self):
        validator = MinMaxElementsValidator(min=2, max=3, keys=['items'])
        serializer = _ItemsSerializer(data={'items': ['a']})

        with self.assertRaises(serializers.ValidationError) as ctx:
            validator({'items': ['a']}, serializer)

        self.assertEqual(
            ctx.exception.detail['items'],
            ['La lista debe tener al menos 2 elemento(s).'],
        )

    def test_above_max_raises(self):
        validator = MinMaxElementsValidator(min=1, max=2, keys=['items'])
        serializer = _ItemsSerializer(data={'items': ['a', 'b', 'c']})

        with self.assertRaises(serializers.ValidationError) as ctx:
            validator({'items': ['a', 'b', 'c']}, serializer)

        self.assertEqual(
            ctx.exception.detail['items'],
            ['La lista debe tener como máximo 2 elemento(s).'],
        )

    def test_missing_required_key_on_non_partial_serializer_raises_assertion(self):
        validator = MinMaxElementsValidator(min=1, keys=['items'])
        serializer = _ItemsSerializer(data={})

        with self.assertRaises(AssertionError):
            validator({}, serializer)

    def test_required_constructor_param_is_dead_and_does_not_prevent_the_assertion(self):
        # Known bug: `required` is stored on the instance but never read
        # inside __call__ -- it checks serializer.fields[key].required
        # instead. Passing required=False changes nothing.
        validator = MinMaxElementsValidator(min=1, keys=['items'], required=False)
        serializer = _ItemsSerializer(data={})

        with self.assertRaises(AssertionError):
            validator({}, serializer)

    def test_partial_serializer_skips_missing_key_entirely(self):
        validator = MinMaxElementsValidator(min=1, keys=['items'])
        serializer = _ItemsSerializer(data={}, partial=True)

        validator({}, serializer)


class ListValidationErrorTests(unittest.TestCase):
    def test_error_list_maps_message_dicts(self):
        error = DjangoValidationError({'field': ['bad']})
        list_error = ListValidationError([error])

        self.assertEqual(list_error.error_list, [{'field': ['bad']}])

    def test_plain_message_error_raises_attribute_error(self):
        plain_error = DjangoValidationError('plain message')
        list_error = ListValidationError([plain_error])

        with self.assertRaises(AttributeError):
            _ = list_error.error_list


class ValidationErrorSubclassesTests(unittest.TestCase):
    def test_status_codes(self):
        self.assertEqual(ValidationError400.status_code, 400)
        self.assertEqual(ValidationError401.status_code, 401)
        self.assertEqual(ValidationError404.status_code, 404)
        self.assertEqual(ValidationError406.status_code, 406)
        self.assertEqual(ValidationError429.status_code, 429)
        self.assertEqual(ValidationError501.status_code, 501)

    def test_custom_detail_message(self):
        exc = ValidationError400('custom message')

        self.assertEqual(str(exc.detail), 'custom message')


class ExceptionHandlerTests(unittest.TestCase):
    def test_dict_shaped_validation_error_returns_400(self):
        # Note: exception_handler uses exc.error_dict directly, which -
        # unlike exc.message_dict (used by ListValidationError.error_list
        # below) - does NOT flatten to plain strings: each value stays a
        # list of nested ValidationError objects, not plain messages. This
        # is inconsistent with the ListValidationError path and likely
        # isn't cleanly JSON-serializable by DRF's renderer.
        exc = DjangoValidationError({'field': ['bad']})

        response = exception_handler(exc, {'view': None, 'request': None})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['field'][0].messages, ['bad'])

    def test_list_validation_error_returns_400(self):
        exc = ListValidationError([DjangoValidationError({'field': ['bad']})])

        response = exception_handler(exc, {'view': None, 'request': None})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, [{'field': ['bad']}])

    def test_standard_drf_exception_passes_through(self):
        response = exception_handler(NotFound(), {'view': None, 'request': None})

        self.assertEqual(response.status_code, 404)

    def test_unrecognized_exception_returns_none(self):
        response = exception_handler(ValueError('oops'), {'view': None, 'request': None})

        self.assertIsNone(response)


class MultipleChoiceFieldTests(unittest.TestCase):
    def test_to_representation_returns_list(self):
        field = MultipleChoiceField(choices=['a', 'b', 'c'])

        result = field.to_representation({'a', 'b'})

        self.assertIsInstance(result, list)
        self.assertEqual(set(result), {'a', 'b'})


class DataAttributesSelectTests(unittest.TestCase):
    def test_injects_data_attribute_for_matching_value(self):
        widget = DataAttributesSelect(
            choices=[('1', 'One'), ('2', 'Two')],
            data={'data-foo': {'1': 'bar1', '2': 'bar2'}},
        )

        option = widget.create_option('field', '1', 'One', False, 0)

        self.assertEqual(option['attrs']['data-foo'], 'bar1')

    def test_missing_value_in_data_mapping_raises_key_error(self):
        widget = DataAttributesSelect(choices=[('1', 'One')], data={'data-foo': {}})

        with self.assertRaises(KeyError):
            widget.create_option('field', '1', 'One', False, 0)

    def test_passed_in_attrs_argument_is_discarded(self):
        # Known bug: create_option hardcodes subindex=None, attrs=None in
        # the super() call, discarding whatever the caller actually passed.
        widget = DataAttributesSelect(choices=[('1', 'One')])

        option = widget.create_option('field', '1', 'One', False, 0, subindex=99, attrs={'class': 'my-class'})

        self.assertNotIn('class', option['attrs'])


class DeleteCacheTests(unittest.TestCase):
    def test_no_caches_configured_returns_none(self):
        with override_settings(CACHES={}):
            self.assertIsNone(delete_cache('key'))

    def test_non_redis_backend_returns_none(self):
        caches = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

        with override_settings(CACHES=caches):
            self.assertIsNone(delete_cache('key'))

    def _swap_module_cache(self, mock_cache):
        # `mock.patch('...delete_cache.cache')` cannot be used here: it
        # inspects the *original* attribute (Django's lazy cache
        # ConnectionProxy) to decide whether to build an AsyncMock, and that
        # inspection itself resolves the configured backend - which raises
        # ImportError for 'django_redis.cache.RedisCache' since django-redis
        # isn't an installed dependency of this repo. A plain attribute swap
        # avoids touching the original object at all.
        #
        # Note: `django_general_utils.utils.delete_cache` (the module) gets
        # shadowed as an attribute of the `utils` package by the `delete_cache`
        # *function* re-exported in utils/__init__.py (same name as the
        # module) - `import ... as` resolves via attribute traversal, so it
        # would pick up the function instead of the module. import_module()
        # goes through sys.modules directly and avoids that.
        module = import_module('django_general_utils.utils.delete_cache')
        original_cache = module.cache
        module.cache = mock_cache
        self.addCleanup(setattr, module, 'cache', original_cache)

    def test_redis_backend_deletes_matching_keys(self):
        caches = {'default': {'BACKEND': 'django_redis.cache.RedisCache'}}
        mock_cache = MagicMock()
        mock_cache.keys.return_value = ['prefix:key:1', 'prefix:key:2']
        self._swap_module_cache(mock_cache)

        with override_settings(CACHES=caches):
            delete_cache('key')

        mock_cache.keys.assert_called_once_with('*key*')
        mock_cache.delete_many.assert_called_once_with(['prefix:key:1', 'prefix:key:2'])

    def test_redis_backend_no_matching_keys_does_not_call_delete_many(self):
        caches = {'default': {'BACKEND': 'django_redis.cache.RedisCache'}}
        mock_cache = MagicMock()
        mock_cache.keys.return_value = []
        self._swap_module_cache(mock_cache)

        with override_settings(CACHES=caches):
            delete_cache('key')

        mock_cache.delete_many.assert_not_called()


if __name__ == '__main__':
    unittest.main()
