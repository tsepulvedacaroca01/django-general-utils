from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser, User
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken

prefix_token = api_settings.AUTH_HEADER_TYPES


@database_sync_to_async
def get_user_by_header(headers) -> tuple:
    token_name, token_key = headers[b'authorization'].decode().split()

    if token_name == prefix_token:
        try:
            data = AccessToken(token_key)
            user = User.objects.get(id=data['user_id'])
        except TokenError:
            user = AnonymousUser()

        return user, token_key

    return AnonymousUser(), ''


@database_sync_to_async
def get_user_by_query_params(query_params) -> tuple:
    token_key = query_params.get('token', None)
    token_name = query_params.get('prefix_token', None)

    if token_name == prefix_token:
        try:
            data = AccessToken(token_key)
            user = User.objects.get(id=data['user_id'])
        except TokenError:
            user = AnonymousUser()

        return user, token_key

    return AnonymousUser(), ''


class QueryAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        headers = dict(scope['headers'])
        query_params = parse_qs(scope['query_string'].decode())

        for k, v in query_params.items():
            query_params[k] = v[-1]

        scope['query_params'] = query_params

        if b'authorization' in headers:
            scope['user'], scope['token'] = get_user_by_header(headers)
        elif query_params:
            scope['user'], scope['token'] = get_user_by_query_params(query_params)

        return await super().__call__(scope, receive, send)


TokenAuthMiddlewareSocket = lambda inner: QueryAuthMiddleware(AuthMiddlewareStack(inner))
