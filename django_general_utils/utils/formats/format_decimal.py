from babel import numbers


def format_decimal(
        value: str,
        locale: str = 'es_CL',
        **kwargs
):
    """
    Get format decimal
    @return:
    """
    return numbers.format_decimal(
        value,
        locale=locale,
        **kwargs,
    )
