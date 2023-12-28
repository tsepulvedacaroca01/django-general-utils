from django.conf import settings
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as rest_exception_handler
from rest_framework.views import set_rollback

# import traceback


def exception_handler(exc, context) -> Response:
    """
    For every time an error occurs, notify the botcenter
    @return: Response
    """

    response = rest_exception_handler(exc, context)
    if not settings.TESTING:
        pass
    # user = context['request'].user
    # user = user if not user.is_anonymous else None
    # status_code = 500
    # method = str(context['request'].method)
    # headers = dict(context['request'].headers)
    # data = dict(context['request'].data)
    # query_params = dict(context['request'].query_params)
    # error_message = str(exc)
    # error_detail = traceback.format_exc()
    # if response:
    #     status_code = response.status_code
    #
    # Error.objects.create(
    #     **{
    #         'user': user,
    #         'status_code': status_code,
    #         'method': method,
    #         'headers': headers,
    #         'data': data,
    #         'query_params': query_params,
    #         'error_message': error_message,
    #         'error_detail': error_detail,
    #     }
    # )
    if response is None and isinstance(exc, ValidationError):
        set_rollback()

        data = {
            'detail': exc.messages
        }

        if hasattr(exc, 'error_dict'):
            data = exc.error_dict

        return Response(
            status=status.HTTP_400_BAD_REQUEST,
            data=data
        )

    return response
