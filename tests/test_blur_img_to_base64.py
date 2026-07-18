import base64
import unittest
from io import BytesIO

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

from PIL import Image, UnidentifiedImageError

from django_general_utils.utils.image.blur import DEFAULT_BLUR_CODE
from django_general_utils.utils.image.blur_img_to_base64 import blur_img_to_base64


def _make_image_bytes(size=(50, 50), color=(255, 0, 0)) -> BytesIO:
    buffer = BytesIO()
    Image.new('RGB', size, color).save(buffer, format='PNG')
    buffer.seek(0)

    return buffer


class DefaultBlurCodeTests(unittest.TestCase):
    def test_is_valid_base64_bmp(self):
        decoded = base64.b64decode(DEFAULT_BLUR_CODE)

        self.assertEqual(decoded[:2], b'BM')


class BlurImgToBase64Tests(unittest.TestCase):
    def test_valid_image_returns_base64_bmp(self):
        result = blur_img_to_base64(_make_image_bytes())

        decoded = base64.b64decode(result)
        self.assertEqual(decoded[:2], b'BM')

    def test_thumbnail_is_applied(self):
        # blur_img_to_base64 always thumbnails down to size_img_blur, so a
        # much larger source image should shrink.
        result = blur_img_to_base64(_make_image_bytes(size=(500, 500)), size_img_blur=(20, 20))

        decoded = base64.b64decode(result)
        img = Image.open(BytesIO(decoded))
        self.assertLessEqual(img.size[0], 20)
        self.assertLessEqual(img.size[1], 20)

    def test_blur_is_not_actually_applied_current_behavior(self):
        # Known bug: img.filter(ImageFilter.GaussianBlur(...)) return value
        # is discarded (never reassigned to `img`), so the output is
        # pixel-identical to a plain thumbnail+BMP-encode with no blur at
        # all. This test documents that current (buggy) behavior.
        source = _make_image_bytes(size=(20, 20))
        result = blur_img_to_base64(source, size_img_blur=(20, 20))

        source.seek(0)
        expected_img = Image.open(source)
        expected_img.thumbnail((20, 20), Image.LANCZOS)
        expected_buffer = BytesIO()
        expected_img.save(expected_buffer, format='BMP')
        expected = base64.b64encode(expected_buffer.getvalue()).decode('utf-8')

        self.assertEqual(result, expected)

    def test_invalid_file_returns_default_blur_code_by_default(self):
        # with_exception=True (the default) actually SUPPRESSES exceptions
        # and returns the fallback code -- the parameter name reads
        # backwards from what it does.
        result = blur_img_to_base64(BytesIO(b'not an image'))

        self.assertEqual(result, DEFAULT_BLUR_CODE)

    def test_invalid_file_raises_when_with_exception_false(self):
        with self.assertRaises(UnidentifiedImageError):
            blur_img_to_base64(BytesIO(b'not an image'), with_exception=False)


if __name__ == '__main__':
    unittest.main()
