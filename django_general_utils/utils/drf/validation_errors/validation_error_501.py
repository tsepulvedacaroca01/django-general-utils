from rest_framework import status
from rest_framework.exceptions import APIException


class ValidationError501(APIException):
    status_code = status.HTTP_501_NOT_IMPLEMENTED
