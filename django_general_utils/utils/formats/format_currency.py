from babel import numbers


def format_currency(
        value: str,
        currency='CLP',
        locale: str = 'es_CL',
        **kwargs
):
    """
    Get format decimal
    @return:
    """
    return numbers.format_currency(
        value,
        currency=currency,
        locale=locale,
        **kwargs,
    )
