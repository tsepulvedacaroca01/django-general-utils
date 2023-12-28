import functools
import typing

import drf_spectacular.authentication  # noqa: F403, F401
import drf_spectacular.serializers  # noqa: F403, F401
from drf_spectacular import openapi
from drf_spectacular.contrib import *  # noqa: F403, F401
from drf_spectacular.drainage import get_override, warn
from drf_spectacular.plumbing import (
    UnableToProceedError, build_basic_type, force_instance,
    get_doc, get_type_hints, is_field, is_serializer, resolve_type_hint, )
from drf_spectacular.types import OpenApiTypes


class AutoSchema(openapi.AutoSchema):
    def get_tags(self) -> typing.List[str]:
        """ override this for custom behaviour """
        # URL LIKE THIS: /api/v1/subscription/subscription/ where /api/v1/TAG/SUMMARY/
        return [self.path.split('/')[3].capitalize()]

    def get_summary(self):
        """ override this for custom behaviour """
        # URL LIKE THIS: /api/v1/subscription/subscription/ where /api/v1/TAG/SUMMARY/
        basename = self.path.split('/')[4].replace("_", " ").title()

        have_action = hasattr(self, 'view') and hasattr(self.view, 'action')
        have_detail = hasattr(self, 'view') and hasattr(self.view, 'detail') and self.view.detail

        if have_detail and have_action and 'details' not in self.view.action:
            basename = f'{basename} Details'

        if have_action and self.view.action not in self.method_mapping.values():
            basename = f'{basename} {self.view.action.replace("_", " ").title()}'

        return basename

    def _map_response_type_hint(self, method):
        hint = None

        if hasattr(method, 'get_annotation') and callable(method.get_annotation):
            hint = get_type_hints(method.get_annotation).get('return', None)

        if hint is None:
            func = method.func if isinstance(method, functools.partial) else method
            hint = get_override(func, 'field') or get_type_hints(func).get('return')

        if is_serializer(hint) or is_field(hint):
            return self._map_serializer_field(force_instance(hint), 'response')
        if isinstance(hint, dict):
            return hint

        try:
            schema = resolve_type_hint(hint)
        except UnableToProceedError:
            warn(
                f'unable to resolve type hint for function "{method.__name__}". Consider '
                f'using a type hint or @extend_schema_field. Defaulting to string.'
            )
            return build_basic_type(OpenApiTypes.STR)

        description = get_doc(
            method.func if isinstance(method, functools.partial) else method
        )
        if description:
            schema['description'] = description

        return schema
