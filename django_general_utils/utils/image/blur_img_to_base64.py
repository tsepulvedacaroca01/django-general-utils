import base64
import os
from io import BytesIO

from PIL import Image, ImageFilter
from django.conf import settings
from django.core.files import File as DjangoFile

base_dir = [settings.BASE_DIR, 'django_general_utils', 'utils', 'image', 'assets', 'default.png']


def blur_img_to_base64(file: DjangoFile | str, size_img_blur=(25, 25), with_exception=True) -> str:
    """
    blur image and return base64
    """
    try:
        img = Image.open(file)
        img.thumbnail(size_img_blur, Image.LANCZOS)
        img.filter(ImageFilter.GaussianBlur(radius=5))

        buffered = BytesIO()

        img.save(buffered, format='BMP')

        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        if with_exception:
            return blur_img_to_base64(
                os.path.join(*base_dir),
                size_img_blur,
                False
            )

        raise e
