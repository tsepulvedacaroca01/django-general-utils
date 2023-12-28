import base64
from io import BytesIO

from PIL import Image, ImageFilter
from django.core.files import File as DjangoFile

from .blur import DEFAULT_BLUR_CODE


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
            return DEFAULT_BLUR_CODE

        raise e
