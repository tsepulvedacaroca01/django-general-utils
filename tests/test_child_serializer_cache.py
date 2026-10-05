import unittest

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

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from django_general_utils.utils.drf.fields import LazyRefSerializerField, NestedPrimaryKeyRelatedField
from django_general_utils.utils.rest_ql import DynamicFieldsMixin

# ---------------------------------------------------------------------------
# `CachedChildSerializerMixin`: the nested serializer of `NestedPrimaryKeyRelatedField` /
# `LazyRefSerializerField` is built once per bound field, not once per rendered object.
# Everything runs on UNSAVED instances (no table needed): `LazyRefSerializerField` only hits the
# database when it receives a pk instead of an instance.
# ---------------------------------------------------------------------------

BUILT = []


class ContentTypeSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        BUILT.append(self.__class__.__name__)
        super().__init__(*args, **kwargs)

    class Meta:
        model = ContentType
        fields = ['app_label', 'model']


class NestedPermissionSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    content_type = NestedPrimaryKeyRelatedField(
        serializer_class=ContentTypeSerializer, queryset=ContentType.objects.all(),
    )

    class Meta:
        model = Permission
        fields = ['codename', 'content_type']


class LazyPermissionSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    content_type = LazyRefSerializerField(serializer_class=ContentTypeSerializer)

    class Meta:
        model = Permission
        fields = ['codename', 'content_type']


def build_permissions(count):
    return [
        Permission(
            codename=f'perm_{i}',
            name=f'Perm {i}',
            content_type=ContentType(app_label=f'app_{i % 3}', model=f'model_{i}'),
        )
        for i in range(count)
    ]


class ChildSerializerCacheTests(unittest.TestCase):
    def setUp(self):
        BUILT.clear()

    def test_nested_pk_field_builds_the_child_serializer_once_for_a_list(self):
        data = NestedPermissionSerializer(build_permissions(25), many=True, context={}).data

        self.assertEqual(len(data), 25)
        self.assertEqual(BUILT.count('ContentTypeSerializer'), 1)

    def test_lazy_ref_field_builds_the_child_serializer_once_for_a_list(self):
        data = LazyPermissionSerializer(build_permissions(25), many=True, context={}).data

        self.assertEqual(len(data), 25)
        self.assertEqual(BUILT.count('ContentTypeSerializer'), 1)

    def test_payload_is_identical_to_a_serializer_built_per_object(self):
        permissions = build_permissions(12)

        for serializer_class in (NestedPermissionSerializer, LazyPermissionSerializer):
            cached = serializer_class(permissions, many=True, context={}).data

            serializer = serializer_class(context={})
            fresh = []
            for permission in permissions:
                field = serializer.fields['content_type']
                nested = field.get_serializer(instance=permission.content_type).data
                fresh.append({'codename': permission.codename, 'content_type': dict(nested)})

            self.assertEqual([dict(row) | {'content_type': dict(row['content_type'])} for row in cached], fresh)

    def test_each_row_gets_its_own_nested_values(self):
        data = NestedPermissionSerializer(build_permissions(6), many=True, context={}).data

        self.assertEqual([row['content_type']['model'] for row in data], [f'model_{i}' for i in range(6)])

    def test_cache_is_not_shared_between_serializer_instances(self):
        permissions = build_permissions(3)

        for _ in range(2):
            _ = NestedPermissionSerializer(permissions, many=True, context={}).data

        self.assertEqual(BUILT.count('ContentTypeSerializer'), 2)

    def test_get_serializer_still_returns_a_new_instance_each_call(self):
        serializer = NestedPermissionSerializer(context={})
        field = serializer.fields['content_type']

        first, second = field.get_serializer(), field.get_serializer()

        self.assertIsNot(first, second)

    def test_replaced_context_rebuilds_the_cached_serializer(self):
        serializer = NestedPermissionSerializer(build_permissions(1)[0], context={'a': 1})
        _ = serializer.data
        field = serializer.fields['content_type']
        before = field.get_cached_serializer()

        self.assertIs(field.get_cached_serializer(), before)

        serializer._context = {'a': 2}

        self.assertIsNot(field.get_cached_serializer(), before)
        self.assertEqual(field.get_cached_serializer().context, {'a': 2})

    def test_lazy_ref_field_still_resolves_a_pk_through_the_database(self):
        field = LazyRefSerializerField(serializer_class=ContentTypeSerializer)
        field.bind('content_type', NestedPermissionSerializer(context={}))
        content_type = ContentType(app_label='app', model='model')

        self.assertEqual(dict(field.to_representation(content_type)), {'app_label': 'app', 'model': 'model'})


if __name__ == '__main__':
    unittest.main()
