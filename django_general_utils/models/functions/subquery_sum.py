from main.utils.models.functions import SubqueryAggregate


class SubquerySum(SubqueryAggregate):
    function = 'SUM'
