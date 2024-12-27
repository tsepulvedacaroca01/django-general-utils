from ajax_datatable.views import AjaxDatatableView as AjaxDatatableViewBase
from django.utils.translation import gettext_lazy as _

from ..postgres import PostgresSearch


class AjaxDatatableView(AjaxDatatableViewBase):
    # initial_order = [['id', 'desc'], ]
    initial_order = []
    length_menu = [
        [10, 20, 50, 100, -1],
        [10, 20, 50, 100, _('Todos')]
    ]
    search_values_separator = '+'

    is_history_model = False
    edit_lookup_field = 'pk'

    search_icontains_fields = []
    search_trigram_fields = []
    search_word_trigram_fields = []
    search_vector_fields = []
    search_fields_bonus_rank_startswith = []

    vector_language = 'spanish'
    search_fields_filter = 'gte'
    search_fields_average = 0.4
    search_rank_weights = [0.2, 0.4, 0.6, 1]

    def filter_queryset_all_columns(self, search_value, queryset):
        return PostgresSearch.get_queryset(
            queryset,
            search_terms=search_value,
            search_fields_average=self.search_fields_average,
            search_icontains_fields=self.search_icontains_fields,
            search_trigram_fields=self.search_trigram_fields,
            search_word_trigram_fields=self.search_word_trigram_fields,
            search_vector_fields=self.search_vector_fields,
            search_fields_bonus_rank_startswith=self.search_fields_bonus_rank_startswith,
        )
