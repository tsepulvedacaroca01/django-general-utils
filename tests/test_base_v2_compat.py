import importlib
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

from django_general_utils.models import BaseV2, BaseWithoutSafeDeleteModel
from django_general_utils.models.base_v2 import BaseV2 as BaseV2FromModule
from django_general_utils.models.base_v2 import ModelBaseV2Meta
from django_general_utils.models.base_without_safe_delete import (
    BaseWithoutSafeDeleteModel as BaseWithoutSafeDeleteModelFromModule,
)
from django_general_utils.models.base_without_safe_delete import ModelBaseWithOutSafeDeleteMeta
from django_general_utils.models.managers.base_v2 import BaseV2Manager
from django_general_utils.models.managers.base_without_safe_delete import (
    BaseWithoutSafeDeleteModelManager,
)


class BaseV2RenameCompatTests(unittest.TestCase):
    """
    `base_without_safe_delete.py` was renamed to `base_v2.py` (`BaseWithoutSafeDeleteModel` ->
    `BaseV2`). Every import path a consumer project might already use must keep resolving to
    the exact same class, not just an equivalent one, since Django's `issubclass()`-based
    checks (constraints, signal registration, etc.) rely on class identity.
    """

    def test_package_level_aliases_are_the_same_class(self):
        self.assertIs(BaseV2, BaseWithoutSafeDeleteModel)

    def test_module_level_names_match_package_level_names(self):
        self.assertIs(BaseV2, BaseV2FromModule)
        self.assertIs(BaseWithoutSafeDeleteModel, BaseWithoutSafeDeleteModelFromModule)

    def test_old_and_new_module_paths_resolve_to_the_same_class(self):
        self.assertIs(BaseV2FromModule, BaseWithoutSafeDeleteModelFromModule)

    def test_metaclass_alias_is_the_same_class(self):
        self.assertIs(ModelBaseV2Meta, ModelBaseWithOutSafeDeleteMeta)


class BaseV2ManagerRenameCompatTests(unittest.TestCase):
    """
    Same rename, same guarantee, for `managers/base_without_safe_delete.py` ->
    `managers/base_v2.py` (`BaseWithoutSafeDeleteModelManager` -> `BaseV2Manager`).
    """

    def test_alias_is_the_same_class(self):
        self.assertIs(BaseV2Manager, BaseWithoutSafeDeleteModelManager)


class DeprecationWarningTests(unittest.TestCase):
    """
    Each renamed module exposes its old name(s) only through a module-level `__getattr__`
    (PEP 562), which is what lets it emit a `DeprecationWarning` on every access instead of just
    once when the module is first imported. `getattr(module, name)` re-triggers `__getattr__`
    every time (the shims don't cache), which is what makes `assertWarns` reliable here even
    though the module-level imports above already "used up" the warning once at collection time.
    """

    def test_package_level_alias_warns(self):
        module = importlib.import_module('django_general_utils.models')

        with self.assertWarns(DeprecationWarning) as ctx:
            _ = module.BaseWithoutSafeDeleteModel

        self.assertIn('django_general_utils.models.BaseWithoutSafeDeleteModel', str(ctx.warning))
        self.assertIn('django_general_utils.models.BaseV2', str(ctx.warning))

    def test_base_module_alias_warns(self):
        module = importlib.import_module('django_general_utils.models.base_without_safe_delete')

        with self.assertWarns(DeprecationWarning):
            _ = module.BaseWithoutSafeDeleteModel

        with self.assertWarns(DeprecationWarning):
            _ = module.ModelBaseWithOutSafeDeleteMeta

    def test_manager_module_alias_warns(self):
        module = importlib.import_module('django_general_utils.models.managers.base_without_safe_delete')

        with self.assertWarns(DeprecationWarning) as ctx:
            _ = module.BaseWithoutSafeDeleteModelManager

        self.assertIn(
            'django_general_utils.models.managers.base_without_safe_delete.BaseWithoutSafeDeleteModelManager',
            str(ctx.warning),
        )
        self.assertIn('django_general_utils.models.managers.base_v2.BaseV2Manager', str(ctx.warning))

    def test_unknown_attribute_still_raises_attribute_error(self):
        module = importlib.import_module('django_general_utils.models.base_without_safe_delete')

        with self.assertRaises(AttributeError):
            _ = module.ThisDoesNotExist


if __name__ == '__main__':
    unittest.main()
