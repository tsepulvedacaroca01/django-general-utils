from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as rest_exception_handler
from rest_framework.views import set_rollback

from ..drf.validation_errors import ListValidationError


# import traceback
def exception_handler(exc, context) -> Response | None:
    """
    @return: Response
    """
    response = rest_exception_handler(exc, context)

    if response is None:
        set_rollback()

        data = None

        if isinstance(exc, ValidationError) and hasattr(exc, 'error_dict'):
            data = exc.error_dict

        if isinstance(exc, ListValidationError):
            data = exc.error_list

        if data is None:
            return None

        return Response(
            status=status.HTTP_400_BAD_REQUEST,
            data=data
        )

    return response
