from django.core.paginator import InvalidPage
from rest_framework import pagination
from rest_framework.exceptions import NotFound
from rest_framework.response import Response


class Pagination(pagination.PageNumberPagination):
    page_size_query_param = 'page_size'
    max_page_size = 250

    def get_paginated_response(self, data):
        return Response({
            'links': {
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            },
            'page_size': self.get_page_size(self.request),
            'num_pages': self.page.paginator.num_pages,
            'page': self.page.number,
            'count': self.page.paginator.count,
            'results': data
        })

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'properties': {
                'links': {
                    'type': 'object',
                    'properties': {
                        'next': {
                            'type': 'string',
                            'nullable': True,
                            'format': 'uri',
                            'example': 'http://api.example.org/accounts/?{page_query_param}=4'.format(
                                page_query_param=self.page_query_param
                            )
                        },
                        'previous': {
                            'type': 'string',
                            'nullable': True,
                            'format': 'uri',
                            'example': 'http://api.example.org/accounts/?{page_query_param}=2'.format(
                                page_query_param=self.page_query_param
                            )
                        },
                    }
                },
                'num_pages': {
                    'type': 'integer',
                    'example': 100,
                },
                'page': {
                    'type': 'integer',
                    'example': 1,
                },
                'count': {
                    'type': 'integer',
                    'example': 123,
                },
                'results': schema,
            },
        }

    def paginate_queryset(self, queryset, request, view=None):
        """
        Paginate a queryset if required, either returning a
        page object, or `None` if pagination is not configured for this view.
        """
        if view is not None and hasattr(view, 'max_page_size'):
            self.max_page_size = view.max_page_size

        page_size = self.get_page_size(request)

        if not page_size:
            return None

        paginator = self.django_paginator_class(queryset, page_size)
        page_number = self.get_page_number(request, paginator)

        try:
            self.page = paginator.page(page_number)
        except InvalidPage as exc:
            msg = self.invalid_page_message.format(
                page_number=page_number, message=str(exc)
            )
            raise NotFound(msg)

        if paginator.num_pages > 1 and self.template is not None:
            # The browsable API should display pagination controls.
            self.display_page_controls = True

        self.request = request

        return list(self.page)
