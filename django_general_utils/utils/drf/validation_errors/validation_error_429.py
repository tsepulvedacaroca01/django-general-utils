from rest_framework import status
from rest_framework.exceptions import APIException


class ValidationError429(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
