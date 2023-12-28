from drf_spectacular.extensions import OpenApiSerializerFieldExtension
from drf_spectacular.plumbing import build_basic_type
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import Direction
from timezone_field.rest_framework import TimeZoneSerializerField



class TimeZoneSerializerFieldExtension(OpenApiSerializerFieldExtension):
    target_class = TimeZoneSerializerField
    match_subclasses = True

    def map_serializer_field(self, auto_schema, direction: Direction):
        return build_basic_type(OpenApiTypes.STR)
