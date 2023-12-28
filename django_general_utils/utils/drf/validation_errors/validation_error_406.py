from rest_framework import status
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class ValidationError406(AuthenticationFailed):
    status_code = status.HTTP_406_NOT_ACCEPTABLE
