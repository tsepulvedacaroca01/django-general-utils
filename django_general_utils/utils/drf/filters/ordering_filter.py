from django.db.models.functions import Round
from rest_framework import filters

from ....models.functions.random_number import RandomNumber


class OrderingFilter(filters.OrderingFilter):
    def get_valid_fields(self, queryset, view, context=None):
        if context is None:
            context = {}

        ordering_fields = super().get_valid_fields(queryset, view, context)

        try:
            index = ordering_fields.index(('?', '?'))
            del ordering_fields[index]
        except ValueError:
            pass

        return ordering_fields

    def is_random_ordering(self, request, queryset, view):
        """
        Return `True` if random ordering should be applied.
        """
        params = request.query_params.get(self.ordering_param)

        if params is None:
            return False

        fields = [param.strip() for param in params.split(',')]

        return '?' in fields

    def random_ordering(self, queryset):
        """
        Return a random ordering if the `ordering` query parameter is '?'.
        """
        return queryset.annotate(_random_=Round(RandomNumber() * 5 + 1)).order_by('_random_')

    def filter_queryset(self, request, queryset, view):
        ordering = self.get_ordering(request, queryset, view)
        ordering_fields = getattr(view, 'ordering_fields', self.ordering_fields)

        if ordering_fields is not None and '?' in ordering_fields and self.is_random_ordering(request, queryset, view):
            return self.random_ordering(queryset)

        if ordering:
            queryset = queryset.order_by(*ordering)

        return queryset
