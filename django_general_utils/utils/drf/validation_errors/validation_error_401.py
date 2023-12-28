from rest_framework import status
from rest_framework.exceptions import APIException


class ValidationError401(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
