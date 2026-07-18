import json
import tempfile
import unittest
from pathlib import Path

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

from django_general_utils.utils.file_to_json import file_to_json


class FileToJsonTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.dir_path = Path(self._tmp_dir.name)

    def _write(self, name: str, content: str) -> str:
        path = self.dir_path / name
        path.write_text(content, encoding='utf-8')

        return str(path)

    def test_valid_json_object_returns_dict(self):
        path = self._write('valid.json', json.dumps({'a': 1, 'b': 'two'}))

        self.assertEqual(file_to_json(path), {'a': 1, 'b': 'two'})

    def test_valid_json_array_returns_list_despite_type_hint(self):
        path = self._write('array.json', json.dumps([1, 2, 3]))

        self.assertEqual(file_to_json(path), [1, 2, 3])

    def test_malformed_json_raises_decode_error(self):
        path = self._write('bad.json', '{not valid json')

        with self.assertRaises(json.JSONDecodeError):
            file_to_json(path)

    def test_missing_file_raises_file_not_found(self):
        missing_path = str(self.dir_path / 'does-not-exist.json')

        with self.assertRaises(FileNotFoundError):
            file_to_json(missing_path)

    def test_directory_path_raises_is_a_directory_error(self):
        with self.assertRaises(IsADirectoryError):
            file_to_json(str(self.dir_path))


if __name__ == '__main__':
    unittest.main()
